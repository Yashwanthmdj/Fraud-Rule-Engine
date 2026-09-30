"""AEGIS orchestration: ingest -> evaluate -> persist -> broadcast -> alert, plus review workflow,
analytics and what-if backtesting."""
import asyncio
import copy
import json
import logging
import secrets
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import WebSocket
from sqlalchemy import func, select

from . import config
from .db import (Customer, Flag, Notification, Review, SessionLocal, Transaction, get_setting, init_db,
                 put_setting)
from .engine import DECISIONS, RuleEngine, Txn, account_standing, median
from .notifier import Notifier
from .simulator import Simulator

log = logging.getLogger("aegis")

REVIEW_ACTIONS = {"reviewed": "reviewed", "cleared": "cleared", "fraud": "fraud", "reopen": "flagged"}
TXN_FIELDS = ("id", "user_id", "user_name", "amount", "currency", "merchant", "category", "city", "country",
              "lat", "lon", "device_id", "ip", "channel", "ts")


def iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat(timespec="milliseconds") + "Z" if dt else None


def txn_dict(t: Transaction, detail: bool = True) -> dict:
    d = {k: getattr(t, k) for k in TXN_FIELDS}
    d.update(ts=iso(t.ts), risk_score=t.risk_score, risk_level=t.risk_level, status=t.status,
             source=t.source, scenario=t.scenario, latency_ms=t.latency_ms, decision=t.decision,
             decision_reason=t.decision_reason, tier=t.tier, stages=t.stages)
    if detail:
        d["flags"] = [{"rule_id": f.rule_id, "rule_name": f.rule_name, "score": f.score, "weight": f.weight,
                       "contribution": f.contribution, "reason": f.reason, "evidence": f.evidence} for f in t.flags]
        d["reviews"] = [{"action": r.action, "from_status": r.from_status, "reviewer": r.reviewer, "note": r.note,
                         "ts": iso(r.ts)} for r in t.reviews]
    return d


def notif_dict(n: Notification) -> dict:
    return {"id": n.id, "txn_id": n.txn_id, "channel": n.channel, "mode": n.mode, "status": n.status,
            "target": n.target, "subject": n.subject, "message_id": n.message_id, "error": n.error,
            "risk_score": n.risk_score, "ts": iso(n.ts)}


class Hub:
    """Fan-out of live events to every connected console."""

    def __init__(self):
        self.clients: set = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.clients.add(ws)

    def disconnect(self, ws: WebSocket):
        self.clients.discard(ws)

    async def broadcast(self, kind: str, data) -> None:
        if not self.clients:
            return
        msg = json.dumps({"type": kind, "data": data}, default=str)
        for ws in list(self.clients):
            try:
                await asyncio.wait_for(ws.send_text(msg), timeout=1.0)
            except Exception:
                self.clients.discard(ws)


class Aegis:
    def __init__(self):
        self.engine = RuleEngine(config.RULES_DIR, config.FLAG_THRESHOLD, config.ALERT_THRESHOLD)
        self.notifier = Notifier()
        self.hub = Hub()
        self.sim = Simulator(self.ingest, config.SIM_RATE,
                             demo_user={"user_id": config.DEMO_USER_ID, "name": config.DEMO_USER_NAME})
        self._last_test = 0.0
        self._last_alert: Dict[str, datetime] = {}
        self._sent_times: List[float] = []
        self.started = time.time()

    # ------------------------------------------------------------------ lifecycle
    def boot(self) -> None:
        init_db()
        with SessionLocal() as s:
            self.engine.persisted = get_setting(s, "rules", {})
            th = get_setting(s, "thresholds")
            if th:
                self.engine.flag_threshold, self.engine.alert_threshold = th["flag"], th["alert"]
            empty = s.scalar(select(func.count()).select_from(Transaction)) == 0
        self.engine.load_all()
        if empty:
            self.seed()
        self.ensure_demo_customer()

    def ensure_demo_customer(self) -> None:
        """Register the single demo cardholder (and give it a history if the DB predates it)."""
        d = self.sim.demo
        with SessionLocal() as s:
            c = s.get(Customer, d.user_id) or Customer(user_id=d.user_id)
            c.name, c.email, c.bank, c.is_demo = d.name, config.DEMO_EMAIL, config.DEMO_BANK, True
            s.add(c)
            if not s.scalar(select(func.count()).where(Transaction.user_id == d.user_id)):
                s.add_all([Transaction(**r, source="seed") for r in self.sim.profile_history(d)])
            s.commit()

    def seed(self) -> int:
        rows = self.sim.seed_history()
        with SessionLocal() as s:
            s.add_all([Transaction(**r, source="seed") for r in rows])
            s.commit()
        log.info("seeded %d historical transactions for %d cardholders", len(rows), len(self.sim.users))
        return len(rows)

    async def watch_rules(self):
        while True:
            await asyncio.sleep(1.0)
            try:
                changes = self.engine.reload_if_changed()
            except Exception as exc:
                log.error("rule reload failed: %s", exc)
                continue
            if changes:
                await self.hub.broadcast("rules", {"event": "reloaded", **changes})

    async def push_stats(self):
        while True:
            await asyncio.sleep(2.0)
            if self.hub.clients:
                await self.hub.broadcast("stats", self.stats())

    # ------------------------------------------------------------------ pipeline
    @staticmethod
    def _history(s, user_id: str, before: datetime, days: int = 90, limit: int = 400) -> List[Txn]:
        rows = s.execute(select(Transaction)
                         .where(Transaction.user_id == user_id, Transaction.ts <= before,
                                Transaction.ts >= before - timedelta(days=days))
                         .order_by(Transaction.ts.desc()).limit(limit)).scalars()
        return [Txn.from_model(r) for r in rows]

    @staticmethod
    def normalize(p: dict) -> dict:
        p = {k: v for k, v in p.items() if v is not None}
        ts = p.get("ts")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if isinstance(ts, datetime) and ts.tzinfo is not None:
            ts = datetime.utcfromtimestamp(ts.timestamp())
        p["ts"] = ts or datetime.utcnow()
        p.setdefault("id", "TX" + secrets.token_hex(5).upper())
        p.setdefault("user_name", p["user_id"])
        p["amount"] = round(float(p["amount"]), 2)
        return {k: p[k] for k in TXN_FIELDS if k in p}

    async def ingest(self, payload: dict, source: str = "api", scenario: Optional[str] = None) -> dict:
        """The real-time path: validate -> load history -> run rules + decide -> persist -> push.

        Every stage is timed and returned, so "how is it real-time?" is answered with numbers.
        The alert (SES/SNS) runs after the response, off the hot path.
        """
        clock = [time.perf_counter()]
        stages: Dict[str, float] = {}

        def lap(name: str) -> None:
            clock.append(time.perf_counter())
            stages[name] = round((clock[-1] - clock[-2]) * 1000, 3)

        data = self.normalize(payload)
        with SessionLocal() as s:
            if s.get(Transaction, data["id"]):
                raise ValueError(f"transaction {data['id']} already exists")
            lap("validate")
            view = Txn(**{k: data[k] for k in data if k != "user_name"})
            history = self._history(s, data["user_id"], data["ts"])
            lap("history")
            ev = self.engine.evaluate(view, history)
            lap("rules")
            m = Transaction(**data, risk_score=ev.score, risk_level=ev.level,
                            status="flagged" if ev.flagged else "clean", source=source, scenario=scenario,
                            decision=ev.decision, decision_reason=ev.decision_reason, tier=ev.standing.get("tier"))
            m.flags = [Flag(rule_id=h.rule_id, rule_name=h.rule_name, score=h.score, weight=h.weight,
                            contribution=h.contribution, reason=h.reason, evidence=h.evidence) for h in ev.hits]
            s.add(m)
            s.commit()
            lap("persist")
            m.stages = dict(stages)
            m.latency_ms = round((clock[-1] - clock[0]) * 1000, 2)
            s.commit()
            d = txn_dict(m)
        evd = ev.to_dict()
        evd["tier"] = ev.standing.get("tier")
        await self.hub.broadcast("txn", d)
        lap("broadcast")
        if ev.alert:
            asyncio.create_task(self._alert(d, evd))
        return {"transaction": d, "evaluation": evd, "decision": ev.decision, "stages": stages,
                "latency_ms": round((clock[-1] - clock[0]) * 1000, 2)}

    async def _alert(self, txn: dict, ev: dict, force: bool = False) -> List[dict]:
        now = datetime.utcnow()
        last = self._last_alert.get(txn["user_id"])
        self._sent_times = [t for t in self._sent_times if time.time() - t < 3600]
        why = None
        if not force and last and (now - last).total_seconds() < config.ALERT_COOLDOWN_SECONDS:
            why = (f"cardholder already alerted {int((now - last).total_seconds())}s ago "
                   f"(cooldown {config.ALERT_COOLDOWN_SECONDS}s)")
        elif not force and self.notifier.mode == "live" and len(self._sent_times) >= config.ALERT_MAX_PER_HOUR:
            why = f"hourly email cap reached ({config.ALERT_MAX_PER_HOUR}/h, AEGIS_ALERT_MAX_PER_HOUR)"
        if why:
            records = [{"txn_id": txn["id"], "channel": "all", "mode": self.notifier.mode, "status": "suppressed",
                        "subject": self.notifier.subject(txn, ev), "risk_score": ev["score"], "target": "",
                        "message_id": "", "error": why}]
        else:
            if not force:  # manual test / case-report sends don't start the cardholder cooldown
                self._last_alert[txn["user_id"]] = now
            if self.notifier.mode == "live":
                self._sent_times.append(time.time())
            records = await asyncio.to_thread(self.notifier.send, txn, ev)
        out = []
        with SessionLocal() as s:
            for r in records:
                n = Notification(**r)
                s.add(n)
                s.flush()
                out.append(notif_dict(n))
            s.commit()
        for n in out:
            await self.hub.broadcast("alert", n)
        return out

    async def send_test_alert(self) -> List[dict]:
        """One sample alert to prove delivery end to end (rate-limited: the endpoint is public)."""
        if time.time() - self._last_test < 15:
            raise ValueError("a test alert was sent less than 15s ago")
        self._last_test = time.time()
        txn = {"id": "TEST-" + secrets.token_hex(3).upper(), "user_id": config.DEMO_USER_ID,
               "user_name": config.DEMO_USER_NAME, "amount": 4999.0, "currency": "USD", "merchant": "AEGIS test",
               "category": "test", "city": "Hyderabad", "country": "IN", "device_id": "-",
               "ts": iso(datetime.utcnow())}
        ev = {"score": 99.0, "level": "critical", "decision": "hold", "tier": "test",
              "decision_reason": "Test alert from the AEGIS console: if you can read this, delivery works",
              "hits": [{"rule_name": "Delivery test", "reason": "Sent from Alerts > Send test alert", "contribution": 0.99}]}
        return await self._alert(txn, ev, force=True)

    def recheck_notifier(self) -> dict:
        self.notifier.configure()
        return self.notifier.status()

    # ------------------------------------------------------------------ review workflow
    async def review(self, txn_id: str, action: str, reviewer: str, note: str) -> dict:
        if action not in REVIEW_ACTIONS:
            raise ValueError(f"action must be one of {sorted(REVIEW_ACTIONS)}")
        with SessionLocal() as s:
            t = s.get(Transaction, txn_id)
            if not t:
                raise KeyError(txn_id)
            s.add(Review(txn_id=txn_id, action=action, from_status=t.status, reviewer=reviewer or "analyst",
                         note=note or ""))
            t.status = REVIEW_ACTIONS[action]
            s.commit()
            s.refresh(t)
            d = txn_dict(t)
        await self.hub.broadcast("review", d)
        return d

    # ------------------------------------------------------------------ queries
    def detail(self, txn_id: str) -> dict:
        with SessionLocal() as s:
            t = s.get(Transaction, txn_id)
            if not t:
                raise KeyError(txn_id)
            d = txn_dict(t)
            hist = s.execute(select(Transaction).where(Transaction.user_id == t.user_id)
                             .order_by(Transaction.ts.desc()).limit(400)).scalars().all()
            amounts = [h.amount for h in hist if h.id != t.id]
            d["cardholder"] = {
                "user_id": t.user_id, "name": t.user_name, "txn_count": len(hist),
                "median_amount": round(median(amounts), 2) if amounts else None,
                "devices": sorted({h.device_id for h in hist if h.device_id}),
                "countries": [c for c, _ in Counter(h.country for h in hist if h.country).most_common()],
                "home": Counter(h.city for h in hist if h.city).most_common(1)[0][0] if hist else "",
                "fraud_count": sum(1 for h in hist if h.status == "fraud"),
            }
            cust = s.get(Customer, t.user_id)
            d["cardholder"].update(email=cust.email if cust else "", bank=cust.bank if cust else "",
                                   is_demo=bool(cust and cust.is_demo))
            # standing *now* (after reviews), vs. d["tier"] = standing when it was scored
            d["standing"] = account_standing([Txn.from_model(h) for h in hist], datetime.utcnow())
            d["timeline"] = [txn_dict(h, detail=False) for h in hist[:40]]
            d["notifications"] = [notif_dict(n) for n in s.execute(
                select(Notification).where(Notification.txn_id == txn_id).order_by(Notification.ts)).scalars()]
            return d

    def list_txns(self, status: Optional[str], level: Optional[str], q: Optional[str], min_score: float,
                  limit: int, sort: str) -> List[dict]:
        with SessionLocal() as s:
            stmt = select(Transaction).where(Transaction.source != "seed")
            if status:
                stmt = stmt.where(Transaction.status.in_(status.split(",")))
            if level:
                stmt = stmt.where(Transaction.risk_level.in_(level.split(",")))
            if min_score:
                stmt = stmt.where(Transaction.risk_score >= min_score)
            if q:
                like = f"%{q}%"
                stmt = stmt.where(Transaction.id.ilike(like) | Transaction.user_id.ilike(like) |
                                  Transaction.user_name.ilike(like) | Transaction.merchant.ilike(like) |
                                  Transaction.city.ilike(like))
            order = [Transaction.risk_score.desc(), Transaction.ts.desc()] if sort == "risk" else [Transaction.ts.desc()]
            rows = s.execute(stmt.order_by(*order).limit(min(limit, 1000))).scalars().all()
            return [txn_dict(t) for t in rows]

    def attack_runs(self, limit: int = 25) -> List[dict]:
        """Attack Lab log rebuilt from persisted ground-truth labels (survives restarts)."""
        with SessionLocal() as s:
            rows = s.execute(select(Transaction).where(Transaction.scenario.is_not(None))
                             .order_by(Transaction.ts.desc()).limit(limit * 10)).scalars().all()
        runs: Dict[str, dict] = {}
        for t in reversed(rows):
            r = runs.setdefault(t.scenario, {"run": t.scenario, "scenario": t.scenario.split(":")[0],
                                             "victim_name": t.user_name, "started": iso(t.ts), "n": 0,
                                             "max_score": 0.0, "level": "low", "top_id": t.id, "caught_at": None})
            r["n"] += 1
            if t.risk_score >= r["max_score"]:
                r.update(max_score=t.risk_score, level=t.risk_level, top_id=t.id)
            if r["caught_at"] is None and t.risk_score >= self.engine.flag_threshold:
                r["caught_at"] = r["n"]
        return sorted(runs.values(), key=lambda r: r["started"], reverse=True)[:limit]

    def notifications(self, limit: int = 100) -> List[dict]:
        with SessionLocal() as s:
            return [notif_dict(n) for n in s.execute(
                select(Notification).order_by(Notification.ts.desc()).limit(limit)).scalars()]

    def stats(self) -> dict:
        now = datetime.utcnow()
        e = self.engine
        with SessionLocal() as s:
            live = Transaction.source != "seed"
            by_status = dict(s.execute(select(Transaction.status, func.count()).where(live)
                                       .group_by(Transaction.status)).all())
            total = sum(by_status.values())
            last60 = s.scalar(select(func.count()).where(live, Transaction.ts >= now - timedelta(seconds=60)))
            avg_latency = s.scalar(select(func.avg(Transaction.latency_ms)).where(live, Transaction.ts >= now - timedelta(minutes=5)))
            by_decision = dict(s.execute(select(Transaction.decision, func.count())
                                         .where(live, Transaction.decision.is_not(None))
                                         .group_by(Transaction.decision)).all())
            exposure = s.scalar(select(func.sum(Transaction.amount)).where(Transaction.status == "flagged")) or 0
            prevented = s.scalar(select(func.sum(Transaction.amount)).where(Transaction.status == "fraud")) or 0

            recent = s.execute(select(Transaction.ts, Transaction.risk_score, Transaction.risk_level)
                               .where(live, Transaction.ts >= now - timedelta(minutes=30))).all()
            buckets = defaultdict(lambda: [0, 0, 0])
            for ts, score, lvl in recent:
                b = buckets[int((now - ts).total_seconds() // 60)]
                b[0] += 1
                b[1] += score >= e.flag_threshold
                b[2] += lvl == "critical"
            series = [{"minute": -i, "total": buckets[i][0], "flagged": buckets[i][1], "critical": buckets[i][2]}
                      for i in range(29, -1, -1)]

            rule_rows = s.execute(select(Flag.rule_id, Transaction.status, func.count())
                                  .join(Transaction, Flag.txn_id == Transaction.id)
                                  .where(Transaction.risk_score >= e.flag_threshold)
                                  .group_by(Flag.rule_id, Transaction.status)).all()
            per_rule: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
            for rid, st, c in rule_rows:
                per_rule[rid][st] += c
            rules = {}
            for rid, sts in per_rule.items():
                labeled = sts["fraud"] + sts["cleared"]
                rules[rid] = {"flags": sum(sts.values()), "confirmed": sts["fraud"], "cleared": sts["cleared"],
                              "precision": round(sts["fraud"] / labeled, 3) if labeled else None}

            scen = s.execute(select(Transaction.scenario, Transaction.risk_score, Transaction.amount, Transaction.ts)
                             .where(Transaction.scenario.is_not(None)).order_by(Transaction.ts)).all()
            runs: Dict[str, dict] = {}
            for sc, score, amt, ts in scen:
                r = runs.setdefault(sc, {"n": 0, "caught_at": None, "blocked": 0.0, "kind": sc.split(":")[0]})
                r["n"] += 1
                if score >= e.flag_threshold:
                    r["blocked"] += amt
                    if r["caught_at"] is None:
                        r["caught_at"] = r["n"]
            caught = [r for r in runs.values() if r["caught_at"]]
            n_alerts = s.scalar(select(func.count()).select_from(Notification).where(
                Notification.status.in_(["sent", "simulated"]))) or 0
            suppressed = s.scalar(select(func.count()).select_from(Notification).where(
                Notification.status == "suppressed")) or 0

        flagged_total = sum(v for k, v in by_status.items() if k != "clean")
        return {
            "total": total, "by_status": by_status, "flagged_total": flagged_total,
            "by_decision": {k: by_decision.get(k, 0) for k in DECISIONS},
            "pending": by_status.get("flagged", 0), "tpm": last60, "avg_latency_ms": round(avg_latency or 0, 2),
            "exposure": round(exposure, 2), "prevented": round(prevented, 2), "series": series, "rules": rules,
            "alerts": {"sent": n_alerts, "suppressed": suppressed, "mode": self.notifier.mode},
            "attacks": {"runs": len(runs), "caught": len(caught),
                        "avg_txns_to_detect": round(sum(r["caught_at"] for r in caught) / len(caught), 2) if caught else None,
                        "blocked_amount": round(sum(r["blocked"] for r in runs.values()), 2)},
            "thresholds": {"flag": e.flag_threshold, "alert": e.alert_threshold},
            "simulator": {"running": self.sim.running, "rate": self.sim.rate},
            "uptime": int(time.time() - self.started), "clients": len(self.hub.clients),
        }

    # ------------------------------------------------------------------ config
    def configure_rule(self, rule_id: str, **kw) -> dict:
        out = self.engine.configure(rule_id, **kw)
        with SessionLocal() as s:
            put_setting(s, "rules", self.engine.persisted)
            s.commit()
        return out

    def set_thresholds(self, flag: Optional[float], alert: Optional[float]) -> dict:
        f = self.engine.flag_threshold if flag is None else float(flag)
        a = self.engine.alert_threshold if alert is None else float(alert)
        if not 0 < f < a <= 100:
            raise ValueError("need 0 < flag threshold < alert threshold <= 100")
        self.engine.flag_threshold, self.engine.alert_threshold = f, a
        with SessionLocal() as s:
            put_setting(s, "thresholds", {"flag": f, "alert": a})
            s.commit()
        return {"flag": f, "alert": a}

    # ------------------------------------------------------------------ what-if backtest
    def backtest(self, limit: int = 600, rules: Optional[Dict[str, dict]] = None,
                 thresholds: Optional[dict] = None) -> dict:
        """Replay recent traffic through a *proposed* configuration without touching production."""
        t0 = time.perf_counter()
        trial = RuleEngine(self.engine.rules_dir, **{
            "flag_threshold": (thresholds or {}).get("flag", self.engine.flag_threshold),
            "alert_threshold": (thresholds or {}).get("alert", self.engine.alert_threshold)})
        trial.persisted = copy.deepcopy(self.engine.persisted)
        for rid, cfg in (rules or {}).items():
            base = trial.persisted.setdefault(rid, {})
            for k in ("enabled", "weight"):
                if k in cfg:
                    base[k] = cfg[k]
            if cfg.get("params"):
                base["params"] = {**base.get("params", {}), **cfg["params"]}
        trial.load_all()

        with SessionLocal() as s:
            rows = s.execute(select(Transaction).where(Transaction.source != "seed")
                             .order_by(Transaction.ts.desc()).limit(limit)).scalars().all()
            rows.reverse()
            cm = {"before": Counter(), "after": Counter()}
            newly, dropped, rule_hits, alerts_after, flagged_before, flagged_after = [], [], Counter(), 0, 0, 0
            for t in rows:
                ev = trial.evaluate(Txn.from_model(t), self._history(s, t.user_id, t.ts))
                was = t.risk_score >= self.engine.flag_threshold
                flagged_before += was
                flagged_after += ev.flagged
                alerts_after += ev.alert
                for h in ev.hits:
                    rule_hits[h.rule_id] += 1
                label = True if (t.status == "fraud" or t.scenario) else False if t.status == "cleared" else None
                if label is not None:
                    for key, pred in (("before", was), ("after", ev.flagged)):
                        cm[key][("tp" if pred else "fn") if label else ("fp" if pred else "tn")] += 1
                brief = {"id": t.id, "user_name": t.user_name, "amount": t.amount, "merchant": t.merchant,
                         "before": t.risk_score, "after": ev.score}
                if ev.flagged and not was:
                    newly.append(brief)
                elif was and not ev.flagged:
                    dropped.append(brief)

        def metrics(c):
            tp, fp, fn = c["tp"], c["fp"], c["fn"]
            return {**{k: c[k] for k in ("tp", "fp", "fn", "tn")},
                    "precision": round(tp / (tp + fp), 3) if tp + fp else None,
                    "recall": round(tp / (tp + fn), 3) if tp + fn else None}

        return {"evaluated": len(rows), "flagged_before": flagged_before, "flagged_after": flagged_after,
                "alerts_after": alerts_after, "newly_flagged": newly[-25:], "no_longer_flagged": dropped[-25:],
                "newly_count": len(newly), "dropped_count": len(dropped), "rule_hits": dict(rule_hits),
                "labeled": {"before": metrics(cm["before"]), "after": metrics(cm["after"])},
                "duration_ms": round((time.perf_counter() - t0) * 1000, 1)}

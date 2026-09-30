"""The contract every fraud rule implements.

A rule is any subclass of ``Rule`` living in a module inside the rules directory.
The engine discovers it automatically - no registration, no edits to the core.
"""
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional


@dataclass(frozen=True)
class Txn:
    """Read-only view of a transaction handed to rules (rules can't mutate state)."""
    id: str
    user_id: str
    amount: float
    ts: datetime
    currency: str = "USD"
    merchant: str = ""
    category: str = "retail"
    city: str = ""
    country: str = ""
    lat: Optional[float] = None
    lon: Optional[float] = None
    device_id: str = ""
    ip: str = ""
    channel: str = "card_present"
    # Reviewer verdict on *past* transactions (clean | flagged | reviewed | cleared | fraud).
    # Empty for the transaction being scored. This is how analyst decisions feed back into scoring.
    status: str = ""

    @classmethod
    def from_model(cls, m) -> "Txn":
        return cls(id=m.id, user_id=m.user_id, amount=m.amount, ts=m.ts, currency=m.currency,
                   merchant=m.merchant, category=m.category, city=m.city, country=m.country,
                   lat=m.lat, lon=m.lon, device_id=m.device_id, ip=m.ip, channel=m.channel,
                   status=m.status or "")

    @property
    def has_location(self) -> bool:
        return self.lat is not None and self.lon is not None


@dataclass
class RuleResult:
    """What a rule returns when it fires. ``score`` is the rule's confidence in 0..1."""
    score: float
    reason: str
    evidence: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.score = max(0.0, min(1.0, float(self.score)))


class RuleContext:
    """Everything a rule may look at besides the transaction itself.

    ``history`` is the cardholder's prior activity, newest first, strictly *before*
    the transaction being scored. That makes evaluation deterministic and lets the
    very same rules replay history in backtests without peeking into the future.
    """

    def __init__(self, txn: Txn, history: Iterable[Txn]):
        self.txn = txn
        self._history: List[Txn] = [h for h in history if h.id != txn.id and h.ts <= txn.ts]
        self._history.sort(key=lambda h: h.ts, reverse=True)
        self._standing: Optional[dict] = None

    def standing(self) -> dict:
        """The account's standing at the moment of this transaction (see ``account_standing``)."""
        if self._standing is None:
            self._standing = account_standing(self._history, self.txn.ts)
        return self._standing

    def history(self, within: Optional[timedelta] = None, limit: Optional[int] = None) -> List[Txn]:
        items = self._history
        if within is not None:
            cutoff = self.txn.ts - within
            items = [h for h in items if h.ts >= cutoff]
        return items[:limit] if limit else list(items)

    def last(self, with_location: bool = False) -> Optional[Txn]:
        for h in self._history:
            if not with_location or h.has_location:
                return h
        return None

    def known_devices(self, older_than: Optional[timedelta] = None) -> set:
        """Devices seen on this card. With ``older_than``, only devices that have aged in."""
        cutoff = self.txn.ts - older_than if older_than else None
        return {h.device_id for h in self._history if h.device_id and (cutoff is None or h.ts <= cutoff)}

    def known_countries(self) -> set:
        return {h.country for h in self._history if h.country}


class Rule(ABC):
    """Base class for all fraud rules.

    Subclasses declare metadata as class attributes and implement ``evaluate``.
    ``params`` holds tunable knobs; reviewers can edit them live in the console.
    """
    id: str = ""
    name: str = ""
    description: str = ""
    category: str = "behavioral"
    default_weight: float = 1.0
    params: Dict[str, float] = {}
    param_help: Dict[str, str] = {}

    def __init__(self, overrides: Optional[Dict[str, float]] = None):
        self.p: Dict[str, float] = {**self.params, **(overrides or {})}

    @abstractmethod
    def evaluate(self, txn: Txn, ctx: RuleContext) -> Optional[RuleResult]:
        """Return a RuleResult when the rule fires, or None when the transaction looks fine."""


# ---------- helpers shared by rules ----------

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def ramp(value: float, start: float, full: float) -> float:
    """Linear 0..1 ramp: 0 at ``start``, 1 at ``full``."""
    if full == start:
        return 1.0 if value >= full else 0.0
    return max(0.0, min(1.0, (value - start) / (full - start)))


def median(xs: List[float]) -> float:
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


# ---------- account memory ----------

TIERS = ("new", "trusted", "normal", "watchlist", "compromised")


def account_standing(history: List[Txn], now: datetime) -> dict:
    """Summarise what AEGIS already knows about an account from its reviewed history.

    This is the difference between "a good customer having an unusual day" and "an account
    we have already caught being abused": the same transaction means something different
    depending on the account's track record.

    Tiers: compromised (confirmed fraud in the last 30 days), watchlist (older confirmed fraud
    or several unresolved flags in 24h), new (too little history to judge), trusted (a month+
    of clean history), normal (everything else).
    """
    fraud = sorted((h for h in history if h.status == "fraud"), key=lambda h: h.ts, reverse=True)
    fraud_30d = [h for h in fraud if now - h.ts <= timedelta(days=30)]
    open_24h = [h for h in history if h.status == "flagged" and now - h.ts <= timedelta(hours=24)]
    cleared = [h for h in history if h.status == "cleared"]
    first = min((h.ts for h in history), default=now)
    age_days = max(0.0, (now - first).total_seconds() / 86400)

    reasons: List[str] = []
    if fraud_30d:
        tier = "compromised"
        hours = (now - fraud_30d[0].ts).total_seconds() / 3600
        when = f"{hours:.0f}h ago" if hours < 48 else f"{hours / 24:.0f} days ago"
        reasons.append(f"analyst confirmed fraud on this account {when} ({fraud_30d[0].id})")
    elif fraud:
        tier = "watchlist"
        reasons.append(f"{len(fraud)} confirmed fraud case(s) in the last 90 days")
    elif len(open_24h) >= 2:
        tier = "watchlist"
        reasons.append(f"{len(open_24h)} unresolved flags in the last 24h")
    elif len(history) < 5 or age_days < 7:
        tier = "new"
        reasons.append(f"only {len(history)} transactions over {age_days:.0f} days, baseline still forming")
    elif age_days >= 30 and len(history) >= 15:
        tier = "trusted"
        reasons.append(f"{len(history)} transactions over {age_days:.0f} days with no confirmed fraud")
    else:
        tier = "normal"
        reasons.append(f"{len(history)} transactions over {age_days:.0f} days")
    if cleared:
        reasons.append(f"{len(cleared)} earlier alert(s) verified as genuine by an analyst")

    return {"tier": tier, "reasons": reasons, "confirmed_fraud": len(fraud),
            "last_fraud_id": fraud[0].id if fraud else None, "open_flags_24h": len(open_24h),
            "analyst_cleared": len(cleared), "age_days": round(age_days, 1), "txn_count": len(history)}

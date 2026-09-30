from datetime import timedelta

from app.engine import Rule, RuleResult, median, ramp


class AmountAnomalyRule(Rule):
    id = "amount_anomaly"
    name = "Unusual Amount"
    description = ("Compares the amount against this cardholder's own spending baseline using a robust "
                   "z-score (median + MAD), so one past splurge can't hide the next anomaly. Confirmed "
                   "fraud is excluded from the baseline, and a similar amount an analyst already verified "
                   "as genuine lowers the score: the rule learns from reviewer decisions.")
    category = "behavioral"
    default_weight = 0.85
    params = {"lookback_days": 90, "min_history": 5, "z_start": 4, "z_full": 14, "cold_start_ceiling": 3000,
              "learn_match": 0.6, "learned_discount": 0.3}
    param_help = {
        "lookback_days": "How far back the personal baseline looks",
        "min_history": "Transactions needed before trusting the baseline",
        "z_start": "Robust z-score where suspicion begins",
        "z_full": "Robust z-score where the rule is 100% confident",
        "cold_start_ceiling": "Amount considered risky for a card with no history",
        "learn_match": "An analyst-cleared amount >= this fraction of the current one counts as precedent",
        "learned_discount": "Confidence multiplier when such a precedent exists",
    }

    def evaluate(self, txn, ctx):
        recent = ctx.history(within=timedelta(days=self.p["lookback_days"]))
        past = [t.amount for t in recent if t.status != "fraud"]   # fraud must not become "normal"

        if len(past) < self.p["min_history"]:
            ceiling = self.p["cold_start_ceiling"]
            if txn.amount < ceiling:
                return None
            res = RuleResult(ramp(txn.amount, ceiling, ceiling * 4) * 0.8 + 0.2,
                             f"${txn.amount:,.2f} on a card with only {len(past)} prior transactions "
                             f"(cold-start ceiling ${ceiling:,.0f})",
                             {"amount": txn.amount, "history_size": len(past), "mode": "cold_start"})
            return self._learn(txn, recent, res)

        med = median(past)
        mad = median([abs(x - med) for x in past])
        scale = max(1.4826 * mad, 0.25 * med, 5.0)
        z = (txn.amount - med) / scale
        if z < self.p["z_start"]:
            return None

        ratio = txn.amount / med if med else float("inf")
        res = RuleResult(
            ramp(z, self.p["z_start"], self.p["z_full"]),
            f"${txn.amount:,.2f} is {ratio:.1f}x this cardholder's typical ${med:,.2f} (robust z = {z:.1f})",
            {"amount": txn.amount, "median": round(med, 2), "mad": round(mad, 2), "z": round(z, 2),
             "ratio": round(ratio, 2), "history_size": len(past), "max_seen": max(past), "mode": "baseline"},
        )
        return self._learn(txn, recent, res)

    def _learn(self, txn, recent, res):
        """Reviewer feedback: an analyst already confirmed a comparable spend was the real customer."""
        precedent = [t for t in recent if t.status == "cleared" and t.amount >= txn.amount * self.p["learn_match"]]
        if not precedent:
            return res
        p = max(precedent, key=lambda t: t.ts)
        res.score *= self.p["learned_discount"]
        res.reason += (f". Learned: an analyst verified ${p.amount:,.2f} on {p.ts:%d %b} as genuine, "
                       f"so confidence is reduced x{self.p['learned_discount']}")
        res.evidence["learned"] = {"txn_id": p.id, "amount": p.amount, "ts": p.ts,
                                   "discount": self.p["learned_discount"]}
        return res

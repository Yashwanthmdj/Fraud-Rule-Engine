from datetime import timedelta

from app.engine import Rule, RuleResult, median, ramp


class AmountAnomalyRule(Rule):
    id = "amount_anomaly"
    name = "Unusual Amount"
    description = ("Compares the amount against this cardholder's own spending baseline using a robust "
                   "z-score (median + MAD), so one past splurge can't hide the next anomaly. Falls back "
                   "to an absolute ceiling for brand-new cards with no history.")
    category = "behavioral"
    default_weight = 0.85
    params = {"lookback_days": 90, "min_history": 5, "z_start": 4, "z_full": 14, "cold_start_ceiling": 3000}
    param_help = {
        "lookback_days": "How far back the personal baseline looks",
        "min_history": "Transactions needed before trusting the baseline",
        "z_start": "Robust z-score where suspicion begins",
        "z_full": "Robust z-score where the rule is 100% confident",
        "cold_start_ceiling": "Amount considered risky for a card with no history",
    }

    def evaluate(self, txn, ctx):
        past = [t.amount for t in ctx.history(within=timedelta(days=self.p["lookback_days"]))]

        if len(past) < self.p["min_history"]:
            ceiling = self.p["cold_start_ceiling"]
            if txn.amount < ceiling:
                return None
            return RuleResult(ramp(txn.amount, ceiling, ceiling * 4) * 0.8 + 0.2,
                              f"${txn.amount:,.2f} on a card with only {len(past)} prior transactions "
                              f"(cold-start ceiling ${ceiling:,.0f})",
                              {"amount": txn.amount, "history_size": len(past), "mode": "cold_start"})

        med = median(past)
        mad = median([abs(x - med) for x in past])
        scale = max(1.4826 * mad, 0.25 * med, 5.0)
        z = (txn.amount - med) / scale
        if z < self.p["z_start"]:
            return None

        ratio = txn.amount / med if med else float("inf")
        return RuleResult(
            ramp(z, self.p["z_start"], self.p["z_full"]),
            f"${txn.amount:,.2f} is {ratio:.1f}x this cardholder's typical ${med:,.2f} (robust z = {z:.1f})",
            {"amount": txn.amount, "median": round(med, 2), "mad": round(mad, 2), "z": round(z, 2),
             "ratio": round(ratio, 2), "history_size": len(past), "max_seen": max(past), "mode": "baseline"},
        )

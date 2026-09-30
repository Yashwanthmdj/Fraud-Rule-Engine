from datetime import timedelta

from app.engine import Rule, RuleResult, ramp


class VelocityRule(Rule):
    id = "velocity"
    name = "Transaction Velocity"
    description = ("Too many transactions from one card in a short window. Also recognises the "
                   "card-testing signature: a burst of tiny charges probing whether a stolen card works.")
    category = "velocity"
    default_weight = 0.85
    params = {"window_seconds": 120, "max_txns": 3, "saturate_txns": 8, "micro_amount": 5}
    param_help = {
        "window_seconds": "Sliding window length",
        "max_txns": "Transactions allowed in the window before firing",
        "saturate_txns": "Count at which the rule is 100% confident",
        "micro_amount": "Charges at or below this look like card testing",
    }

    def evaluate(self, txn, ctx):
        window = timedelta(seconds=self.p["window_seconds"])
        recent = ctx.history(within=window)
        count = len(recent) + 1
        if count <= self.p["max_txns"]:
            return None

        burst = [txn] + recent
        micro = [t for t in burst if t.amount <= self.p["micro_amount"]]
        span = max(1, int((txn.ts - recent[-1].ts).total_seconds()))
        score = ramp(count, self.p["max_txns"], self.p["saturate_txns"])
        reason = (f"{count} transactions in {span}s (limit {int(self.p['max_txns'])} per "
                  f"{int(self.p['window_seconds'])}s) across {len({t.merchant for t in burst})} merchants")
        if len(micro) >= 3:
            score = max(score, 0.75)
            reason += f" - {len(micro)} micro-charges <= ${self.p['micro_amount']:.0f} (card-testing pattern)"

        return RuleResult(score, reason, {
            "count": count, "span_seconds": span, "window_seconds": self.p["window_seconds"],
            "total_amount": round(sum(t.amount for t in burst), 2), "micro_charges": len(micro),
            "timeline": [{"id": t.id, "ts": t.ts, "amount": t.amount, "merchant": t.merchant} for t in burst],
        })

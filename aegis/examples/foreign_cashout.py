"""Drop-in demo rule. Copy this file into backend/app/rules/ while AEGIS is running:
the engine hot-loads it within a second - no restart, no change to the core engine."""
from app.engine import Rule, RuleResult

LIQUID = {"gift_cards", "crypto", "wire_transfer"}


class ForeignCashOutRule(Rule):
    id = "foreign_cashout"
    name = "Foreign Cash-Out"
    description = "Liquid-asset purchase (gift cards / crypto / wire) from a country this card has never used."
    category = "geo"
    default_weight = 0.7
    params = {"min_amount": 250}
    param_help = {"min_amount": "Ignore cash-outs below this amount"}

    def evaluate(self, txn, ctx):
        if txn.category not in LIQUID or txn.amount < self.p["min_amount"]:
            return None
        seen = {h.country for h in ctx.history() if h.category not in LIQUID}
        if not txn.country or txn.country in seen:
            return None
        return RuleResult(0.8, f"{txn.category.replace('_', ' ')} cash-out of ${txn.amount:,.0f} from {txn.country}, "
                               f"a country this card has never shopped in", {"seen_countries": sorted(seen)})

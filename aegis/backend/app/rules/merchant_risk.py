from app.engine import Rule, RuleResult, ramp

HIGH_RISK = {"gift_cards": 0.55, "crypto": 0.6, "wire_transfer": 0.5, "gambling": 0.45}


class MerchantRiskRule(Rule):
    id = "merchant_risk"
    name = "High-Risk Merchant"
    description = ("Categories fraudsters love because the money is instantly liquid and irreversible: "
                   "gift cards, crypto exchanges, wire transfers, gambling. Confidence grows with amount.")
    category = "merchant"
    default_weight = 0.45
    params = {"amount_floor": 200, "amount_full": 2000}
    param_help = {"amount_floor": "Below this amount the category alone is only mildly risky",
                  "amount_full": "Amount at which category risk counts in full"}

    def evaluate(self, txn, ctx):
        base = HIGH_RISK.get(txn.category)
        if base is None:
            return None
        scale = 0.4 + 0.6 * ramp(txn.amount, self.p["amount_floor"], self.p["amount_full"])
        return RuleResult(base * scale,
                          f"{txn.category.replace('_', ' ')} merchant '{txn.merchant}' - funds are hard to recover",
                          {"category": txn.category, "category_risk": base})

from app.engine import Rule, RuleResult, median


class AccountStandingRule(Rule):
    id = "account_standing"
    name = "Account Standing"
    description = ("Remembers what analysts already decided about this account. A card with confirmed "
                   "fraud stays risky for every transaction that follows, even small, normal-looking ones; "
                   "an account piling up unresolved flags is watched more closely.")
    category = "identity"
    default_weight = 0.9
    params = {"compromised_score": 0.6, "watchlist_score": 0.3, "open_flag_step": 0.1, "amount_boost": 0.3}
    param_help = {
        "compromised_score": "Confidence for any transaction on an account with fraud in the last 30 days",
        "watchlist_score": "Confidence for an account on the watchlist",
        "open_flag_step": "Extra confidence per unresolved flag in the last 24h",
        "amount_boost": "Extra confidence when a risky account also spends above its usual amount",
    }

    def evaluate(self, txn, ctx):
        st = ctx.standing()
        if st["tier"] == "compromised":
            score = self.p["compromised_score"]
        elif st["tier"] == "watchlist":
            score = self.p["watchlist_score"] + self.p["open_flag_step"] * st["open_flags_24h"]
        else:
            return None
        reason = f"{'Account compromised' if st['tier'] == 'compromised' else 'Account on watchlist'}: {st['reasons'][0]}"
        genuine = [h.amount for h in ctx.history() if h.status != "fraud"]
        med = median(genuine) if genuine else 0
        if med and txn.amount > 2 * med:
            score += self.p["amount_boost"]
            reason += f", and this is {txn.amount / med:.1f}x the genuine typical spend"
        return RuleResult(score, reason, {**st, "genuine_median": round(med, 2)})

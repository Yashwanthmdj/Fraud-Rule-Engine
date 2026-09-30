from datetime import timedelta

from app.engine import Rule, RuleResult, median


class NewDeviceRule(Rule):
    id = "new_device"
    name = "Unrecognized Device"
    description = ("Card used from a device fingerprint never seen on this account. Weak on its own "
                   "(people buy new phones) but a strong amplifier for account-takeover patterns.")
    category = "identity"
    default_weight = 0.5
    params = {"min_history": 3, "base_score": 0.35, "amount_multiplier": 3, "trust_after_hours": 24}
    param_help = {
        "min_history": "Transactions needed before a device can be 'new'",
        "base_score": "Confidence for any unknown device",
        "amount_multiplier": "Also spending > N x median on it pushes confidence up",
        "trust_after_hours": "A device only becomes trusted after it has been around this long",
    }

    def evaluate(self, txn, ctx):
        past = ctx.history()
        if len(past) < self.p["min_history"] or not txn.device_id:
            return None
        known = ctx.known_devices(older_than=timedelta(hours=self.p["trust_after_hours"]))
        if txn.device_id in known:
            return None
        med = median([t.amount for t in past])
        score = self.p["base_score"]
        seen_recently = txn.device_id in ctx.known_devices()
        reason = (f"Device {txn.device_id[:10]} "
                  f"{'first seen minutes ago' if seen_recently else 'never seen before'} ({len(known)} trusted devices)")
        if med and txn.amount > med * self.p["amount_multiplier"]:
            score = min(1.0, score + 0.4)
            reason += f", spending {txn.amount / med:.1f}x usual on first use"
        new_country = txn.country and txn.country not in ctx.known_countries()
        if new_country:
            score = min(1.0, score + 0.2)
            reason += f", first activity ever in {txn.country}"
        return RuleResult(score, reason, {"device_id": txn.device_id, "known_devices": sorted(known),
                                          "new_country": bool(new_country)})

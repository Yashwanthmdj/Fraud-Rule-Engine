from datetime import timedelta

from app.engine import Rule, RuleResult, haversine_km, ramp


class ImpossibleTravelRule(Rule):
    id = "impossible_travel"
    name = "Impossible Travel"
    description = ("Great-circle distance between consecutive transactions divided by elapsed time. "
                   "If the card would have had to move faster than a commercial jet, one of the two "
                   "swipes is not the real cardholder.")
    category = "geo"
    default_weight = 0.9
    params = {"max_speed_kmh": 900, "min_distance_km": 150, "lookback_hours": 24, "online_discount": 0.6}
    param_help = {
        "max_speed_kmh": "Fastest plausible travel speed (airliner cruise)",
        "min_distance_km": "Ignore hops shorter than this (GPS / IP noise)",
        "lookback_hours": "Only compare against transactions this recent",
        "online_discount": "Multiplier for online txns (IP geolocation is fuzzier)",
    }

    def evaluate(self, txn, ctx):
        if not txn.has_location:
            return None
        prev = next((h for h in ctx.history(within=timedelta(hours=self.p["lookback_hours"])) if h.has_location), None)
        if prev is None:
            return None

        dist = haversine_km(prev.lat, prev.lon, txn.lat, txn.lon)
        if dist < self.p["min_distance_km"]:
            return None
        seconds = max((txn.ts - prev.ts).total_seconds(), 1.0)
        speed = dist / (seconds / 3600)
        if speed <= self.p["max_speed_kmh"]:
            return None

        score = ramp(speed, self.p["max_speed_kmh"], self.p["max_speed_kmh"] * 4)
        if "online" in (txn.channel, prev.channel):
            score *= self.p["online_discount"]
        minutes = seconds / 60
        took = f"{minutes:.0f} min" if minutes >= 1 else f"{seconds:.0f}s"
        return RuleResult(
            score,
            f"{prev.city or 'previous location'} -> {txn.city or 'here'}: {dist:,.0f} km in {took} "
            f"implies {speed:,.0f} km/h (max plausible {self.p['max_speed_kmh']:,.0f} km/h)",
            {"from": {"txn_id": prev.id, "city": prev.city, "country": prev.country, "lat": prev.lat,
                      "lon": prev.lon, "ts": prev.ts},
             "to": {"txn_id": txn.id, "city": txn.city, "country": txn.country, "lat": txn.lat,
                    "lon": txn.lon, "ts": txn.ts},
             "distance_km": round(dist, 1), "minutes": round(minutes, 2), "speed_kmh": round(speed)},
        )

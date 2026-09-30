"""Synthetic but realistic payment traffic, plus on-demand fraud attack scenarios.

Every cardholder has a home city, a personal spending scale, favourite categories and
known devices, so the behavioural rules have a genuine baseline to learn from.
Scenario transactions carry a ground-truth ``scenario`` label so the console can
measure the engine's detection rate live.
"""
import asyncio
import math
import random
import secrets
from datetime import datetime, timedelta
from typing import Awaitable, Callable, Dict, List, Optional

CITIES = [
    ("New York", "US", 40.71, -74.01), ("San Francisco", "US", 37.77, -122.42), ("Chicago", "US", 41.88, -87.63),
    ("Los Angeles", "US", 34.05, -118.24), ("Toronto", "CA", 43.65, -79.38), ("Mexico City", "MX", 19.43, -99.13),
    ("Sao Paulo", "BR", -23.55, -46.63), ("Buenos Aires", "AR", -34.60, -58.38), ("London", "GB", 51.51, -0.13),
    ("Paris", "FR", 48.86, 2.35), ("Berlin", "DE", 52.52, 13.40), ("Madrid", "ES", 40.42, -3.70),
    ("Amsterdam", "NL", 52.37, 4.90), ("Istanbul", "TR", 41.01, 28.98), ("Dubai", "AE", 25.20, 55.27),
    ("Mumbai", "IN", 19.08, 72.88), ("Bengaluru", "IN", 12.97, 77.59), ("Hyderabad", "IN", 17.39, 78.49),
    ("Delhi", "IN", 28.61, 77.21), ("Singapore", "SG", 1.35, 103.82), ("Hong Kong", "HK", 22.32, 114.17),
    ("Tokyo", "JP", 35.68, 139.69), ("Seoul", "KR", 37.57, 126.98), ("Sydney", "AU", -33.87, 151.21),
    ("Johannesburg", "ZA", -26.20, 28.05), ("Nairobi", "KE", -1.29, 36.82), ("Cairo", "EG", 30.04, 31.24),
]
HOME_CITIES = [c for c in CITIES if c[0] not in ("Cairo", "Nairobi")]
FRAUD_CITIES = [("Lagos", "NG", 6.52, 3.38), ("Moscow", "RU", 55.76, 37.62), ("Bangkok", "TH", 13.76, 100.50),
                 ("Kyiv", "UA", 50.45, 30.52), ("Manila", "PH", 14.60, 120.98), ("Lima", "PE", -12.05, -77.04)]

CATEGORIES = {
    # category: (relative frequency, amount multiplier, online probability, merchants)
    "grocery": (22, 1.0, 0.1, ["FreshCart Market", "GreenLeaf Grocers", "Daily Basket", "Harvest Hall"]),
    "restaurants": (18, 0.7, 0.15, ["Saffron Table", "Noodle Theory", "Brick Oven Co.", "Blue Door Cafe"]),
    "fuel": (9, 0.9, 0.0, ["Volt & Fuel", "Northstar Gas", "Swift Pump"]),
    "transport": (12, 0.35, 0.8, ["Metro Transit", "RideNow", "Zoom Cabs"]),
    "online_retail": (14, 1.2, 1.0, ["Parcelly", "ShopSphere", "Bazaar.io"]),
    "subscriptions": (7, 0.25, 1.0, ["StreamBox", "CloudLocker", "TuneStream"]),
    "pharmacy": (6, 0.5, 0.1, ["CarePlus Pharmacy", "MediQuick"]),
    "fashion": (6, 1.6, 0.4, ["Thread & Needle", "Urban Loom", "Atelier Nine"]),
    "electronics": (3, 2.6, 0.5, ["Circuit City Works", "Pixel Depot", "GadgetHub"]),
    "travel": (3, 3.2, 0.9, ["SkyWays Air", "StayLoop Hotels", "RailJet"]),
}
FIRST = ["Aarav", "Maya", "Liam", "Sofia", "Kenji", "Amara", "Noah", "Priya", "Lucas", "Zara", "Ethan", "Ananya",
         "Mateo", "Chloe", "Omar", "Isla", "Ravi", "Hana", "Leo", "Fatima", "Arjun", "Elena", "Kai", "Nadia",
         "Diego", "Aisha", "Felix", "Mei", "Yash", "Grace", "Tariq", "Ines", "Rohan", "Lena", "Samir", "Ava"]
LAST = ["Sharma", "Okafor", "Tanaka", "Silva", "Müller", "Rossi", "Kim", "Reddy", "Dubois", "Haddad", "Novak",
        "Patel", "Garcia", "Chen", "Johansson", "Mensah", "Kowalski", "Nair", "Walker", "Costa", "Ahmed", "Ivanova"]

N_USERS = 250


def _tx_id() -> str:
    return "TX" + secrets.token_hex(5).upper()


def _device(rng: random.Random) -> str:
    return "dev_" + "".join(rng.choice("0123456789abcdef") for _ in range(10))


def _ip(rng: random.Random) -> str:
    return ".".join(str(rng.randint(11, 223)) for _ in range(4))


class Profile:
    def __init__(self, idx: int, rng: random.Random):
        self.user_id = f"C{100000 + idx * 37}"
        self.name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        self.home = rng.choice(HOME_CITIES)
        self.scale = math.exp(rng.gauss(math.log(38), 0.55))       # personal "typical ticket"
        self.devices = [_device(rng) for _ in range(rng.choice([1, 1, 2, 2, 3]))]
        self.ip = _ip(rng)
        cats = list(CATEGORIES)
        self.cat_weights = [CATEGORIES[c][0] * rng.uniform(0.4, 1.8) for c in cats]


class Simulator:
    def __init__(self, submit: Callable[..., Awaitable[dict]], rate: float = 1.2,
                 demo_user: Optional[Dict[str, str]] = None):
        self.submit = submit
        self.rate = rate
        self.running = False
        self.rng = random.Random()
        seed_rng = random.Random(1337)
        self.users: List[Profile] = [Profile(i, seed_rng) for i in range(N_USERS)]
        self.demo: Optional[Profile] = None
        if demo_user:  # one named, predictable cardholder to target in live demos
            d = Profile(N_USERS, random.Random(2026))
            d.user_id, d.name = demo_user["user_id"], demo_user["name"]
            d.home = ("Hyderabad", "IN", 17.39, 78.49)
            d.scale = 45.0
            self.demo = d
            self.users.insert(0, d)
        self.by_id: Dict[str, Profile] = {u.user_id: u for u in self.users}
        self.scenario_log: List[dict] = []

    def profile_history(self, u: Profile, days: int = 45) -> List[dict]:
        return [self.normal_txn(u, ts=datetime.utcnow() - timedelta(days=self.rng.uniform(1, days),
                                                                   hours=self.rng.uniform(0, 12)))
                for _ in range(self.rng.randint(25, 35))]

    # ------------------------------------------------------------------ normal traffic
    def normal_txn(self, u: Profile, ts: Optional[datetime] = None, city=None) -> dict:
        rng = self.rng
        cat = rng.choices(list(CATEGORIES), weights=u.cat_weights)[0]
        _, mult, p_online, merchants = CATEGORIES[cat]
        online = rng.random() < p_online
        name, country, lat, lon = city or u.home
        amount = round(u.scale * mult * math.exp(rng.gauss(0, 0.5)), 2)
        return {
            "id": _tx_id(), "user_id": u.user_id, "user_name": u.name, "amount": max(1.0, amount),
            "currency": "USD", "merchant": rng.choice(merchants), "category": cat,
            "city": name, "country": country,
            "lat": round(lat + rng.uniform(-0.06, 0.06), 4), "lon": round(lon + rng.uniform(-0.06, 0.06), 4),
            "device_id": rng.choice(u.devices), "ip": u.ip, "channel": "online" if online else "card_present",
            "ts": ts or datetime.utcnow(),
        }

    def seed_history(self, days: int = 45) -> List[dict]:
        """Backdated history so every cardholder has a behavioural baseline from minute one."""
        rows, now = [], datetime.utcnow()
        for u in self.users:
            n = self.rng.randint(18, 40)
            trip = self.rng.choice(CITIES) if self.rng.random() < 0.25 else None
            trip_day = self.rng.randint(8, days - 3)
            for _ in range(n):
                day = self.rng.uniform(1, days)
                ts = now - timedelta(days=day, hours=self.rng.uniform(0, 12))
                city = trip if trip and trip_day <= day <= trip_day + 3 else None
                rows.append(self.normal_txn(u, ts=ts, city=city))
        return rows

    async def run(self):
        while True:
            if self.running and self.rate > 0:
                try:
                    await self.submit(self.normal_txn(self.rng.choice(self.users)), source="simulator")
                except Exception as exc:  # keep the stream alive no matter what
                    print("simulator error:", exc)
                await asyncio.sleep(self.rng.expovariate(self.rate))
            else:
                await asyncio.sleep(0.25)

    # ------------------------------------------------------------------ attack scenarios
    SCENARIOS = {
        "card_testing": {"title": "Card Testing Burst", "icon": "zap",
                         "story": "A bot validates a stolen card with rapid micro-charges, then cashes out."},
        "impossible_travel": {"title": "Impossible Travel", "icon": "plane",
                              "story": "Card swiped at home, then minutes later on another continent."},
        "amount_spike": {"title": "Amount Spike", "icon": "trend",
                         "story": "A cloned card makes one purchase ~30x the owner's normal ticket."},
        "account_takeover": {"title": "Account Takeover", "icon": "skull",
                             "story": "New device, foreign country, rapid gift card + crypto + wire cash-out."},
        "fraud_storm": {"title": "Fraud Storm", "icon": "storm",
                        "story": "All four attacks at once on different victims. Watch alert de-duplication."},
    }

    def _victim(self, user_id: Optional[str] = None) -> Profile:
        return self.by_id.get(user_id) if user_id in self.by_id else self.rng.choice(self.users)

    def _far_city(self, u: Profile, pool=None):
        from .engine import haversine_km
        pool = pool or CITIES + FRAUD_CITIES
        far = [c for c in pool if haversine_km(u.home[2], u.home[3], c[2], c[3]) > 4000]
        return self.rng.choice(far)

    def _mk(self, u: Profile, **kw) -> dict:
        base = self.normal_txn(u)
        base.update(kw)
        return base

    async def launch(self, name: str, user_id: Optional[str] = None) -> dict:
        if name not in self.SCENARIOS:
            raise KeyError(name)
        if name == "fraud_storm":
            victims = self.rng.sample(self.users, 4)
            for scen, v in zip(["card_testing", "impossible_travel", "amount_spike", "account_takeover"], victims):
                asyncio.create_task(self.launch(scen, v.user_id))
            return {"scenario": name, "victims": [v.user_id for v in victims]}
        u = self._victim(user_id)
        info = {"scenario": name, "victim": u.user_id, "victim_name": u.name, "home": u.home[0],
                "started": datetime.utcnow().isoformat() + "Z"}
        self.scenario_log.insert(0, info)
        del self.scenario_log[50:]
        info["run"] = f"{name}:{secrets.token_hex(2)}"
        asyncio.create_task(getattr(self, f"_run_{name}")(u, info["run"]))
        return info

    async def _send(self, txn: dict, scenario: Optional[str], delay: float = 0.0):
        if delay:
            await asyncio.sleep(delay)
        return await self.submit(txn, source="scenario", scenario=scenario)

    async def _run_card_testing(self, u: Profile, tag: str):
        bot_dev, bot_ip = _device(self.rng), _ip(self.rng)
        shops = ["PixelKeys Digital", "QuickTop-Up", "AppCredits Store", "eVoucher Hub", "GameCoins", "StreamGift"]
        for i in range(7):
            await self._send(self._mk(u, amount=round(self.rng.uniform(0.5, 4.99), 2), merchant=self.rng.choice(shops),
                                      category="online_retail", channel="online", device_id=bot_dev, ip=bot_ip),
                             tag, delay=0 if i == 0 else self.rng.uniform(0.9, 1.6))
        await self._send(self._mk(u, amount=round(self.rng.uniform(1200, 1900), 2), merchant="GadgetHub",
                                  category="electronics", channel="online", device_id=bot_dev, ip=bot_ip),
                         tag, delay=1.5)

    async def _run_impossible_travel(self, u: Profile, tag: str):
        gap = self.rng.randint(8, 25)
        await self._send(self._mk(u, ts=datetime.utcnow() - timedelta(minutes=gap), channel="card_present",
                                  category="restaurants", merchant="Blue Door Cafe"), None)
        name, country, lat, lon = self._far_city(u)
        await self._send(self._mk(u, city=name, country=country, lat=lat, lon=lon, channel="card_present",
                                  amount=round(u.scale * self.rng.uniform(3, 6), 2), category="fashion",
                                  merchant="Atelier Nine"), tag, delay=1.2)

    async def _run_amount_spike(self, u: Profile, tag: str):
        await self._send(self._mk(u, amount=round(u.scale * self.rng.uniform(28, 45), 2), category="jewelry",
                                  merchant="Maison Aurelle Jewelers", channel="card_present"), tag)

    async def _run_account_takeover(self, u: Profile, tag: str):
        await self._send(self._mk(u, ts=datetime.utcnow() - timedelta(minutes=self.rng.randint(20, 50)),
                                  category="grocery", merchant="FreshCart Market", channel="card_present"), None)
        name, country, lat, lon = self._far_city(u, FRAUD_CITIES)
        dev, ip = _device(self.rng), _ip(self.rng)
        steps = [("gift_cards", "GiftVault Online", 900), ("crypto", "CoinSwift Exchange", 2500),
                 ("wire_transfer", "RapidWire Intl", 4200)]
        for cat, merch, amt in steps:
            await self._send(self._mk(u, city=name, country=country, lat=lat, lon=lon, device_id=dev, ip=ip,
                                      channel="online", category=cat, merchant=merch,
                                      amount=round(amt * self.rng.uniform(0.85, 1.2), 2)),
                             tag, delay=1.4)

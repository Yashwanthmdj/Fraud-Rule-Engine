import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.config import RULES_DIR
from app.engine import Hit, RuleEngine, Txn

T0 = datetime(2026, 9, 30, 12, 0, 0)
LONDON, TOKYO, PARIS = (51.51, -0.13), (35.68, 139.69), (48.86, 2.35)


def tx(i, minutes=0.0, amount=40.0, loc=LONDON, city="London", device="dev_a", **kw):
    return Txn(id=f"t{i}", user_id="u1", amount=amount, ts=T0 + timedelta(minutes=minutes),
               lat=loc[0], lon=loc[1], city=city, country="GB", device_id=device, **kw)


def baseline(n=20):
    """A month of ordinary ~$40 purchases at home."""
    return [tx(f"h{i}", minutes=-60 * 24 * (i + 1), amount=30 + (i % 7) * 4) for i in range(n)]


@pytest.fixture()
def engine():
    e = RuleEngine(RULES_DIR)
    e.load_all()
    return e


def rule_ids(ev):
    return {h.rule_id for h in ev.hits}


def test_discovers_plugin_rules(engine):
    assert {"velocity", "amount_anomaly", "impossible_travel", "new_device", "merchant_risk"} <= set(engine.rules)
    assert engine.load_errors == {}


def test_normal_transaction_is_clean(engine):
    ev = engine.evaluate(tx(1, amount=42), baseline())
    assert not ev.flagged and ev.level == "low"


def test_velocity_fires_on_burst(engine):
    hist = baseline() + [tx(f"b{i}", minutes=-0.2 * i, amount=2) for i in range(1, 7)]
    ev = engine.evaluate(tx(99, amount=3), hist)
    assert "velocity" in rule_ids(ev)
    assert ev.flagged
    assert "card-testing" in next(h.reason for h in ev.hits if h.rule_id == "velocity")


def test_velocity_ignores_normal_pace(engine):
    hist = baseline() + [tx("b1", minutes=-30)]
    assert "velocity" not in rule_ids(engine.evaluate(tx(99), hist))


def test_amount_anomaly_uses_personal_baseline(engine):
    ev = engine.evaluate(tx(1, amount=1500), baseline())
    hit = next(h for h in ev.hits if h.rule_id == "amount_anomaly")
    assert hit.evidence["ratio"] > 30 and ev.flagged
    assert "amount_anomaly" not in rule_ids(engine.evaluate(tx(2, amount=70), baseline()))


def test_impossible_travel(engine):
    hist = baseline() + [tx("home", minutes=-10)]
    ev = engine.evaluate(tx(1, loc=TOKYO, city="Tokyo"), hist)
    hit = next(h for h in ev.hits if h.rule_id == "impossible_travel")
    assert hit.evidence["speed_kmh"] > 40000
    assert ev.level == "critical" and ev.alert


def test_plausible_travel_is_fine(engine):
    hist = baseline() + [tx("home", minutes=-240)]
    assert "impossible_travel" not in rule_ids(engine.evaluate(tx(1, loc=PARIS, city="Paris"), hist))


def test_noisy_or_fusion():
    hits = [Hit("a", "A", 0.5, 1, 0.5, "", {}), Hit("b", "B", 0.5, 1, 0.5, "", {})]
    assert RuleEngine.fuse(hits) == 75.0
    assert RuleEngine.fuse([]) == 0.0


def test_disable_and_reweight(engine):
    hist = baseline() + [tx("home", minutes=-10)]
    engine.configure("impossible_travel", enabled=False)
    assert "impossible_travel" not in rule_ids(engine.evaluate(tx(1, loc=TOKYO), hist))
    engine.configure("impossible_travel", enabled=True, weight=0.2)
    hit = next(h for h in engine.evaluate(tx(1, loc=TOKYO), hist).hits if h.rule_id == "impossible_travel")
    assert hit.contribution <= 0.2


def test_hot_reload_and_fault_isolation(tmp_path: Path):
    shutil.copy(RULES_DIR / "velocity.py", tmp_path / "velocity.py")
    e = RuleEngine(tmp_path)
    e.load_all()
    assert set(e.rules) == {"velocity"}

    (tmp_path / "broken.py").write_text("this is not python(")
    (tmp_path / "exploding.py").write_text(
        "from app.engine import Rule\n"
        "class Boom(Rule):\n    id='boom'\n    name='Boom'\n"
        "    def evaluate(self, txn, ctx):\n        raise RuntimeError('kaboom')\n")
    time.sleep(0.01)
    changes = e.reload_if_changed()
    assert changes["added"] == ["boom"] and "broken.py" in changes["errors"]

    ev = e.evaluate(tx(1), baseline())          # a crashing rule never breaks scoring
    assert ev.errors[0]["rule_id"] == "boom" and ev.score == 0

    shutil.copy(Path(__file__).parents[2] / "examples" / "foreign_cashout.py", tmp_path / "foreign_cashout.py")
    assert "foreign_cashout" in e.reload_if_changed()["added"]


def test_backtest_safe_history_never_sees_future(engine):
    future = tx("future", minutes=+5, amount=9999)
    ev = engine.evaluate(tx(1), baseline() + [future])
    assert not ev.flagged

import time

from fastapi.testclient import TestClient

from app.main import aegis, app


def test_end_to_end_review_flow():
    with TestClient(app) as c:
        assert c.get("/api/health").json()["rules"] >= 3
        assert c.get("/api/transactions").status_code == 200
        # a normal purchase for a seeded cardholder, then an impossible hop to the other side of the world
        u = aegis.sim.users[0]
        r1 = c.post("/api/transactions", json={"user_id": u.user_id, "amount": 20, "lat": u.home[2], "lon": u.home[3],
                                                "city": u.home[0], "device_id": u.devices[0]}).json()
        far = (-u.home[2], u.home[3] + 180 if u.home[3] < 0 else u.home[3] - 180)
        r2 = c.post("/api/transactions", json={"user_id": u.user_id, "amount": u.scale * 40, "lat": far[0],
                                                "lon": far[1], "city": "Antipode", "device_id": "dev_evil"}).json()
        assert r1["evaluation"]["flagged"] is False
        assert r2["evaluation"]["level"] == "critical"
        tid = r2["transaction"]["id"]

        queue = c.get("/api/transactions", params={"status": "flagged"}).json()
        assert tid in [t["id"] for t in queue]

        assert c.post(f"/api/transactions/{tid}/review", json={"action": "bogus"}).status_code == 400
        done = c.post(f"/api/transactions/{tid}/review", json={"action": "fraud", "reviewer": "ci", "note": "confirmed"}).json()
        assert done["status"] == "fraud" and done["reviews"][-1]["reviewer"] == "ci"
        assert c.post(f"/api/transactions/{tid}/review", json={"action": "cleared"}).json()["status"] == "cleared"

        detail = c.get(f"/api/transactions/{tid}").json()
        assert {f["rule_id"] for f in detail["flags"]} >= {"impossible_travel", "amount_anomaly"}
        assert detail["cardholder"]["txn_count"] > 10

        time.sleep(0.3)
        assert any(n["txn_id"] == tid for n in c.get("/api/notifications").json())
        assert c.patch("/api/settings/thresholds", json={"flag": 90, "alert": 50}).status_code == 400
        bt = c.post("/api/backtest", json={"limit": 50, "rules": {"impossible_travel": {"enabled": False}}}).json()
        assert bt["evaluated"] >= 2


def test_realtime_decision_stages_demo_user_and_test_alert():
    with TestClient(app) as c:
        sim = c.get("/api/simulator").json()
        demo = sim["demo_user"]
        assert demo and demo["user_id"] in {u.user_id for u in aegis.sim.users}
        r = c.post("/api/transactions", json={"user_id": demo["user_id"], "amount": 30}).json()
        assert r["decision"] in {"approve", "step_up", "hold", "decline"}
        assert {"validate", "history", "rules", "persist", "broadcast"} <= set(r["stages"])
        d = c.get(f"/api/transactions/{r['transaction']['id']}").json()
        assert d["cardholder"]["is_demo"] and d["standing"]["tier"] in {"trusted", "normal", "new"}
        assert d["decision"] == r["decision"] and d["stages"]

        st = c.get("/api/settings").json()["notifier"]
        assert st["mode"] == "dry-run" and st["checks"]
        sent = c.post("/api/notifications/test").json()
        assert sent[0]["status"] == "simulated"
        assert c.post("/api/notifications/test").status_code == 429
        assert set(c.get("/api/stats").json()["by_decision"]) == {"approve", "step_up", "hold", "decline"}

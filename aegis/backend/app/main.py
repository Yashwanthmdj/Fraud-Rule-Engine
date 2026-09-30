"""AEGIS HTTP + WebSocket API."""
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config
from .service import Aegis

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
aegis = Aegis()


@asynccontextmanager
async def lifespan(_: FastAPI):
    aegis.boot()
    aegis.sim.running = config.SIM_AUTOSTART
    tasks = [asyncio.create_task(c) for c in (aegis.sim.run(), aegis.watch_rules(), aegis.push_stats())]
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(title="AEGIS Fraud Rule Engine", version="1.0.0", lifespan=lifespan,
              description="Pluggable real-time fraud rule engine with a reviewer console.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---------------------------------------------------------------- schemas
class TxnIn(BaseModel):
    user_id: str = Field(..., examples=["C100037"])
    amount: float = Field(..., gt=0, examples=[4999.0])
    id: Optional[str] = None
    user_name: Optional[str] = None
    currency: str = "USD"
    merchant: str = "Unknown merchant"
    category: str = "retail"
    city: str = ""
    country: str = ""
    lat: Optional[float] = Field(None, ge=-90, le=90)
    lon: Optional[float] = Field(None, ge=-180, le=180)
    device_id: str = ""
    ip: str = ""
    channel: str = "card_present"
    ts: Optional[datetime] = None


class ReviewIn(BaseModel):
    action: str = Field(..., description="reviewed | cleared | fraud | reopen")
    reviewer: str = "analyst"
    note: str = ""


class RulePatch(BaseModel):
    enabled: Optional[bool] = None
    weight: Optional[float] = None
    params: Optional[Dict[str, float]] = None


class ThresholdPatch(BaseModel):
    flag: Optional[float] = None
    alert: Optional[float] = None


class SimPatch(BaseModel):
    running: Optional[bool] = None
    rate: Optional[float] = Field(None, ge=0, le=25)


class BacktestIn(BaseModel):
    limit: int = Field(600, ge=10, le=5000)
    rules: Optional[Dict[str, dict]] = None
    thresholds: Optional[Dict[str, float]] = None


# ---------------------------------------------------------------- transactions
@app.post("/api/transactions", tags=["transactions"], summary="Score and persist a transaction in real time")
async def ingest(txn: TxnIn):
    try:
        return await aegis.ingest(txn.model_dump(), source="api")
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@app.get("/api/transactions", tags=["transactions"])
def list_transactions(status: Optional[str] = None, level: Optional[str] = None, q: Optional[str] = None,
                      min_score: float = 0, limit: int = Query(200, le=1000), sort: str = "time"):
    return aegis.list_txns(status, level, q, min_score, limit, sort)


@app.get("/api/transactions/{txn_id}", tags=["transactions"])
def get_transaction(txn_id: str):
    try:
        return aegis.detail(txn_id)
    except KeyError:
        raise HTTPException(404, "transaction not found")


@app.post("/api/transactions/{txn_id}/review", tags=["review"], summary="Mark reviewed / cleared / fraud / reopen")
async def review(txn_id: str, body: ReviewIn):
    try:
        return await aegis.review(txn_id, body.action, body.reviewer, body.note)
    except KeyError:
        raise HTTPException(404, "transaction not found")
    except ValueError as exc:
        raise HTTPException(400, str(exc))


# ---------------------------------------------------------------- rules
@app.get("/api/rules", tags=["rules"])
def rules():
    return aegis.engine.describe()


@app.patch("/api/rules/{rule_id}", tags=["rules"])
async def patch_rule(rule_id: str, body: RulePatch):
    try:
        out = aegis.configure_rule(rule_id, **body.model_dump(exclude_none=True))
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    await aegis.hub.broadcast("rules", {"event": "configured", "rule_id": rule_id})
    return out


@app.post("/api/rules/reload", tags=["rules"])
async def reload_rules():
    changes = aegis.engine.load_all()
    await aegis.hub.broadcast("rules", {"event": "reloaded", **changes})
    return changes


@app.post("/api/backtest", tags=["rules"], summary="Replay recent traffic through a proposed configuration")
async def backtest(body: BacktestIn):
    return await asyncio.to_thread(aegis.backtest, body.limit, body.rules, body.thresholds)


@app.get("/api/settings", tags=["settings"])
def settings():
    return {"thresholds": {"flag": aegis.engine.flag_threshold, "alert": aegis.engine.alert_threshold},
            "notifier": aegis.notifier.status(),
            "simulator": {"running": aegis.sim.running, "rate": aegis.sim.rate, "users": len(aegis.sim.users)}}


@app.patch("/api/settings/thresholds", tags=["settings"])
async def patch_thresholds(body: ThresholdPatch):
    try:
        out = aegis.set_thresholds(body.flag, body.alert)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    await aegis.hub.broadcast("settings", {"thresholds": out})
    return out


# ---------------------------------------------------------------- alerts
@app.get("/api/notifications", tags=["alerts"])
def notifications(limit: int = Query(100, le=500)):
    return aegis.notifications(limit)


@app.post("/api/notifications/test/{txn_id}", tags=["alerts"], summary="Re-send the alert for a transaction now")
async def test_notification(txn_id: str):
    try:
        d = aegis.detail(txn_id)
    except KeyError:
        raise HTTPException(404, "transaction not found")
    ev = {"score": d["risk_score"], "level": d["risk_level"],
          "hits": [{"rule_name": f["rule_name"], "reason": f["reason"], "contribution": f["contribution"]}
                   for f in d["flags"]]}
    return await aegis._alert(d, ev, force=True)


@app.get("/api/notifications/preview/{txn_id}", tags=["alerts"], summary="Render the alert email HTML")
def preview_notification(txn_id: str):
    from fastapi.responses import HTMLResponse
    try:
        d = aegis.detail(txn_id)
    except KeyError:
        raise HTTPException(404, "transaction not found")
    ev = {"score": d["risk_score"], "level": d["risk_level"], "hits": d["flags"]}
    return HTMLResponse(aegis.notifier.html_body(d, ev))


# ---------------------------------------------------------------- simulator / attack lab
@app.get("/api/simulator", tags=["simulator"])
def simulator():
    return {"running": aegis.sim.running, "rate": aegis.sim.rate, "scenarios": aegis.sim.SCENARIOS,
            "users": len(aegis.sim.users), "log": aegis.attack_runs()}


@app.patch("/api/simulator", tags=["simulator"])
async def patch_simulator(body: SimPatch):
    if body.running is not None:
        aegis.sim.running = body.running
    if body.rate is not None:
        aegis.sim.rate = body.rate
    state = {"running": aegis.sim.running, "rate": aegis.sim.rate}
    await aegis.hub.broadcast("simulator", state)
    return state


@app.post("/api/scenarios/{name}", tags=["simulator"], summary="Launch a live fraud attack scenario")
async def launch_scenario(name: str, user_id: Optional[str] = None):
    try:
        info = await aegis.sim.launch(name, user_id)
    except KeyError:
        raise HTTPException(404, f"unknown scenario; choose from {list(aegis.sim.SCENARIOS)}")
    await aegis.hub.broadcast("scenario", info)
    return info


# ---------------------------------------------------------------- live + meta
@app.get("/api/stats", tags=["meta"])
def stats():
    return aegis.stats()


@app.get("/api/health", tags=["meta"])
def health():
    return {"ok": True, "rules": len(aegis.engine.rules), "notifier": aegis.notifier.mode}


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await aegis.hub.connect(websocket)
    try:
        await websocket.send_json({"type": "hello", "data": aegis.stats()})
        while True:
            await websocket.receive_text()  # keepalive pings from the console
    except WebSocketDisconnect:
        pass
    finally:
        aegis.hub.disconnect(websocket)


# ---------------------------------------------------------------- console (built React app)
if config.FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=config.FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        root = config.FRONTEND_DIST.resolve()
        f = (root / path).resolve()
        ok = path and f.is_file() and root in f.parents
        if ok:
            return FileResponse(f)
        return FileResponse(root / "index.html", headers={"Cache-Control": "no-cache"})

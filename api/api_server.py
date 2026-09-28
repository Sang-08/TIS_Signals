"""
api_server.py — FastAPI server expose dữ liệu từ SQLite cho Web Dashboard.

CHẠY: python run_api.py  (từ thư mục gốc CrypT/)
HOẶC: python -m api.api_server
"""

import os
import sys
import uvicorn
from datetime import datetime, timezone
from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Add project root to path for bot package imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.database import CryptDB
from bot.collector import fetch_fear_greed, fear_greed_label
from bot.economic_calendar import get_upcoming_high_impact, get_this_week_events, hours_to_next_high_event
from bot.labeler import get_label_stats
from bot.trainer import load_latest_model

load_dotenv()

db = CryptDB()

app = FastAPI(
    title="Trading Intelligence API",
    description="API for CrypT Trading Intelligence Dashboard",
    version="1.0",
)

# CORS for dashboard HTML
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve dashboard static files
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHBOARD_DIR = os.path.join(PROJECT_ROOT, "dashboard")
if os.path.isdir(DASHBOARD_DIR):
    app.mount("/dashboard", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")


@app.get("/")
async def root():
    return {"message": "Trading Intelligence API", "dashboard": "/dashboard/index.html"}


@app.get("/api/summary")
async def api_summary():
    snapshots = db.get_latest_snapshots()
    fg = fetch_fear_greed()
    h_event = hours_to_next_high_event()
    upcoming = get_upcoming_high_impact(hours=24)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "snapshots": snapshots,
        "fear_greed": fg,
        "fear_greed_label": fear_greed_label(fg),
        "hours_to_next_event": h_event,
        "upcoming_events": upcoming[:3] if upcoming else [],
    }


@app.get("/api/candles")
async def api_candles(
    asset: str = Query("BTCUSDT"),
    hours: int = Query(168),
):
    history = db.get_price_history(asset, hours=hours)
    return {
        "asset": asset, "hours": hours, "count": len(history),
        "data": [{"timestamp": ts, "price": price} for ts, price in history],
    }


@app.get("/api/derivatives")
async def api_derivatives(asset: str = Query("BTCUSDT")):
    snapshot = db.get_latest_snapshot(asset)
    return {"asset": asset, "snapshot": snapshot}


@app.get("/api/funding-history")
async def api_funding_history(asset: str = Query("BTCUSDT"), hours: int = Query(24)):
    history = db.get_funding_history(asset, hours=hours)
    return {
        "asset": asset, "hours": hours, "count": len(history),
        "data": [{"timestamp": ts, "rate": rate} for ts, rate in history],
    }


@app.get("/api/oi-history")
async def api_oi_history(asset: str = Query("BTCUSDT"), hours: int = Query(24)):
    history = db.get_oi_history(asset, hours=hours)
    return {
        "asset": asset, "hours": hours, "count": len(history),
        "data": [{"timestamp": ts, "oi": oi} for ts, oi in history],
    }


@app.get("/api/signals")
async def api_signals(asset: str = Query(None), limit: int = Query(50)):
    signals = db.get_recent_signals(asset=asset, limit=limit)
    return {"asset": asset, "count": len(signals), "signals": signals}


@app.get("/api/news")
async def api_news(limit: int = Query(20)):
    news = db.get_recent_news(limit=limit)
    return {"count": len(news), "news": news}


@app.get("/api/whale")
async def api_whale(hours: int = Query(24)):
    txs = db.get_recent_whale_txs(hours=hours, limit=50)
    return {"hours": hours, "count": len(txs), "transactions": txs}


@app.get("/api/accuracy")
async def api_accuracy():
    rows = db._execute(
        "SELECT DISTINCT asset FROM signals",
        fetch="all",
    )
    assets = [r["asset"] for r in (rows or [])]

    results = {}
    for asset in assets:
        results[asset] = {
            "7d": db.get_signal_accuracy(asset, days=7),
            "30d": db.get_signal_accuracy(asset, days=30),
        }
    return {"accuracy": results}


@app.get("/api/calendar")
async def api_calendar(hours: int = Query(48)):
    events = get_upcoming_high_impact(hours=hours)
    for ev in events:
        ev.pop("_parsed_time", None)
    return {"hours": hours, "count": len(events), "events": events}


@app.get("/api/calendar/all")
async def api_calendar_all():
    events = get_this_week_events()
    return {"count": len(events), "events": events}


@app.get("/api/label-stats")
async def api_label_stats(asset: str = Query(None)):
    stats = get_label_stats(db, asset=asset)
    return {"asset": asset, "stats": stats}


@app.get("/api/model-info")
async def api_model_info(asset: str = Query("BTCUSDT")):
    model, meta = load_latest_model(asset)
    return {"asset": asset, "has_model": model is not None, "meta": meta}


@app.get("/api/cross-exchange")
async def api_cross_exchange(asset: str = Query("BTCUSDT")):
    data = db.get_cross_exchange_latest(asset)
    return {"asset": asset, "exchanges": data}


@app.get("/api/db-stats")
async def api_db_stats():
    stats = db.get_db_stats()
    return {"stats": stats}


if __name__ == "__main__":
    port = int(os.getenv("API_PORT", "8877"))
    print(f"Starting Trading Intelligence API on port {port}")
    print(f"Dashboard: http://localhost:{port}/dashboard/index.html")
    uvicorn.run(app, host="127.0.0.1", port=port)


"""
collector.py — Thu thập dữ liệu tự động mỗi giờ từ tất cả nguồn.

Nguồn dữ liệu:
1. Finnhub       → giá forex + tin tức
2. Binance       → funding rate, OI, long/short ratio
3. Bybit         → cross-exchange funding rate (free, không key)
4. Whale Alert   → giao dịch on-chain lớn (optional)
5. alternative.me → Fear & Greed Index (free, không key)
6. ForexFactory  → Economic calendar (free, không key)

Dữ liệu được ghi vào PostgreSQL (database.py).
Module này được main_bot.py gọi thông qua job_queue.
"""

import time
import logging
import requests
from datetime import datetime, timezone

from .database import CryptDB
from .data_provider import FinnhubClient
from .crypto_provider import BinanceFuturesClient, WhaleAlertClient
from .bybit_provider import BybitClient
from .economic_calendar import get_this_week_events

logger = logging.getLogger(__name__)

FEAR_GREED_URL = "https://api.alternative.me/fng/?limit=1"


_FG_CACHE = {'value': None, 'ts': 0}

def fetch_fear_greed() -> int | None:
    now = time.time()
    if _FG_CACHE['value'] is not None and (now - _FG_CACHE['ts']) < 300:
        return _FG_CACHE['value']
    """
    Lấy Fear & Greed Index từ alternative.me (crypto).
    Trả về int 0-100 hoặc None nếu lỗi.
    0 = Extreme Fear, 100 = Extreme Greed.
    """
    try:
        resp = requests.get(FEAR_GREED_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        value = int(data["data"][0]["value"])
        _FG_CACHE["value"] = value
        _FG_CACHE["ts"] = now
        return value
    except Exception as e:
        logger.warning(f"Error fetching Fear & Greed: {e}")
        return None


def fear_greed_label(value: int | None) -> str:
    """Chuyển giá trị Fear & Greed thành label mô tả."""
    if value is None:
        return "N/A"
    if value <= 25:
        return f"{value} (EXTREME FEAR)"
    elif value <= 40:
        return f"{value} (FEAR)"
    elif value <= 60:
        return f"{value} (NEUTRAL)"
    elif value <= 75:
        return f"{value} (GREED)"
    else:
        return f"{value} (EXTREME GREED)"


def collect_forex(
    db: CryptDB,
    finnhub: FinnhubClient,
    watchlist: list[str],
    fear_greed: int | None,
) -> dict:
    """Thu thập giá forex và ghi vào DB. Trả về dict prices."""
    prices = {}
    try:
        prices = finnhub.get_watchlist_prices(watchlist)
        for pair, info in prices.items():
            if "error" not in info:
                db.record_snapshot(
                    asset=pair.replace("OANDA:", ""),
                    price=info.get("price"),
                    fear_greed=fear_greed,
                )
        logger.info(f"Collected {len([p for p in prices.values() if 'error' not in p])} forex pairs")
    except Exception as e:
        logger.error(f"Error collect forex: {e}")
    return prices


def collect_crypto(
    db: CryptDB,
    binance: BinanceFuturesClient,
    symbols: list[str],
    fear_greed: int | None,
) -> dict[str, dict]:
    """Thu thập derivatives crypto và ghi vào DB. Trả về summaries."""
    summaries = {}
    for sym in symbols:
        try:
            summary = binance.get_summary(sym)
            summaries[sym] = summary

            # Extract data cho snapshot
            funding = summary.get("funding", {})
            oi = summary.get("oi_change_1h", {})
            ls = summary.get("long_short", {})

            db.record_snapshot(
                asset=sym,
                price=funding.get("mark_price"),
                funding_rate=funding.get("last_funding_rate"),
                oi_value=oi.get("oi_now") if oi else None,
                oi_change_1h=oi.get("oi_change_percent") if oi else None,
                long_ratio=ls.get("long_account_pct", 0) / 100 if ls else None,
                short_ratio=ls.get("short_account_pct", 0) / 100 if ls else None,
                fear_greed=fear_greed,
            )
            logger.info(f"Collected crypto: {sym}")
        except Exception as e:
            logger.error(f"Error collect crypto {sym}: {e}")
    return summaries


def collect_news(db: CryptDB, finnhub: FinnhubClient) -> list[dict]:
    """Thu thập tin tức và ghi vào DB."""
    items = []
    try:
        items = finnhub.get_forex_news(limit=15)
        for item in items:
            db.record_news(
                headline=item.get("headline", ""),
                source=item.get("source", ""),
                url=item.get("url", ""),
                timestamp=item.get("datetime", int(time.time())),
            )
        logger.info(f"Collected {len(items)} news items")
    except Exception as e:
        logger.error(f"Error collect news: {e}")
    return items


def collect_whale(db: CryptDB, whale: WhaleAlertClient | None) -> list[dict]:
    """Thu thập whale transactions và ghi vào DB."""
    txs = []
    if not whale:
        return txs
    try:
        result = whale.get_recent_transactions(min_value_usd=500000, minutes_back=120)
        if isinstance(result, list):
            txs = result
            for tx in txs:
                from_owner = tx.get("from", {}).get("owner") or tx.get("from", {}).get("owner_type", "unknown")
                to_owner = tx.get("to", {}).get("owner") or tx.get("to", {}).get("owner_type", "unknown")
                db.record_whale_tx(
                    symbol=tx.get("symbol", "?").upper(),
                    amount_usd=tx.get("amount_usd", 0),
                    from_type=from_owner,
                    to_type=to_owner,
                    tx_hash=tx.get("hash", ""),
                    timestamp=tx.get("timestamp", int(time.time())),
                )
            logger.info(f"Collected {len(txs)} whale transactions")
    except Exception as e:
        logger.error(f"Error collect whale: {e}")
    return txs


def collect_calendar(db: CryptDB) -> list[dict]:
    """Thu thập economic calendar và ghi vào DB."""
    events = []
    try:
        events = get_this_week_events()
        if events:
            db.record_calendar_events(events)
            logger.info(f"Collected {len(events)} calendar events")
    except Exception as e:
        logger.error(f"Error collect calendar: {e}")
    return events


def collect_bybit(
    db: CryptDB,
    bybit: BybitClient,
    symbols: list[str],
) -> int:
    """Thu thập cross-exchange funding rate từ Bybit."""
    count = 0
    for sym in symbols:
        try:
            data = bybit.get_funding_rate(sym)
            if data:
                db.record_cross_exchange_funding(
                    asset=sym,
                    exchange="bybit",
                    funding_rate=data.get("funding_rate"),
                    mark_price=data.get("mark_price"),
                    open_interest=data.get("open_interest"),
                    volume_24h=data.get("volume_24h"),
                )
                count += 1
        except Exception as e:
            logger.error(f"Error collect Bybit {sym}: {e}")
    if count > 0:
        logger.info(f"Collected Bybit funding for {count} symbols")
    return count


def collect_all(
    db: CryptDB,
    finnhub: FinnhubClient,
    binance: BinanceFuturesClient,
    whale: WhaleAlertClient | None,
    bybit: BybitClient | None,
    forex_watchlist: list[str],
    crypto_symbols: list[str],
) -> dict:
    """
    Thu thập TOÀN BỘ dữ liệu từ mọi nguồn và ghi vào DB.
    Gọi hàm này mỗi giờ từ main_bot.py job_queue.
    """
    logger.info("=== DATA COLLECTION START ===")
    start_time = time.time()

    # 1. Fear & Greed
    fear_greed = fetch_fear_greed()
    logger.info(f"Fear & Greed: {fear_greed_label(fear_greed)}")

    # 2. Forex
    prices = collect_forex(db, finnhub, forex_watchlist, fear_greed)

    # 3. Crypto derivatives (Binance)
    crypto_summaries = collect_crypto(db, binance, crypto_symbols, fear_greed)

    # 4. Cross-exchange funding (Bybit)
    bybit_count = 0
    if bybit:
        bybit_count = collect_bybit(db, bybit, crypto_symbols)

    # 5. News
    news = collect_news(db, finnhub)

    # 6. Whale (optional)
    whale_txs = collect_whale(db, whale)

    # 7. Calendar
    calendar_events = collect_calendar(db)

    elapsed = time.time() - start_time
    logger.info(f"=== DATA COLLECTION DONE ({elapsed:.1f}s) ===")

    # Record system metric
    try:
        db.record_metric("collection_time", elapsed)
    except Exception:
        pass

    return {
        "fear_greed": fear_greed,
        "forex_count": len([p for p in prices.values() if "error" not in p]),
        "crypto_count": len(crypto_summaries),
        "bybit_count": bybit_count,
        "news_count": len(news),
        "whale_count": len(whale_txs),
        "calendar_count": len(calendar_events),
        "elapsed_seconds": elapsed,
    }


# ─────────────── Alert Detection ───────────────

def check_volatility_alerts(
    db: CryptDB,
    binance: BinanceFuturesClient,
    forex_watchlist: list[str],
    crypto_symbols: list[str],
    threshold_price: float = 0.5,
    threshold_funding: float = 0.1,
    threshold_oi: float = 5.0,
    threshold_whale_usd: float = 50_000_000,
    cooldown_seconds: int = 1800,
) -> list[str]:
    """Kiểm tra biến động đột biến. Trả về danh sách alert messages."""
    alerts = []

    # 1. Forex price spike
    for pair in forex_watchlist:
        pair_key = pair.replace("OANDA:", "")
        alert_key = f"price_spike_{pair_key}"
        change_15m = db.get_price_change(pair_key, 900)
        if change_15m is not None and abs(change_15m) > threshold_price:
            if db.check_alert_cooldown(alert_key, cooldown_seconds):
                direction = "tang" if change_15m > 0 else "giam"
                alerts.append(
                    f"* {pair_key.replace('_', '/')} {direction} {change_15m:+.2f}% in 15m (threshold: {threshold_price}%)"
                )
                db.mark_alert_sent(alert_key)

    # 2. Funding rate extreme
    for sym in crypto_symbols:
        alert_key = f"funding_extreme_{sym}"
        snapshot = db.get_latest_snapshot(sym)
        if snapshot and snapshot.get("funding_rate") is not None:
            fr = snapshot["funding_rate"]
            if abs(fr) > threshold_funding:
                if db.check_alert_cooldown(alert_key, cooldown_seconds):
                    alerts.append(
                        f"* {sym} funding rate extreme: {fr:+.4f}% (threshold: +/-{threshold_funding}%)"
                    )
                    db.mark_alert_sent(alert_key)

    # 3. OI surge
    for sym in crypto_symbols:
        alert_key = f"oi_surge_{sym}"
        snapshot = db.get_latest_snapshot(sym)
        if snapshot and snapshot.get("oi_change_1h") is not None:
            oi_chg = snapshot["oi_change_1h"]
            if abs(oi_chg) > threshold_oi:
                if db.check_alert_cooldown(alert_key, cooldown_seconds):
                    direction = "up" if oi_chg > 0 else "down"
                    alerts.append(
                        f"* {sym} OI {direction} {abs(oi_chg):.1f}% in 1h (threshold: {threshold_oi}%)"
                    )
                    db.mark_alert_sent(alert_key)

    # 4. Whale alert
    recent_whales = db.get_recent_whale_txs(hours=1)
    for tx in recent_whales:
        if tx["amount_usd"] >= threshold_whale_usd:
            alert_key = f"whale_{tx.get('tx_hash', '')}"
            if db.check_alert_cooldown(alert_key, cooldown_seconds):
                alerts.append(
                    f"Whale: ${tx['amount_usd']:,.0f} {tx['symbol']} - {tx['from_type']} -> {tx['to_type']}"
                )
                db.mark_alert_sent(alert_key)

    return alerts

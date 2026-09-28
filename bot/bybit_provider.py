"""
bybit_provider.py — Lấy funding rate từ Bybit để so sánh cross-exchange.

Bybit Futures public API — KHÔNG cần API key.
Endpoint: https://api.bybit.com/v5/market/tickers?category=linear

Mục đích: So sánh funding rate Binance vs Bybit
→ Chênh lệch lớn = cơ hội funding arbitrage (không phải tín hiệu hướng giá)
"""

import requests
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

BYBIT_V5_BASE = "https://api.bybit.com/v5"


class BybitClient:
    """Bybit public API — không cần key."""

    def __init__(self):
        self.session = requests.Session()

    def get_funding_rate(self, symbol: str) -> dict | None:
        """
        Lấy funding rate hiện tại cho symbol (VD: BTCUSDT).
        Trả về dict hoặc None nếu lỗi.
        """
        try:
            url = f"{BYBIT_V5_BASE}/market/tickers"
            resp = self.session.get(
                url,
                params={"category": "linear", "symbol": symbol},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("retCode") != 0:
                logger.warning(f"Bybit API error: {data.get('retMsg')}")
                return None

            items = data.get("result", {}).get("list", [])
            if not items:
                return None

            item = items[0]
            return {
                "symbol": symbol,
                "funding_rate": float(item.get("fundingRate", 0)) * 100,  # %
                "mark_price": float(item.get("markPrice", 0)),
                "last_price": float(item.get("lastPrice", 0)),
                "open_interest": float(item.get("openInterest", 0)),
                "volume_24h": float(item.get("volume24h", 0)),
            }

        except Exception as e:
            logger.warning(f"Lỗi lấy Bybit funding {symbol}: {e}")
            return None

    def get_funding_history(self, symbol: str, limit: int = 20) -> list[dict]:
        """Lấy lịch sử funding rate."""
        try:
            url = f"{BYBIT_V5_BASE}/market/funding/history"
            resp = self.session.get(
                url,
                params={"category": "linear", "symbol": symbol, "limit": limit},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("retCode") != 0:
                return []

            items = data.get("result", {}).get("list", [])
            return [
                {
                    "symbol": symbol,
                    "funding_rate": float(item.get("fundingRate", 0)) * 100,
                    "timestamp": int(item.get("fundingRateTimestamp", 0)) // 1000,
                }
                for item in items
            ]

        except Exception as e:
            logger.warning(f"Lỗi lấy Bybit funding history {symbol}: {e}")
            return []


def compare_funding_rates(binance_rate: float | None, bybit_data: dict | None) -> dict | None:
    """
    So sánh funding rate Binance vs Bybit.
    Trả về dict chênh lệch hoặc None.
    """
    if binance_rate is None or bybit_data is None:
        return None

    bybit_rate = bybit_data.get("funding_rate")
    if bybit_rate is None:
        return None

    diff = abs(binance_rate - bybit_rate)
    higher = "Binance" if binance_rate > bybit_rate else "Bybit"

    return {
        "binance_rate": binance_rate,
        "bybit_rate": bybit_rate,
        "difference": diff,
        "higher_exchange": higher,
        "is_significant": diff > 0.02,  # Chênh lệch > 0.02% coi là đáng chú ý
    }


def format_cross_exchange_telegram(symbol: str, comparison: dict) -> str:
    """Format so sánh cross-exchange cho Telegram."""
    if not comparison:
        return f"⚡ {symbol}: Không có dữ liệu cross-exchange"

    binance = comparison["binance_rate"]
    bybit = comparison["bybit_rate"]
    diff = comparison["difference"]

    lines = [
        f"⚡ *CHÊNH LỆCH FUNDING RATE ({symbol}):*",
        f"• Binance: {binance:+.4f}%",
        f"• Bybit:   {bybit:+.4f}%",
        f"Chênh lệch: {diff:.4f}%",
    ]

    if comparison["is_significant"]:
        lines.append(f"⚠️ Chênh lệch đáng chú ý — {comparison['higher_exchange']} funding cao hơn")

    lines.append("\nℹ️ Chênh lệch funding cross-exchange ≠ tín hiệu hướng giá.")

    return "\n".join(lines)

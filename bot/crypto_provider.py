"""
crypto_provider.py
Lấy dữ liệu derivatives crypto (funding rate, open interest) từ Binance Futures
public API (KHÔNG cần API key) và giao dịch on-chain lớn từ Whale Alert (cần key free).

QUAN TRỌNG VỀ GIỚI HẠN: Dữ liệu này phản ánh trạng thái thị trường hiện tại
(thiên hướng đòn bẩy long/short, dòng tiền lớn di chuyển), KHÔNG phải dự đoán
giá tương lai. Funding rate dương cao = phe long đang trả phí cho phe short
(nhiều người đang long bằng đòn bẩy) - đây là dữ liệu về VỊ THẾ hiện tại,
không phải tín hiệu mua/bán.
"""

import time
import requests
from datetime import datetime, timezone

BINANCE_FAPI = "https://fapi.binance.com"
WHALE_ALERT_BASE = "https://api.whale-alert.io/v1"


class BinanceFuturesClient:
    """Không cần API key cho các endpoint market data public này."""

    def __init__(self):
        self.session = requests.Session()

    def get_funding_rate(self, symbol: str):
        """symbol dạng 'BTCUSDT'. Trả funding rate hiện tại + giá mark."""
        url = f"{BINANCE_FAPI}/fapi/v1/premiumIndex"
        resp = self.session.get(url, params={"symbol": symbol}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return {
            "symbol": symbol,
            "mark_price": float(data["markPrice"]),
            "last_funding_rate": float(data["lastFundingRate"]) * 100,  # %
            "next_funding_time": datetime.fromtimestamp(
                int(data["nextFundingTime"]) / 1000, tz=timezone.utc
            ).isoformat(),
        }

    def get_open_interest(self, symbol: str):
        """OI hiện tại (số lượng hợp đồng)."""
        url = f"{BINANCE_FAPI}/fapi/v1/openInterest"
        resp = self.session.get(url, params={"symbol": symbol}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return {
            "symbol": symbol,
            "open_interest": float(data["openInterest"]),
            "timestamp": datetime.fromtimestamp(int(data["time"]) / 1000, tz=timezone.utc).isoformat(),
        }

    def get_open_interest_change(self, symbol: str, period: str = "1h", limit: int = 2):
        """
        So sánh OI hiện tại với cách đây 1 kỳ, để biết OI đang tăng/giảm.
        period: 5m,15m,30m,1h,2h,4h,6h,12h,1d
        """
        url = f"{BINANCE_FAPI}/futures/data/openInterestHist"
        resp = self.session.get(
            url, params={"symbol": symbol, "period": period, "limit": limit}, timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        if len(data) < 2:
            return None
        oldest = float(data[0]["sumOpenInterest"])
        newest = float(data[-1]["sumOpenInterest"])
        if oldest == 0:
            return None
        pct_change = (newest - oldest) / oldest * 100
        return {
            "symbol": symbol,
            "period": period,
            "oi_change_percent": pct_change,
            "oi_now": newest,
            "oi_before": oldest,
        }

    def get_long_short_ratio(self, symbol: str, period: str = "1h"):
        """Tỷ lệ tài khoản long/short (toàn thị trường top trader). Phản ánh thiên hướng vị thế."""
        url = f"{BINANCE_FAPI}/futures/data/globalLongShortAccountRatio"
        resp = self.session.get(url, params={"symbol": symbol, "period": period, "limit": 1}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return None
        d = data[-1]
        return {
            "symbol": symbol,
            "long_account_pct": float(d["longAccount"]) * 100,
            "short_account_pct": float(d["shortAccount"]) * 100,
            "long_short_ratio": float(d["longShortRatio"]),
        }

    def get_summary(self, symbol: str):
        """Tổng hợp tất cả chỉ số derivatives cho 1 symbol."""
        out = {"symbol": symbol}
        try:
            out["funding"] = self.get_funding_rate(symbol)
        except Exception as e:
            out["funding_error"] = str(e)
        try:
            out["oi_change_1h"] = self.get_open_interest_change(symbol, "1h")
        except Exception as e:
            out["oi_error"] = str(e)
        try:
            out["long_short"] = self.get_long_short_ratio(symbol, "1h")
        except Exception as e:
            out["ls_error"] = str(e)
        return out


class WhaleAlertClient:
    """Cần API key free (giới hạn số request) tại https://whale-alert.io/ -> API tab."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()

    def get_recent_transactions(self, min_value_usd: int = 500000, minutes_back: int = 60):
        if not self.api_key:
            return {"error": "Chưa cấu hình WHALE_ALERT_API_KEY"}
        start = int(time.time()) - minutes_back * 60
        url = f"{WHALE_ALERT_BASE}/transactions"
        params = {
            "api_key": self.api_key,
            "min_value": min_value_usd,
            "start": start,
        }
        resp = self.session.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("transactions", [])


def format_whale_tx(tx: dict) -> str:
    symbol = tx.get("symbol", "?").upper()
    amount_usd = tx.get("amount_usd", 0)
    from_owner = tx.get("from", {}).get("owner") or tx.get("from", {}).get("owner_type", "ví ẩn danh")
    to_owner = tx.get("to", {}).get("owner") or tx.get("to", {}).get("owner_type", "ví ẩn danh")
    ts = datetime.fromtimestamp(tx.get("timestamp", 0), tz=timezone.utc)
    return (
        f"• [{ts.strftime('%d/%m %H:%M UTC')}] {amount_usd:,.0f} USD {symbol}: "
        f"{from_owner} → {to_owner}"
    )


def build_text_summary(symbol: str, derivatives_summary: dict, news_sentiment_hint: str | None = None) -> str:
    """
    Tạo tóm tắt bằng lời mô tả TRẠNG THÁI dữ liệu hiện tại.
    KHÔNG đưa ra khuyến nghị mua/bán, không gợi ý entry/SL/TP.
    """
    lines = [f"Tóm tắt trạng thái thị trường {symbol}:"]

    funding = derivatives_summary.get("funding")
    if funding:
        fr = funding["last_funding_rate"]
        if fr > 0.03:
            fr_desc = "dương cao (phe long đang phải trả phí lớn cho phe short)"
        elif fr > 0:
            fr_desc = "dương nhẹ"
        elif fr < -0.03:
            fr_desc = "âm cao (phe short đang phải trả phí lớn cho phe long)"
        elif fr < 0:
            fr_desc = "âm nhẹ"
        else:
            fr_desc = "gần 0"
        lines.append(f"- Funding rate: {fr:.4f}% — {fr_desc}.")

    oi = derivatives_summary.get("oi_change_1h")
    if oi:
        chg = oi["oi_change_percent"]
        direction = "tăng" if chg > 0 else "giảm" if chg < 0 else "không đổi"
        lines.append(f"- Open Interest 1h qua: {direction} {abs(chg):.2f}% (tổng vị thế mở đang {direction}).")

    ls = derivatives_summary.get("long_short")
    if ls:
        lines.append(
            f"- Tỷ lệ tài khoản: {ls['long_account_pct']:.1f}% long / "
            f"{ls['short_account_pct']:.1f}% short (long/short ratio: {ls['long_short_ratio']:.2f})."
        )

    if news_sentiment_hint:
        lines.append(f"- Tin tức gần đây: {news_sentiment_hint}")

    lines.append(
        "\n⚠️ Đây là mô tả dữ liệu hiện tại (vị thế, dòng tiền), KHÔNG phải dự đoán giá. "
        "Funding/OI/long-short cao hay thấp không tự nó nói trước hướng giá tiếp theo."
    )
    return "\n".join(lines)

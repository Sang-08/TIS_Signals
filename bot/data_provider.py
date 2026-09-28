"""
data_provider.py
Lớp xử lý lấy dữ liệu từ Finnhub: giá forex hiện tại + tin tức thị trường.
Không đưa ra dự đoán "đúng/sai" về xu hướng - chỉ tổng hợp dữ liệu thô + chỉ báo
kỹ thuật cơ bản để người dùng tự tham khảo.

THAY ĐỔI TỪ PHIÊN BẢN CŨ:
- Lịch sử giá chuyển sang SQLite (database.py) thay vì file JSON
- get_change_over() query từ SQLite
- Xóa _load_history / _save_history / price_history.json
"""

import time
import requests
from datetime import datetime, timezone

FINNHUB_BASE = "https://finnhub.io/api/v1"


def _pair_to_finnhub_symbol(pair: str) -> str:
    """Chuyển 'EUR_USD' hoặc 'EURUSD' hoặc 'OANDA:EUR_USD' về dạng chuẩn OANDA:XXX_YYY"""
    p = pair.upper().replace("OANDA:", "").replace("/", "_")
    if "_" not in p and len(p) == 6:
        p = p[:3] + "_" + p[3:]
    return f"OANDA:{p}"


def _base_quote(pair: str):
    p = pair.upper().replace("OANDA:", "").replace("/", "_")
    if "_" in p:
        base, quote = p.split("_")
    else:
        base, quote = p[:3], p[3:]
    return base, quote


class FinnhubClient:
    def __init__(self, api_key: str, db=None):
        """
        Args:
            api_key: Finnhub API key
            db: CryptDB instance (optional) — nếu có, ghi lịch sử vào SQLite
        """
        if not api_key:
            raise ValueError("Thiếu FINNHUB_API_KEY. Hãy tạo key free tại https://finnhub.io/register")
        self.api_key = api_key
        self.session = requests.Session()
        self.db = db

    # ---------- Giá hiện tại ----------
    def get_all_rates(self, base: str = "USD"):
        """Gọi /forex/rates - trả tỷ giá hiện tại của tất cả cặp theo base currency."""
        url = f"{FINNHUB_BASE}/forex/rates"
        resp = self.session.get(url, params={"base": base, "token": self.api_key}, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def get_watchlist_prices(self, watchlist: list[str]):
        """
        Lấy giá hiện tại cho danh sách cặp theo dõi.
        Trả về dict: { 'EUR_USD': {'price': 1.0856, 'change_1h': 0.12, 'change_24h': -0.34}, ... }
        """
        results = {}
        rates_cache = {}

        for pair in watchlist:
            symbol = _pair_to_finnhub_symbol(pair)
            base, quote = _base_quote(symbol)

            if base not in rates_cache:
                try:
                    rates_cache[base] = self.get_all_rates(base=base)
                except requests.HTTPError as e:
                    results[pair] = {"error": f"Lỗi gọi API cho {base}: {e}"}
                    continue
                except Exception as e:
                    results[pair] = {"error": f"Lỗi không xác định: {e}"}
                    continue

            quotes = rates_cache[base].get("quote", {})
            price = quotes.get(quote)

            if price is None:
                results[pair] = {"error": f"Không tìm thấy giá cho {symbol}"}
                continue

            pair_key = f"{base}_{quote}"

            # Ghi vào SQLite nếu có DB
            if self.db:
                self.db.record_snapshot(asset=pair_key, price=price)

            # Tính % thay đổi từ SQLite
            change_1h = None
            change_24h = None
            if self.db:
                change_1h = self.db.get_price_change(pair_key, 3600)
                change_24h = self.db.get_price_change(pair_key, 86400)

            results[pair] = {
                "symbol": f"{base}/{quote}",
                "price": price,
                "change_1h": change_1h,
                "change_24h": change_24h,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        return results

    # ---------- Tin tức ----------
    def get_forex_news(self, limit: int = 8):
        """Gọi /news?category=forex - tin tức thị trường forex mới nhất."""
        url = f"{FINNHUB_BASE}/news"
        resp = self.session.get(url, params={"category": "forex", "token": self.api_key}, timeout=10)
        resp.raise_for_status()
        items = resp.json()
        items = sorted(items, key=lambda x: x.get("datetime", 0), reverse=True)
        return items[:limit]

    def get_general_news(self, limit: int = 8):
        """Tin tức tài chính tổng quát (category=general), dùng làm bổ sung."""
        url = f"{FINNHUB_BASE}/news"
        resp = self.session.get(url, params={"category": "general", "token": self.api_key}, timeout=10)
        resp.raise_for_status()
        items = resp.json()
        items = sorted(items, key=lambda x: x.get("datetime", 0), reverse=True)
        return items[:limit]


def format_news_item(item: dict) -> str:
    ts = datetime.fromtimestamp(item.get("datetime", 0), tz=timezone.utc)
    headline = item.get("headline", "Không có tiêu đề")
    source = item.get("source", "?")
    url = item.get("url", "")
    return f"• [{ts.strftime('%d/%m %H:%M UTC')}] ({source}) {headline}\n  {url}"

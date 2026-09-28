"""
economic_calendar.py — Lấy lịch sự kiện vĩ mô từ ForexFactory.

Nguồn: https://nfs.faireconomy.media/ff_calendar_thisweek.json
- Không cần API key
- Data JSON sạch: {title, country, date, impact, forecast, previous}
- Cập nhật tự động theo tuần

Impact levels: High (🔴), Medium (🟠), Low (⚪)
"""

import logging
import requests
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

FF_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

IMPACT_ICONS = {
    "High": "🔴",
    "Medium": "🟠",
    "Low": "⚪",
}

# Flag quốc gia
COUNTRY_FLAGS = {
    "USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧", "JPY": "🇯🇵",
    "AUD": "🇦🇺", "CAD": "🇨🇦", "CHF": "🇨🇭", "NZD": "🇳🇿",
    "CNY": "🇨🇳", "All": "🌐",
}


def get_this_week_events() -> list[dict]:
    """Fetch toàn bộ sự kiện trong tuần từ ForexFactory."""
    try:
        resp = requests.get(FF_CALENDAR_URL, timeout=15)
        resp.raise_for_status()
        events = resp.json()
        # Chuẩn hóa: đảm bảo mỗi event có các field cần thiết
        for ev in events:
            ev.setdefault("impact", "Low")
            ev.setdefault("forecast", "")
            ev.setdefault("previous", "")
            ev.setdefault("country", "")
            ev.setdefault("title", "")
            ev.setdefault("date", "")
        return events
    except Exception as e:
        logger.warning("Error fetching ForexFactory calendar: %s", e)
        return []


def get_upcoming_high_impact(hours: int = 48) -> list[dict]:
    """Lọc sự kiện High/Medium impact sắp tới trong N giờ."""
    events = get_this_week_events()
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=hours)

    upcoming = []
    for ev in events:
        if ev["impact"] not in ("High", "Medium"):
            continue
        try:
            # ForexFactory date format: "2026-09-14T08:30:00-04:00"
            ev_time = datetime.fromisoformat(ev["date"])
            if now <= ev_time <= cutoff:
                ev["_parsed_time"] = ev_time
                upcoming.append(ev)
        except (ValueError, KeyError):
            continue

    upcoming.sort(key=lambda x: x.get("_parsed_time", now))
    return upcoming


def get_events_by_currency(currency: str) -> list[dict]:
    """Lọc sự kiện theo đồng tiền (USD, EUR, GBP...)."""
    events = get_this_week_events()
    currency = currency.upper()
    return [ev for ev in events if ev.get("country", "").upper() == currency]


def hours_to_next_high_event() -> float | None:
    """
    Trả về số giờ đến sự kiện High impact tiếp theo.
    Dùng làm feature cho ML model (spec: hours_to_event).
    None nếu không có sự kiện nào sắp tới.
    """
    events = get_this_week_events()
    now = datetime.now(timezone.utc)

    for ev in events:
        if ev.get("impact") != "High":
            continue
        try:
            ev_time = datetime.fromisoformat(ev["date"])
            if ev_time > now:
                delta = (ev_time - now).total_seconds() / 3600
                return round(delta, 1)
        except (ValueError, KeyError):
            continue
    return None


def format_calendar_event(ev: dict) -> str:
    """Format 1 sự kiện cho Telegram."""
    impact_icon = IMPACT_ICONS.get(ev.get("impact", "Low"), "⚪")
    flag = COUNTRY_FLAGS.get(ev.get("country", ""), "")
    title = ev.get("title", "?")
    country = ev.get("country", "?")
    forecast = ev.get("forecast", "")
    previous = ev.get("previous", "")

    try:
        ev_time = datetime.fromisoformat(ev["date"])
        time_str = ev_time.strftime("%d/%m %H:%M UTC%z")
        # Tính còn bao lâu
        now = datetime.now(timezone.utc)
        delta = ev_time - now
        if delta.total_seconds() > 0:
            hours_left = delta.total_seconds() / 3600
            if hours_left < 1:
                time_left = f"({int(delta.total_seconds() / 60)} phút nữa)"
            elif hours_left < 24:
                time_left = f"({hours_left:.1f}h nữa)"
            else:
                days_left = hours_left / 24
                time_left = f"({days_left:.1f} ngày nữa)"
        else:
            time_left = "(đã qua)"
    except (ValueError, KeyError):
        time_str = ev.get("date", "?")
        time_left = ""

    line = f"{impact_icon} {flag} {time_str} {time_left}\n"
    line += f"   {country} — {title}"
    if forecast:
        line += f"\n   Dự báo: {forecast}"
        if previous:
            line += f" | Trước: {previous}"
    elif previous:
        line += f"\n   Trước: {previous}"

    return line


def format_calendar_block(events: list[dict], title: str = "📅 Sự kiện vĩ mô sắp tới") -> str:
    """Format danh sách sự kiện thành block cho Telegram."""
    if not events:
        return f"{title}\n\nKhông có sự kiện nào."

    lines = [title, ""]
    for ev in events:
        lines.append(format_calendar_event(ev))
        lines.append("")  # dòng trống giữa các event

    return "\n".join(lines)

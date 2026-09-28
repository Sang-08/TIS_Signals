"""
backtest.py — Theo dõi accuracy signal theo thời gian thực.

Chạy mỗi giờ:
1. Kiểm tra signals đã gửi >= 4h trước và chưa có outcome
2. So sánh hướng signal với giá thực tế
3. Lưu outcome: CORRECT / WRONG
4. Tính rolling win rate: 7 ngày, 30 ngày

Lệnh /accuracy — Output mẫu (spec):
  MODEL ACCURACY (live tracking)
  BTC: 7d: 61.4% (27/44) | 30d: 58.2% (89/153)
  Warning: Win rate < 55% in 7d -> model needs improvement
"""

import time
import logging

from .database import CryptDB

logger = logging.getLogger(__name__)

# Ngưỡng % thay đổi để signal đúng/sai
THRESHOLD_PERCENT = 0.3  # Khớp với labeler.py
# Sau bao lâu kiểm tra outcome (giờ)
CHECK_AFTER_HOURS = 4.0


def _get_price_at(db: CryptDB, asset: str, target_ts: int) -> float | None:
    """Helper: lấy giá gần nhất trước hoặc tại target_ts."""
    row = db._execute(
        """SELECT price FROM snapshots
           WHERE asset = %s AND timestamp <= %s AND price IS NOT NULL
           ORDER BY timestamp DESC LIMIT 1""",
        (asset, target_ts), fetch="one",
    )
    return row["price"] if row else None


def check_signal_outcomes(db: CryptDB) -> dict:
    """
    Kiểm tra tất cả signals chưa có outcome và đã qua >= 4h.
    So sánh direction với giá thực tế.

    Returns:
        dict: {"checked": N, "correct": N, "wrong": N, "skipped": N}
    """
    unchecked = db.get_unchecked_signals(older_than_hours=CHECK_AFTER_HOURS)

    stats = {"checked": 0, "correct": 0, "wrong": 0, "skipped": 0}

    for sig in unchecked:
        asset = sig["asset"]
        sig_ts = sig["timestamp"]
        direction = sig["direction"]

        if direction == "SIDEWAYS":
            db.update_signal_outcome(sig["id"], "SIDEWAYS")
            stats["skipped"] += 1
            continue

        # Lấy giá lúc signal
        price_start = _get_price_at(db, asset, sig_ts)
        if not price_start:
            stats["skipped"] += 1
            continue

        # Lấy giá 4h sau signal
        target_ts = sig_ts + int(CHECK_AFTER_HOURS * 3600)
        price_end = _get_price_at(db, asset, target_ts)
        if not price_end:
            stats["skipped"] += 1
            continue

        if price_start == 0:
            stats["skipped"] += 1
            continue

        pct_change = (price_end - price_start) / price_start * 100

        # Kiểm tra outcome
        if direction == "UP":
            outcome = "CORRECT" if pct_change > THRESHOLD_PERCENT else "WRONG"
        elif direction == "DOWN":
            outcome = "CORRECT" if pct_change < -THRESHOLD_PERCENT else "WRONG"
        else:
            stats["skipped"] += 1
            continue

        db.update_signal_outcome(sig["id"], outcome)
        stats["checked"] += 1
        stats[outcome.lower()] += 1

    if stats["checked"] > 0:
        logger.info(
            f"Checked {stats['checked']} signals: "
            f"correct={stats['correct']}, wrong={stats['wrong']}, "
            f"skipped={stats['skipped']}"
        )

    return stats


def format_accuracy_telegram(db: CryptDB, assets: list[str]) -> str:
    """Format accuracy cho Telegram."""
    lines = ["*MODEL ACCURACY* (live tracking)", ""]

    has_data = False
    for asset in assets:
        stats_7d = db.get_signal_accuracy(asset, days=7)
        stats_30d = db.get_signal_accuracy(asset, days=30)

        if stats_7d["total"] == 0 and stats_30d["total"] == 0:
            lines.append(f"  {asset}: no checked signals yet")
            continue

        has_data = True
        parts = []
        if stats_7d["total"] > 0:
            parts.append(
                f"7d: {stats_7d['win_rate']:.1f}% "
                f"({stats_7d['correct']}/{stats_7d['total']})"
            )
        if stats_30d["total"] > 0:
            parts.append(
                f"30d: {stats_30d['win_rate']:.1f}% "
                f"({stats_30d['correct']}/{stats_30d['total']})"
            )

        lines.append(f"  {asset}: {' | '.join(parts)}")

        if stats_7d["total"] >= 5 and stats_7d["win_rate"] < 55:
            lines.append(f"  Warning: Win rate < 55% in 7d - model needs improvement")

    if not has_data:
        lines.append("Not enough signal data to calculate accuracy.")
        lines.append("Model needs a few weeks of data collection first.")

    lines.append("")
    lines.append("Win rate > 60% + good risk/reward = real edge.")

    return "\n".join(lines)

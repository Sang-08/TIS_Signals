"""
labeler.py — Gán nhãn UP/DOWN/SIDEWAYS cho snapshots đã qua 4h.

Chạy mỗi giờ (qua main_bot.py job_queue):
1. Tìm snapshots có timestamp <= now - 4h và label IS NULL
2. So sánh price lúc snapshot vs price hiện tại gần nhất
3. UP: tăng > 0.3%
4. DOWN: giảm > 0.3%
5. SIDEWAYS: dao động trong +/-0.3%
6. Ghi label + price_4h_later vào database

Cần: ít nhất vài ngày dữ liệu từ collector.py trước khi có đủ labels.
"""

import time
import logging

from .database import CryptDB

logger = logging.getLogger(__name__)

# Ngưỡng % thay đổi để phân loại
THRESHOLD_PERCENT = 0.3  # spec: UP > +0.3%, DOWN < -0.3%, SIDEWAYS trong +/-0.3%


def find_price_at_time(db: CryptDB, asset: str, target_ts: int) -> float | None:
    """
    Tìm giá gần nhất với thời điểm target_ts cho asset.
    Ưu tiên snapshot gần nhất TRƯỚC target_ts.
    """
    # Tìm snapshot gần nhất trước hoặc tại target_ts
    row = db._execute(
        """SELECT price FROM snapshots
           WHERE asset = %s AND timestamp <= %s AND price IS NOT NULL
           ORDER BY timestamp DESC LIMIT 1""",
        (asset, target_ts), fetch="one",
    )
    if row:
        return row["price"]

    # Nếu không có, tìm snapshot gần nhất SAU target_ts
    row = db._execute(
        """SELECT price FROM snapshots
           WHERE asset = %s AND timestamp >= %s AND price IS NOT NULL
           ORDER BY timestamp ASC LIMIT 1""",
        (asset, target_ts), fetch="one",
    )
    return row["price"] if row else None


def label_snapshots(db: CryptDB, hours_later: float = 4.0, threshold: float = THRESHOLD_PERCENT) -> dict:
    """
    Gán nhãn cho tất cả snapshots chưa có label và đã qua >= hours_later.

    Returns:
        dict: {"labeled": N, "up": N, "down": N, "sideways": N, "skipped": N}
    """
    unlabeled = db.get_unlabeled_snapshots(older_than_hours=hours_later)

    stats = {"labeled": 0, "up": 0, "down": 0, "sideways": 0, "skipped": 0}

    if not unlabeled:
        return stats

    for snap in unlabeled:
        asset = snap["asset"]
        snap_ts = snap["timestamp"]
        snap_price = snap["price"]

        if snap_price is None or snap_price == 0:
            stats["skipped"] += 1
            continue

        # Tìm giá 4h sau snapshot
        target_ts = snap_ts + int(hours_later * 3600)
        price_later = find_price_at_time(db, asset, target_ts)

        if price_later is None:
            stats["skipped"] += 1
            continue

        # Tính % thay đổi
        pct_change = (price_later - snap_price) / snap_price * 100

        # Gán nhãn
        if pct_change > threshold:
            label = "UP"
            stats["up"] += 1
        elif pct_change < -threshold:
            label = "DOWN"
            stats["down"] += 1
        else:
            label = "SIDEWAYS"
            stats["sideways"] += 1

        db.label_snapshot(snap["id"], label, price_later)
        stats["labeled"] += 1

    if stats["labeled"] > 0:
        logger.info(
            f"Labeled {stats['labeled']} snapshots: "
            f"UP={stats['up']}, DOWN={stats['down']}, SIDEWAYS={stats['sideways']}, "
            f"skipped={stats['skipped']}"
        )

    return stats


def get_label_stats(db: CryptDB, asset: str | None = None) -> dict:
    """
    Thống kê labels hiện có trong DB.
    Dùng để kiểm tra tiến độ thu thập dữ liệu.
    """
    if asset:
        rows = db._execute(
            """SELECT label, COUNT(*) as cnt FROM snapshots
               WHERE asset = %s AND label IS NOT NULL GROUP BY label""",
            (asset,), fetch="all",
        )
        unlabeled_row = db._execute(
            "SELECT COUNT(*) as cnt FROM snapshots WHERE asset = %s AND label IS NULL",
            (asset,), fetch="one",
        )
    else:
        rows = db._execute(
            "SELECT label, COUNT(*) as cnt FROM snapshots WHERE label IS NOT NULL GROUP BY label",
            fetch="all",
        )
        unlabeled_row = db._execute(
            "SELECT COUNT(*) as cnt FROM snapshots WHERE label IS NULL",
            fetch="one",
        )

    stats = {r["label"]: r["cnt"] for r in (rows or [])}
    stats["total_labeled"] = sum(stats.values())
    stats["unlabeled"] = unlabeled_row["cnt"] if unlabeled_row else 0
    return stats

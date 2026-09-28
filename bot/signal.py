"""
signal.py — Tạo gợi ý lệnh khi xác suất > ngưỡng.

Quy trình:
1. Lấy snapshot hiện tại của asset
2. Extract features (giống trainer.py)
3. Load model mới nhất
4. Predict: UP/DOWN/SIDEWAYS + probability
5. Nếu probability >= SIGNAL_THRESHOLD -> tạo signal
6. Lưu signal vào DB + gửi Telegram
"""

import json
import time
import logging
from datetime import datetime, timezone

import numpy as np

from .database import CryptDB
from .trainer import extract_features, load_latest_model, FEATURE_NAMES

logger = logging.getLogger(__name__)

SIGNAL_THRESHOLD = 0.65  # 65%

DIRECTION_MAP = {
    "UP": ("LONG", "📈"),
    "DOWN": ("SHORT", "📉"),
    "SIDEWAYS": ("SIDEWAY", "➡️"),
}


def generate_signal(db: CryptDB, asset: str) -> dict | None:
    model, meta = load_latest_model(asset)
    if model is None:
        return {"error": f"No model for {asset}. Need data collection and training first."}

    snapshot = db.get_latest_snapshot(asset)
    if not snapshot:
        return {"error": f"No snapshot data for {asset}."}

    features = extract_features(snapshot)
    if features is None:
        return {"error": f"Missing derivatives data for {asset} (need funding/OI/long-short)."}

    X = np.array([features])
    prediction = model.predict(X)[0]
    probabilities = model.predict_proba(X)[0]

    classes = model.classes_.tolist()
    pred_idx = classes.index(prediction)
    confidence = probabilities[pred_idx]

    similar_stats = find_similar_patterns(db, asset, snapshot)

    signal_info = {
        "asset": asset,
        "direction": prediction,
        "probability": round(confidence * 100, 1),
        "threshold": SIGNAL_THRESHOLD * 100,
        "triggered": confidence >= SIGNAL_THRESHOLD and prediction != "SIDEWAYS",
        "features": dict(zip(FEATURE_NAMES, features)),
        "all_probabilities": dict(zip(classes, [round(p * 100, 1) for p in probabilities])),
        "similar_patterns": similar_stats,
        "model_meta": meta,
        "timestamp": int(time.time()),
    }

    if signal_info["triggered"]:
        db.record_signal(
            asset=asset,
            direction=prediction,
            probability=confidence,
            features_json=json.dumps(signal_info["features"]),
        )
        logger.info(f"Signal triggered: {asset} -> {prediction} ({confidence*100:.1f}%)")

    return signal_info


def find_similar_patterns(db: CryptDB, asset: str, current_snapshot: dict) -> dict:
    labeled = db.get_labeled_data(asset=asset)
    if not labeled:
        return {"found": 0, "total": 0}

    current_features = extract_features(current_snapshot)
    if current_features is None:
        return {"found": 0, "total": 0}

    similar_count = 0
    label_counts = {"UP": 0, "DOWN": 0, "SIDEWAYS": 0}

    for snap in labeled:
        hist_features = extract_features(snap)
        if hist_features is None:
            continue

        dist = np.sqrt(sum((a - b) ** 2 for a, b in zip(current_features, hist_features)))
        if dist < 1.5:
            similar_count += 1
            label = snap["label"]
            label_counts[label] = label_counts.get(label, 0) + 1

    return {
        "found": similar_count,
        "total": len(labeled),
        "breakdown": label_counts,
    }


def format_signal_telegram(signal_info: dict) -> str:
    if "error" in signal_info:
        return f"Warning: {signal_info['error']}"

    asset = signal_info["asset"]
    direction = signal_info["direction"]
    dir_text, dir_icon = DIRECTION_MAP.get(direction, (direction, "?"))
    prob = signal_info["probability"]
    threshold = signal_info["threshold"]
    triggered = signal_info["triggered"]
    features = signal_info["features"]
    similar = signal_info["similar_patterns"]
    meta = signal_info.get("model_meta", {})

    now_str = datetime.now(timezone.utc).strftime("%H:%M UTC")

    lines = [f"{dir_icon} *SIGNAL {asset}* - {now_str}", ""]

    lines.append(f"Direction: *{dir_text}*")
    lines.append(f"Model probability: *{prob}%*")
    check = "YES" if triggered else "NO"
    lines.append(f"Threshold: {threshold}% [{check}]")
    lines.append("")

    lines.append("*Input data:*")
    if features.get("funding_rate"):
        fr = features["funding_rate"]
        lines.append(f"  Funding: {fr:+.4f}%")
    if features.get("oi_change_1h"):
        lines.append(f"  OI 1h: {features['oi_change_1h']:+.2f}%")
    if features.get("long_ratio"):
        lr = features["long_ratio"]
        lines.append(f"  L/S ratio: {lr / (1-lr) if lr < 1 else 99:.2f} ({lr*100:.0f}% long)")
    if features.get("fear_greed"):
        fg = int(features["fear_greed"] * 100)
        fg_label = "Extreme Fear" if fg <= 25 else "Fear" if fg <= 40 else "Neutral" if fg <= 60 else "Greed" if fg <= 75 else "Extreme Greed"
        lines.append(f"  Fear & Greed: {fg} ({fg_label})")
    lines.append("")

    if similar["found"] > 0:
        lines.append("*Similar patterns in history:*")
        lines.append(f"Found {similar['found']} in {similar['total']} data points")
        bd = similar.get("breakdown", {})
        total_similar = similar["found"]
        if total_similar > 0:
            for label in ["UP", "DOWN", "SIDEWAYS"]:
                cnt = bd.get(label, 0)
                pct = cnt / total_similar * 100
                lines.append(f"  {label}: {cnt}/{total_similar} ({pct:.0f}%)")
        lines.append("")

    warning = meta.get("warning", "") if meta else ""
    lines.append("This is a statistical pattern suggestion, NOT financial advice.")
    lines.append("You decide your own trades.")
    if warning:
        lines.append(f"   {warning}")

    return "\n".join(lines)


def format_signal_brief(signal_info: dict) -> str:
    if "error" in signal_info:
        return ""
    if not signal_info.get("triggered"):
        return ""

    asset = signal_info["asset"]
    direction = signal_info["direction"]
    _, dir_icon = DIRECTION_MAP.get(direction, (direction, "?"))
    prob = signal_info["probability"]

    return f"{dir_icon} {asset}: {direction} ({prob}%)"

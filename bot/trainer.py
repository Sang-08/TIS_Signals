"""
trainer.py — Train Random Forest model hàng ngày lúc 00:00 UTC.

Features (input):
- funding_rate, oi_change_1h, long_ratio
- price_change_1h, price_change_4h (tính từ snapshots lân cận)
- fear_greed
- has_high_whale (bool)
- hours_to_event (economic calendar)

Target (output): label — 'UP', 'DOWN', 'SIDEWAYS'

Model: Random Forest (sklearn)
- Giải thích được (feature importance)
- Ổn định với dữ liệu ít
- Không cần GPU

Lưu model: data/models/model_{asset}_{date}.pkl
Lưu metadata: n_samples, accuracy, top_features
"""

import os
import json
import time
import pickle
import logging
from datetime import datetime, timezone

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report

from .database import CryptDB, MODELS_DIR

logger = logging.getLogger(__name__)

# Feature names (thứ tự quan trọng — phải khớp với extract_features)
FEATURE_NAMES = [
    "funding_rate",
    "oi_change_1h",
    "long_ratio",
    "short_ratio",
    "fear_greed",
    "price_change_1h",
    "price_change_4h",
]

MIN_SAMPLES_TRAIN = 30  # Tối thiểu để train (spec đề xuất 300+ cho tin cậy)
WARN_SAMPLES = 300      # Dưới mức này cảnh báo "ít dữ liệu"


def extract_features(snapshot: dict) -> list[float] | None:
    """
    Trích xuất features từ 1 snapshot.
    Trả về list float hoặc None nếu thiếu dữ liệu.
    """
    required = ["funding_rate", "oi_change_1h", "long_ratio"]

    # Kiểm tra dữ liệu tối thiểu
    # Forex không có funding/oi nên chỉ train cho crypto
    for field in required:
        if snapshot.get(field) is None:
            return None

    features = [
        snapshot.get("funding_rate", 0) or 0,
        snapshot.get("oi_change_1h", 0) or 0,
        snapshot.get("long_ratio", 0.5) or 0.5,
        snapshot.get("short_ratio", 0.5) or 0.5,
        (snapshot.get("fear_greed") or 50) / 100,  # normalize 0-1
        0,  # price_change_1h — placeholder, tính bên dưới nếu có
        0,  # price_change_4h — placeholder
    ]

    return features


def prepare_training_data(db: CryptDB, asset: str) -> tuple[np.ndarray, np.ndarray, int]:
    """
    Chuẩn bị X (features) và y (labels) cho training.
    Trả về (X, y, n_samples).
    """
    labeled = db.get_labeled_data(asset=asset)

    X_list = []
    y_list = []

    for snap in labeled:
        features = extract_features(snap)
        if features is None:
            continue
        X_list.append(features)
        y_list.append(snap["label"])

    if not X_list:
        return np.array([]), np.array([]), 0

    return np.array(X_list), np.array(y_list), len(X_list)


def train_model(db: CryptDB, asset: str) -> dict:
    """
    Train Random Forest cho 1 asset.

    Returns:
        dict metadata: {
            "asset", "n_samples", "accuracy_train", "accuracy_test",
            "feature_importance", "model_path", "warning", "label_distribution"
        }
    """
    os.makedirs(MODELS_DIR, exist_ok=True)

    X, y, n_samples = prepare_training_data(db, asset)

    result = {
        "asset": asset,
        "n_samples": n_samples,
        "timestamp": int(time.time()),
    }

    if n_samples < MIN_SAMPLES_TRAIN:
        result["error"] = (
            f"Not enough data: {n_samples}/{MIN_SAMPLES_TRAIN} samples. "
            f"Need more data collection."
        )
        return result

    if n_samples < WARN_SAMPLES:
        result["warning"] = (
            f"Model has {n_samples} data points "
            f"(need ~{WARN_SAMPLES}+ for better reliability). "
            f"Current signals are preliminary."
        )

    # Label distribution
    unique, counts = np.unique(y, return_counts=True)
    result["label_distribution"] = dict(zip(unique.tolist(), counts.tolist()))

    # Train/test split
    test_size = min(0.2, max(0.1, 10 / n_samples))
    try:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42, stratify=y
        )
    except ValueError:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42
        )

    # Train Random Forest
    model = RandomForestClassifier(
        n_estimators=100,
        max_depth=8,
        min_samples_split=5,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)

    # Evaluate
    y_pred_train = model.predict(X_train)
    y_pred_test = model.predict(X_test)

    result["accuracy_train"] = round(accuracy_score(y_train, y_pred_train) * 100, 1)
    result["accuracy_test"] = round(accuracy_score(y_test, y_pred_test) * 100, 1)

    # Feature importance
    importance = model.feature_importances_
    feature_imp = sorted(
        zip(FEATURE_NAMES, importance.tolist()),
        key=lambda x: x[1],
        reverse=True,
    )
    result["feature_importance"] = feature_imp

    # Save model
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    model_filename = f"model_{asset}_{date_str}.pkl"
    model_path = os.path.join(MODELS_DIR, model_filename)

    with open(model_path, "wb") as f:
        pickle.dump(model, f)
    result["model_path"] = model_path

    # Save metadata
    meta_path = model_path.replace(".pkl", "_meta.json")
    with open(meta_path, "w") as f:
        json.dump(result, f, indent=2, default=str)

    logger.info(
        f"Trained model for {asset}: {n_samples} samples, "
        f"train_acc={result['accuracy_train']}%, test_acc={result['accuracy_test']}%"
    )

    return result


def load_latest_model(asset: str) -> tuple[RandomForestClassifier | None, dict | None]:
    """
    Load model mới nhất cho asset.
    Returns (model, metadata) hoặc (None, None) nếu chưa có.
    """
    os.makedirs(MODELS_DIR, exist_ok=True)

    model_files = [
        f for f in os.listdir(MODELS_DIR)
        if f.startswith(f"model_{asset}_") and f.endswith(".pkl")
    ]

    if not model_files:
        return None, None

    model_files.sort(reverse=True)
    latest = model_files[0]
    model_path = os.path.join(MODELS_DIR, latest)

    try:
        with open(model_path, "rb") as f:
            model = pickle.load(f)

        meta_path = model_path.replace(".pkl", "_meta.json")
        meta = None
        if os.path.exists(meta_path):
            with open(meta_path, "r") as f:
                meta = json.load(f)

        return model, meta
    except Exception as e:
        logger.error(f"Error loading model {asset}: {e}")
        return None, None


def train_all_assets(db: CryptDB, crypto_symbols: list[str]) -> list[dict]:
    """Train model cho tất cả crypto symbols. Trả về list kết quả."""
    results = []
    for sym in crypto_symbols:
        result = train_model(db, sym)
        results.append(result)
    return results

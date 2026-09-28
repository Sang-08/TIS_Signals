"""
database.py — PostgreSQL database layer cho Trading Intelligence System.

Lưu tất cả dữ liệu lịch sử: giá forex/crypto, derivatives, tin tức, whale,
economic calendar, subscribers, signals, cross-exchange funding.

PostgreSQL connection: từ DATABASE_URL env var
Connection pooling: psycopg2.pool.ThreadedConnectionPool (min=2, max=10)

Schema tối ưu cho PostgreSQL:
- SERIAL thay AUTOINCREMENT
- DOUBLE PRECISION thay REAL
- ON CONFLICT thay INSERT OR IGNORE
- Parameterized queries dùng %s thay ?
"""

import os
import time
import logging
import atexit
from datetime import datetime, timezone
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
import psycopg2.pool

logger = logging.getLogger(__name__)

# Project root = thư mục cha của bot/
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(PROJECT_ROOT, "data", "models")

# Default connection string — override via DATABASE_URL env var
DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/Trading Intelligence System"


class CryptDB:
    """Thread-safe PostgreSQL wrapper với connection pooling."""


    def _parse_url(self) -> dict:
        """Parse DATABASE_URL -> keyword args (handles DB names with spaces)."""
        from urllib.parse import urlparse, unquote
        p = urlparse(self.database_url)
        kw = {}
        if p.hostname: kw["host"] = p.hostname
        if p.port: kw["port"] = p.port
        if p.username: kw["user"] = unquote(p.username)
        if p.password: kw["password"] = unquote(p.password)
        if p.path and p.path != "/": kw["dbname"] = unquote(p.path.lstrip("/"))
        return kw

    def __init__(self, database_url: str | None = None):
        self.database_url = database_url or os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
        os.makedirs(MODELS_DIR, exist_ok=True)

        # Connection pool (2-10 connections)
        try:
            self._pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=2,
                maxconn=10,
                **self._parse_url(),
            )
            logger.info(f"PostgreSQL connection pool created")
        except psycopg2.Error as e:
            logger.error(f"Cannot connect to PostgreSQL: {e}")
            raise SystemExit(f"Database connection failed: {e}")

        # Cleanup pool on exit
        atexit.register(self._close_pool)

        # Init tables
        self._init_tables()

    def _close_pool(self):
        """Đóng tất cả connections trong pool."""
        if hasattr(self, "_pool") and self._pool and not self._pool.closed:
            self._pool.closeall()
            logger.info("PostgreSQL connection pool closed")

    @contextmanager
    def _get_conn(self):
        """Context manager: lấy connection từ pool, tự trả lại sau khi dùng."""
        conn = self._pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)

    def _execute(self, query: str, params: tuple = (), fetch: str = "none"):
        """
        Execute query an toàn.
        fetch: 'none' | 'one' | 'all'
        """
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(query, params)
                if fetch == "one":
                    return cur.fetchone()
                elif fetch == "all":
                    return cur.fetchall()
                return None

    def _execute_many(self, query: str, params_list: list[tuple]):
        """Execute batch."""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                psycopg2.extras.execute_batch(cur, query, params_list)

    def _init_tables(self):
        """Tạo tất cả bảng + indexes nếu chưa có."""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS snapshots (
                        id SERIAL PRIMARY KEY,
                        asset VARCHAR(30) NOT NULL,
                        timestamp BIGINT NOT NULL,
                        price DOUBLE PRECISION,
                        funding_rate DOUBLE PRECISION,
                        oi_value DOUBLE PRECISION,
                        oi_change_1h DOUBLE PRECISION,
                        long_ratio DOUBLE PRECISION,
                        short_ratio DOUBLE PRECISION,
                        fear_greed INTEGER,
                        label VARCHAR(10),
                        price_4h_later DOUBLE PRECISION
                    );

                    CREATE INDEX IF NOT EXISTS idx_snapshots_asset_ts
                        ON snapshots(asset, timestamp);
                    CREATE INDEX IF NOT EXISTS idx_snapshots_label
                        ON snapshots(label) WHERE label IS NULL;

                    CREATE TABLE IF NOT EXISTS news_items (
                        id SERIAL PRIMARY KEY,
                        timestamp BIGINT,
                        headline TEXT,
                        source VARCHAR(100),
                        url TEXT UNIQUE,
                        sentiment_score DOUBLE PRECISION
                    );

                    CREATE INDEX IF NOT EXISTS idx_news_ts
                        ON news_items(timestamp);

                    CREATE TABLE IF NOT EXISTS whale_transactions (
                        id SERIAL PRIMARY KEY,
                        timestamp BIGINT,
                        symbol VARCHAR(20),
                        amount_usd DOUBLE PRECISION,
                        from_type VARCHAR(100),
                        to_type VARCHAR(100),
                        tx_hash TEXT UNIQUE
                    );

                    CREATE INDEX IF NOT EXISTS idx_whale_ts
                        ON whale_transactions(timestamp);

                    CREATE TABLE IF NOT EXISTS signals (
                        id SERIAL PRIMARY KEY,
                        asset VARCHAR(30),
                        timestamp BIGINT,
                        direction VARCHAR(10),
                        probability DOUBLE PRECISION,
                        features_json TEXT,
                        outcome VARCHAR(10),
                        outcome_checked_at BIGINT
                    );

                    CREATE INDEX IF NOT EXISTS idx_signals_asset_ts
                        ON signals(asset, timestamp);
                    CREATE INDEX IF NOT EXISTS idx_signals_unchecked
                        ON signals(timestamp) WHERE outcome IS NULL;

                    CREATE TABLE IF NOT EXISTS subscribers (
                        chat_id BIGINT PRIMARY KEY,
                        subscribed_at BIGINT
                    );

                    CREATE TABLE IF NOT EXISTS economic_events (
                        id SERIAL PRIMARY KEY,
                        event_date TEXT,
                        title TEXT,
                        country VARCHAR(10),
                        impact VARCHAR(10),
                        forecast VARCHAR(50),
                        previous VARCHAR(50),
                        actual VARCHAR(50),
                        fetched_at BIGINT,
                        UNIQUE(event_date, title, country)
                    );

                    CREATE INDEX IF NOT EXISTS idx_econ_date
                        ON economic_events(event_date);

                    CREATE TABLE IF NOT EXISTS alert_cooldowns (
                        alert_key VARCHAR(200) PRIMARY KEY,
                        last_sent BIGINT
                    );

                    -- Bảng cross-exchange funding (Bybit, OKX...)
                    CREATE TABLE IF NOT EXISTS cross_exchange_funding (
                        id SERIAL PRIMARY KEY,
                        asset VARCHAR(30) NOT NULL,
                        exchange VARCHAR(20) NOT NULL,
                        timestamp BIGINT NOT NULL,
                        funding_rate DOUBLE PRECISION,
                        mark_price DOUBLE PRECISION,
                        open_interest DOUBLE PRECISION,
                        volume_24h DOUBLE PRECISION
                    );

                    CREATE INDEX IF NOT EXISTS idx_cross_funding_asset_ts
                        ON cross_exchange_funding(asset, exchange, timestamp);

                    -- Bảng system metrics
                    CREATE TABLE IF NOT EXISTS system_metrics (
                        id SERIAL PRIMARY KEY,
                        timestamp BIGINT NOT NULL,
                        metric_name VARCHAR(50) NOT NULL,
                        metric_value DOUBLE PRECISION,
                        metadata TEXT
                    );

                    CREATE INDEX IF NOT EXISTS idx_metrics_name_ts
                        ON system_metrics(metric_name, timestamp);
                """)

        logger.info("PostgreSQL tables initialized")

    # ─────────────── Snapshots ───────────────

    def record_snapshot(
        self,
        asset: str,
        price: float | None = None,
        funding_rate: float | None = None,
        oi_value: float | None = None,
        oi_change_1h: float | None = None,
        long_ratio: float | None = None,
        short_ratio: float | None = None,
        fear_greed: int | None = None,
        timestamp: int | None = None,
    ):
        """Ghi 1 snapshot thị trường vào DB."""
        ts = timestamp or int(time.time())
        self._execute(
            """INSERT INTO snapshots
               (asset, timestamp, price, funding_rate, oi_value, oi_change_1h,
                long_ratio, short_ratio, fear_greed)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (asset, ts, price, funding_rate, oi_value, oi_change_1h,
             long_ratio, short_ratio, fear_greed),
        )

    def get_latest_snapshot(self, asset: str) -> dict | None:
        """Lấy snapshot mới nhất của 1 asset."""
        row = self._execute(
            "SELECT * FROM snapshots WHERE asset = %s ORDER BY timestamp DESC LIMIT 1",
            (asset,), fetch="one",
        )
        return dict(row) if row else None

    def get_latest_snapshots(self) -> dict[str, dict]:
        """Lấy snapshot mới nhất của MỌI asset. Trả dict {asset: snapshot}."""
        rows = self._execute("""
            SELECT DISTINCT ON (asset) *
            FROM snapshots
            ORDER BY asset, timestamp DESC
        """, fetch="all")
        return {row["asset"]: dict(row) for row in (rows or [])}

    def get_price_history(self, asset: str, hours: int = 24) -> list[tuple[int, float]]:
        """Lấy lịch sử giá [(timestamp, price), ...]."""
        since = int(time.time()) - hours * 3600
        rows = self._execute(
            """SELECT timestamp, price FROM snapshots
               WHERE asset = %s AND timestamp >= %s AND price IS NOT NULL
               ORDER BY timestamp""",
            (asset, since), fetch="all",
        )
        return [(r["timestamp"], r["price"]) for r in (rows or [])]

    def get_funding_history(self, asset: str, hours: int = 24) -> list[tuple[int, float]]:
        """Lấy lịch sử funding rate."""
        since = int(time.time()) - hours * 3600
        rows = self._execute(
            """SELECT timestamp, funding_rate FROM snapshots
               WHERE asset = %s AND timestamp >= %s AND funding_rate IS NOT NULL
               ORDER BY timestamp""",
            (asset, since), fetch="all",
        )
        return [(r["timestamp"], r["funding_rate"]) for r in (rows or [])]

    def get_oi_history(self, asset: str, hours: int = 24) -> list[tuple[int, float]]:
        """Lấy lịch sử OI."""
        since = int(time.time()) - hours * 3600
        rows = self._execute(
            """SELECT timestamp, oi_value FROM snapshots
               WHERE asset = %s AND timestamp >= %s AND oi_value IS NOT NULL
               ORDER BY timestamp""",
            (asset, since), fetch="all",
        )
        return [(r["timestamp"], r["oi_value"]) for r in (rows or [])]

    def get_price_change(self, asset: str, seconds_ago: float) -> float | None:
        """Tính % thay đổi giá so với điểm gần nhất cách đây >= seconds_ago."""
        now = int(time.time())
        target_time = now - seconds_ago

        latest = self._execute(
            """SELECT price FROM snapshots
               WHERE asset = %s AND price IS NOT NULL
               ORDER BY timestamp DESC LIMIT 1""",
            (asset,), fetch="one",
        )
        if not latest:
            return None

        old = self._execute(
            """SELECT price FROM snapshots
               WHERE asset = %s AND timestamp <= %s AND price IS NOT NULL
               ORDER BY timestamp DESC LIMIT 1""",
            (asset, target_time), fetch="one",
        )
        if not old or old["price"] == 0:
            return None

        return (latest["price"] - old["price"]) / old["price"] * 100

    # ─────────────── Labeler support ───────────────

    def get_unlabeled_snapshots(self, older_than_hours: float = 4) -> list[dict]:
        """Lấy snapshots chưa gán label và đã qua >= older_than_hours."""
        cutoff = int(time.time()) - int(older_than_hours * 3600)
        rows = self._execute(
            """SELECT * FROM snapshots
               WHERE label IS NULL AND timestamp <= %s AND price IS NOT NULL
               ORDER BY timestamp""",
            (cutoff,), fetch="all",
        )
        return [dict(r) for r in (rows or [])]

    def label_snapshot(self, snapshot_id: int, label: str, price_4h_later: float):
        """Gán label cho snapshot đã qua."""
        self._execute(
            "UPDATE snapshots SET label = %s, price_4h_later = %s WHERE id = %s",
            (label, price_4h_later, snapshot_id),
        )

    def get_labeled_data(self, asset: str | None = None, min_count: int = 0) -> list[dict]:
        """Lấy tất cả snapshots đã có label (cho training)."""
        if asset:
            rows = self._execute(
                """SELECT * FROM snapshots
                   WHERE label IS NOT NULL AND asset = %s
                   ORDER BY timestamp""",
                (asset,), fetch="all",
            )
        else:
            rows = self._execute(
                "SELECT * FROM snapshots WHERE label IS NOT NULL ORDER BY timestamp",
                fetch="all",
            )
        return [dict(r) for r in (rows or [])]

    # ─────────────── News ───────────────

    def record_news(self, headline: str, source: str, url: str, timestamp: int):
        """Ghi tin tức. Bỏ qua nếu URL trùng."""
        try:
            self._execute(
                """INSERT INTO news_items (timestamp, headline, source, url)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (url) DO NOTHING""",
                (timestamp, headline, source, url),
            )
        except psycopg2.Error:
            pass

    def get_recent_news(self, limit: int = 10) -> list[dict]:
        """Lấy tin tức mới nhất."""
        rows = self._execute(
            "SELECT * FROM news_items ORDER BY timestamp DESC LIMIT %s",
            (limit,), fetch="all",
        )
        return [dict(r) for r in (rows or [])]

    # ─────────────── Whale Transactions ───────────────

    def record_whale_tx(self, symbol: str, amount_usd: float, from_type: str,
                        to_type: str, tx_hash: str | None = None, timestamp: int | None = None):
        """Ghi whale transaction. Bỏ qua nếu tx_hash trùng."""
        ts = timestamp or int(time.time())
        hash_val = tx_hash or f"{ts}_{symbol}_{amount_usd}"
        try:
            self._execute(
                """INSERT INTO whale_transactions
                   (timestamp, symbol, amount_usd, from_type, to_type, tx_hash)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (tx_hash) DO NOTHING""",
                (ts, symbol, amount_usd, from_type, to_type, hash_val),
            )
        except psycopg2.Error:
            pass

    def get_recent_whale_txs(self, hours: int = 1, limit: int = 10) -> list[dict]:
        """Lấy whale transactions gần đây."""
        since = int(time.time()) - hours * 3600
        rows = self._execute(
            """SELECT * FROM whale_transactions
               WHERE timestamp >= %s
               ORDER BY amount_usd DESC LIMIT %s""",
            (since, limit), fetch="all",
        )
        return [dict(r) for r in (rows or [])]

    # ─────────────── Signals ───────────────

    def record_signal(self, asset: str, direction: str, probability: float,
                      features_json: str, timestamp: int | None = None):
        """Ghi signal mới."""
        ts = timestamp or int(time.time())
        self._execute(
            """INSERT INTO signals
               (asset, timestamp, direction, probability, features_json)
               VALUES (%s, %s, %s, %s, %s)""",
            (asset, ts, direction, probability, features_json),
        )

    def get_unchecked_signals(self, older_than_hours: float = 4) -> list[dict]:
        """Lấy signals chưa kiểm tra outcome và đã qua >= 4h."""
        cutoff = int(time.time()) - int(older_than_hours * 3600)
        rows = self._execute(
            """SELECT * FROM signals
               WHERE outcome IS NULL AND timestamp <= %s
               ORDER BY timestamp""",
            (cutoff,), fetch="all",
        )
        return [dict(r) for r in (rows or [])]

    def update_signal_outcome(self, signal_id: int, outcome: str):
        """Cập nhật outcome cho signal: CORRECT / WRONG."""
        self._execute(
            "UPDATE signals SET outcome = %s, outcome_checked_at = %s WHERE id = %s",
            (outcome, int(time.time()), signal_id),
        )

    def get_signal_accuracy(self, asset: str, days: int = 7) -> dict:
        """Tính accuracy của signals trong N ngày qua."""
        since = int(time.time()) - days * 86400
        rows = self._execute(
            """SELECT outcome, COUNT(*) as cnt FROM signals
               WHERE asset = %s AND timestamp >= %s AND outcome IS NOT NULL
               GROUP BY outcome""",
            (asset, since), fetch="all",
        )
        stats = {r["outcome"]: r["cnt"] for r in (rows or [])}
        correct = stats.get("CORRECT", 0)
        wrong = stats.get("WRONG", 0)
        total = correct + wrong
        return {
            "correct": correct, "wrong": wrong, "total": total,
            "win_rate": correct / total * 100 if total > 0 else 0, "days": days,
        }

    def get_recent_signals(self, asset: str | None = None, limit: int = 10) -> list[dict]:
        """Lấy signals gần đây."""
        if asset:
            rows = self._execute(
                """SELECT * FROM signals WHERE asset = %s
                   ORDER BY timestamp DESC LIMIT %s""",
                (asset, limit), fetch="all",
            )
        else:
            rows = self._execute(
                "SELECT * FROM signals ORDER BY timestamp DESC LIMIT %s",
                (limit,), fetch="all",
            )
        return [dict(r) for r in (rows or [])]

    # ─────────────── Subscribers ───────────────

    def add_subscriber(self, chat_id: int):
        """Thêm subscriber."""
        self._execute(
            """INSERT INTO subscribers (chat_id, subscribed_at) VALUES (%s, %s)
               ON CONFLICT (chat_id) DO UPDATE SET subscribed_at = EXCLUDED.subscribed_at""",
            (chat_id, int(time.time())),
        )

    def remove_subscriber(self, chat_id: int):
        """Xóa subscriber."""
        self._execute("DELETE FROM subscribers WHERE chat_id = %s", (chat_id,))

    def get_subscribers(self) -> set[int]:
        """Lấy tất cả subscriber chat_ids."""
        rows = self._execute("SELECT chat_id FROM subscribers", fetch="all")
        return {r["chat_id"] for r in (rows or [])}

    # ─────────────── Economic Events ───────────────

    def record_calendar_events(self, events: list[dict]):
        """Lưu danh sách sự kiện economic calendar. Bỏ qua trùng."""
        now = int(time.time())
        params_list = []
        for ev in events:
            params_list.append((
                ev.get("date", ""), ev.get("title", ""), ev.get("country", ""),
                ev.get("impact", "Low"), ev.get("forecast", ""), ev.get("previous", ""),
                ev.get("actual", ""), now,
            ))
        if params_list:
            self._execute_many(
                """INSERT INTO economic_events
                   (event_date, title, country, impact, forecast, previous, actual, fetched_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (event_date, title, country)
                   DO UPDATE SET
                       forecast = EXCLUDED.forecast,
                       previous = EXCLUDED.previous,
                       actual = EXCLUDED.actual,
                       fetched_at = EXCLUDED.fetched_at""",
                params_list,
            )

    def get_upcoming_events(self, hours: int = 48) -> list[dict]:
        """Lấy sự kiện economic calendar sắp tới trong N giờ."""
        from datetime import timedelta
        now_iso = datetime.now(timezone.utc).isoformat()
        cutoff_iso = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
        rows = self._execute(
            """SELECT * FROM economic_events
               WHERE event_date >= %s AND event_date <= %s
               ORDER BY event_date""",
            (now_iso, cutoff_iso), fetch="all",
        )
        return [dict(r) for r in (rows or [])]

    def get_all_calendar_events(self) -> list[dict]:
        """Lấy tất cả sự kiện trong tuần."""
        rows = self._execute(
            "SELECT * FROM economic_events ORDER BY event_date",
            fetch="all",
        )
        return [dict(r) for r in (rows or [])]

    # ─────────────── Alert Cooldowns ───────────────

    def check_alert_cooldown(self, alert_key: str, cooldown_seconds: int = 1800) -> bool:
        """Kiểm tra có nên gửi alert không. True = nên gửi."""
        row = self._execute(
            "SELECT last_sent FROM alert_cooldowns WHERE alert_key = %s",
            (alert_key,), fetch="one",
        )
        if not row:
            return True
        return (int(time.time()) - row["last_sent"]) >= cooldown_seconds

    def mark_alert_sent(self, alert_key: str):
        """Đánh dấu alert đã gửi (reset cooldown)."""
        self._execute(
            """INSERT INTO alert_cooldowns (alert_key, last_sent) VALUES (%s, %s)
               ON CONFLICT (alert_key) DO UPDATE SET last_sent = EXCLUDED.last_sent""",
            (alert_key, int(time.time())),
        )

    # ─────────────── Cross-Exchange Funding ───────────────

    def record_cross_exchange_funding(
        self,
        asset: str,
        exchange: str,
        funding_rate: float | None = None,
        mark_price: float | None = None,
        open_interest: float | None = None,
        volume_24h: float | None = None,
        timestamp: int | None = None,
    ):
        """Ghi funding rate từ exchange khác (Bybit, OKX...)."""
        ts = timestamp or int(time.time())
        self._execute(
            """INSERT INTO cross_exchange_funding
               (asset, exchange, timestamp, funding_rate, mark_price, open_interest, volume_24h)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (asset, exchange, ts, funding_rate, mark_price, open_interest, volume_24h),
        )

    def get_cross_exchange_latest(self, asset: str) -> list[dict]:
        """Lấy funding rate mới nhất từ tất cả exchanges cho 1 asset."""
        rows = self._execute(
            """SELECT DISTINCT ON (exchange) *
               FROM cross_exchange_funding
               WHERE asset = %s
               ORDER BY exchange, timestamp DESC""",
            (asset,), fetch="all",
        )
        return [dict(r) for r in (rows or [])]

    def get_cross_exchange_history(self, asset: str, exchange: str, hours: int = 24) -> list[dict]:
        """Lấy lịch sử funding rate từ 1 exchange."""
        since = int(time.time()) - hours * 3600
        rows = self._execute(
            """SELECT timestamp, funding_rate, mark_price
               FROM cross_exchange_funding
               WHERE asset = %s AND exchange = %s AND timestamp >= %s
               ORDER BY timestamp""",
            (asset, exchange, since), fetch="all",
        )
        return [dict(r) for r in (rows or [])]

    # ─────────────── System Metrics ───────────────

    def record_metric(self, metric_name: str, metric_value: float, metadata: str = ""):
        """Ghi system metric (collector time, error count, etc.)."""
        self._execute(
            """INSERT INTO system_metrics (timestamp, metric_name, metric_value, metadata)
               VALUES (%s, %s, %s, %s)""",
            (int(time.time()), metric_name, metric_value, metadata),
        )

    def get_metrics(self, metric_name: str, hours: int = 24) -> list[dict]:
        """Lấy metrics gần đây."""
        since = int(time.time()) - hours * 3600
        rows = self._execute(
            """SELECT * FROM system_metrics
               WHERE metric_name = %s AND timestamp >= %s
               ORDER BY timestamp""",
            (metric_name, since), fetch="all",
        )
        return [dict(r) for r in (rows or [])]

    # ─────────────── Cleanup ───────────────

    def cleanup_old(self, days: int = 60):
        """Xóa dữ liệu cũ hơn N ngày."""
        cutoff = int(time.time()) - days * 86400
        self._execute("DELETE FROM snapshots WHERE timestamp < %s", (cutoff,))
        self._execute("DELETE FROM news_items WHERE timestamp < %s", (cutoff,))
        self._execute("DELETE FROM whale_transactions WHERE timestamp < %s", (cutoff,))
        self._execute("DELETE FROM cross_exchange_funding WHERE timestamp < %s", (cutoff,))
        self._execute("DELETE FROM system_metrics WHERE timestamp < %s", (cutoff,))
        logger.info(f"Cleanup done: removed data older than {days} days")

    def close(self):
        """Đóng connection pool."""
        self._close_pool()

    # ─────────────── Stats ───────────────

    def get_db_stats(self) -> dict:
        """Lấy thống kê database (số records, size...)."""
        tables = ["snapshots", "news_items", "whale_transactions", "signals",
                   "subscribers", "economic_events", "cross_exchange_funding"]
        stats = {}
        for table in tables:
            row = self._execute(
                f"SELECT COUNT(*) as cnt FROM {table}",
                fetch="one",
            )
            stats[table] = row["cnt"] if row else 0

        # DB size
        row = self._execute(
            "SELECT pg_database_size(current_database()) as size",
            fetch="one",
        )
        stats["db_size_mb"] = round(row["size"] / 1024 / 1024, 2) if row else 0

        return stats

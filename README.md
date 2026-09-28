# Trading Intelligence System

Hệ thống cá nhân tổng hợp dữ liệu Forex + Crypto từ nhiều nguồn, tự thu thập hàng ngày,
tự train ML model, đưa gợi ý lệnh kèm xác suất — người dùng tự quyết định.

## Tính năng

### Bot Telegram
- `/forex` — giá major pairs hiện tại + % thay đổi 1h/24h
- `/crypto BTCUSDT ETHUSDT` — funding rate, OI, long/short ratio
- `/funding BTCUSDT` — so sánh funding rate cross-exchange (Binance vs Bybit)
- `/news` — tin tức forex mới nhất
- `/whale` — giao dịch on-chain lớn (cần Whale Alert key)
- `/summary` — tổng hợp toàn bộ: forex + crypto + F&G + calendar + whale
- `/calendar` — sự kiện vĩ mô sắp tới (NFP, CPI, Fed...)
- `/signal BTCUSDT` — gợi ý lệnh ML (cần đủ dữ liệu)
- `/accuracy` — win rate model theo thời gian
- `/dbstats` — thống kê database
- `/subscribe` `/unsubscribe` — nhận cập nhật + cảnh báo biến động

### Hệ thống tự động (chạy nền)
- **Thu thập dữ liệu** mỗi giờ → PostgreSQL (giá, derivatives, tin tức, whale, F&G, calendar, Bybit)
- **Gán nhãn** snapshots sau 4h (UP/DOWN/SIDEWAYS) → dữ liệu training
- **Train model** Random Forest mỗi ngày lúc 00:00
- **Kiểm tra accuracy** signal theo thời gian thực
- **Cảnh báo biến động** đột biến (giá, funding, OI, whale) → gửi ngay cho subscribers
- **Cross-exchange monitoring** — so sánh funding rate Binance vs Bybit
- **System metrics** — ghi lại thời gian collection, error count
- **Cleanup** dữ liệu cũ > 60 ngày

### Web Dashboard
- Dark trading terminal (kiểu TradingView/Binance)
- Bảng giá forex real-time, crypto derivatives
- Chart funding rate + OI (Chart.js)
- Feed tin tức, whale transactions
- Economic calendar color-coded
- ML signals + accuracy tracker
- Cross-exchange funding comparison
- Auto-refresh mỗi 30s-5m

### Nguồn dữ liệu

| Nguồn | Dữ liệu | Key? | Giới hạn free |
|---|---|---|---|
| Finnhub | Giá forex + tin tức | Có (free) | 60 calls/phút |
| Binance Futures | Funding rate, OI, L/S ratio | Không cần | Rộng rãi |
| Bybit | Cross-exchange funding/OI | Không cần | Rộng rãi |
| Whale Alert | Giao dịch on-chain lớn | Có (free) | Giới hạn/tháng |
| alternative.me | Fear & Greed Index | Không cần | Không giới hạn |
| ForexFactory | Economic calendar | Không cần | Không giới hạn |

## Cài đặt

### 1. Cài dependencies

```bash
pip install -r requirements.txt
```

### 2. PostgreSQL

Hệ thống dùng **PostgreSQL** (không phải SQLite).

```bash
# Tạo database (nếu chưa có)
psql -U postgres -c "CREATE DATABASE \"Trading Intelligence System\";"
```

Tables được tạo tự động khi bot chạy lần đầu.

### 3. Lấy API keys

| Dịch vụ | Link đăng ký | Bắt buộc? |
|---|---|---|
| Telegram BotFather | Chat @BotFather, gửi `/newbot` | ✅ Có |
| Finnhub | https://finnhub.io/register | ✅ Có |
| Whale Alert | https://whale-alert.io/ (mục API) | ❌ Không |

### 4. Cấu hình

```bash
cp env.example .env
# Mở .env, điền:
# TELEGRAM_BOT_TOKEN=your_token
# FINNHUB_API_KEY=your_key
# DATABASE_URL=postgresql://postgres:your_password@localhost:5432/Trading Intelligence System
```

### 5. Chạy bot

```bash
python run_bot.py
```

Bot sẽ:
- Chạy polling Telegram
- Tự thu thập dữ liệu mỗi giờ vào PostgreSQL
- Thu thập cross-exchange data từ Bybit
- Tự gán nhãn + train model
- Gửi cảnh báo biến động cho subscribers

### 6. Chạy dashboard web (tùy chọn)

```bash
python run_api.py
# Mở browser: http://localhost:8877/dashboard/index.html
```

> **Lưu ý:** Dashboard cần bot đã chạy và thu thập dữ liệu trước (ít nhất vài giờ).
> Có thể chạy bot và API server song song.

## Cấu trúc thư mục

```
CrypT/
├── run_bot.py                # Entry point — chạy Telegram bot
├── run_api.py                # Entry point — chạy API server + dashboard
├── requirements.txt
├── env.example               # Mẫu cấu hình (.env)
├── README.md
│
├── bot/                      # Core logic
│   ├── __init__.py
│   ├── main_bot.py           # Telegram bot + scheduled jobs
│   ├── database.py           # PostgreSQL layer (connection pool)
│   ├── data_provider.py      # Forex data (Finnhub)
│   ├── crypto_provider.py    # Crypto data (Binance + Whale Alert)
│   ├── bybit_provider.py     # Bybit cross-exchange funding
│   ├── collector.py          # Thu thập tự động + alert detection
│   ├── economic_calendar.py  # Economic calendar (ForexFactory)
│   ├── labeler.py            # Gán nhãn UP/DOWN/SIDEWAYS
│   ├── trainer.py            # Train Random Forest model
│   ├── signal.py             # Tạo gợi ý lệnh ML
│   └── backtest.py           # Theo dõi accuracy signal
│
├── api/                      # API server
│   ├── __init__.py
│   └── api_server.py         # FastAPI endpoints
│
├── dashboard/                # Web dashboard
│   ├── index.html
│   ├── style.css             # Dark trading terminal theme
│   └── app.js                # Dashboard logic
│
└── data/
    └── models/               # ML model files (.pkl)
```

## API Endpoints

```
GET /api/summary              — Tổng hợp market data
GET /api/candles?asset=BTCUSDT&hours=168
GET /api/derivatives?asset=BTCUSDT
GET /api/funding-history?asset=BTCUSDT&hours=24
GET /api/oi-history?asset=BTCUSDT&hours=24
GET /api/signals?asset=BTCUSDT&limit=50
GET /api/news?limit=20
GET /api/whale?hours=24
GET /api/accuracy
GET /api/calendar?hours=48
GET /api/calendar/all
GET /api/label-stats?asset=BTCUSDT
GET /api/model-info?asset=BTCUSDT
GET /api/cross-exchange?asset=BTCUSDT
GET /api/db-stats
```

## Giới hạn cần biết

### Dữ liệu
- Finnhub free tier: 60 calls/phút — đủ cho 1 user
- Giá forex từ Finnhub là tỷ giá tham chiếu, không phải giá broker (chênh lệch nhỏ)
- Whale Alert free tier giới hạn request/tháng — bot chỉ gọi mỗi giờ

### ML Model
- Cần **ít nhất 2-4 tuần** dữ liệu trước khi model có ý nghĩa
- Accuracy 60-65% trên live data là **tốt thực tế** — không kỳ vọng 80-90%
- Model chỉ train cho crypto (cần funding/OI features), forex chưa có đủ features
- Win rate 60% + risk/reward tốt = có edge thật

### Bot
- **Bot KHÔNG tự vào lệnh** — chỉ gợi ý
- Mọi signal đều kèm disclaimer rõ ràng

⚠️ **Bot tổng hợp dữ liệu + ML gợi ý, KHÔNG phải khuyến nghị tài chính.**
**Người dùng tự quyết định mọi giao dịch.**

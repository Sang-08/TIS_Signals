# Trading Intelligence System — Kế hoạch dự án toàn diện

> Tài liệu này mô tả toàn bộ hệ thống: đã làm, đang làm, sẽ làm, cách hoạt động,
> giới hạn thật, và lộ trình phát triển từng giai đoạn.
> Cập nhật lần cuối: 2026-06

---

## 1. MỤC TIÊU HỆ THỐNG

Xây một nền tảng cá nhân tổng hợp dữ liệu thị trường Forex + Crypto từ nhiều nguồn,
tự thu thập hàng ngày, tự học từ dữ liệu lịch sử, và đưa ra gợi ý lệnh kèm xác suất
để người dùng tự quyết định — không tự vào lệnh.

### Nguyên tắc xuyên suốt
- Dữ liệu thật từ API chính thức, không scrape trang trả phí
- Minh bạch: mọi gợi ý lệnh đều hiển thị rõ "dựa trên dữ liệu gì, bao nhiêu điểm"
- Không tạo ảo tưởng "dự đoán đúng 100%" — thị trường tài chính không có hệ thống nào làm được điều này
- Bot gợi ý, người dùng quyết định

---

## 2. KIẾN TRÚC TỔNG THỂ

```
┌──────────────────────────────────────────────────────────────────┐
│                        NGUỒN DỮ LIỆU                            │
│                                                                  │
│  Finnhub API          Binance Futures        Whale Alert         │
│  (Forex giá,          (Funding rate,         (Giao dịch          │
│   tin tức)             OI, L/S ratio)         on-chain lớn)      │
│                                                                  │
│  Bybit API            Fear & Greed           Economic Calendar   │
│  (Cross-exchange       Index                 (NFP, CPI, Fed...)  │
│   funding/OI)         (Tâm lý thị trường)                       │
└────────────────────────────┬─────────────────────────────────────┘
                             │ thu thập mỗi giờ
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                      BACKEND (Python)                           │
│                                                                  │
│  collector.py     → Thu thập + lưu SQLite mỗi giờ              │
│  labeler.py       → Gán nhãn UP/DOWN/SIDEWAYS sau 4h            │
│  trainer.py       → Train Random Forest mỗi ngày 00:00          │
│  signal.py        → Tạo gợi ý lệnh khi xác suất > ngưỡng       │
│  backtest.py      → Kiểm tra độ chính xác signal theo thời gian │
│  api_server.py    → FastAPI expose dữ liệu ra cho Web App       │
└──────────┬───────────────────────────────────┬───────────────────┘
           │                                   │
           ▼                                   ▼
┌─────────────────────┐             ┌─────────────────────────────┐
│    BOT TELEGRAM     │             │        WEB APP              │
│                     │             │                             │
│ Alert ngay khi      │             │ Chart nến (candlestick)     │
│ có signal mới       │             │ Đánh dấu signal ▲▼          │
│                     │             │ Funding/OI overlay          │
│ Lệnh:               │             │ Whale tx timeline           │
│ /forex              │             │ Win rate tracker            │
│ /crypto [symbol]    │             │ Economic calendar           │
│ /news               │             │ Multi-coin dashboard        │
│ /whale              │             │ Signal history              │
│ /summary            │             │ Model accuracy theo tuần    │
│ /signal BTC         │             │                             │
│ /subscribe          │             │ → Người dùng mở khi nhận    │
│ /accuracy           │             │   alert từ Telegram         │
└─────────────────────┘             └─────────────────────────────┘
```

---

## 3. TRẠNG THÁI HIỆN TẠI — ĐÃ LÀM XONG ✅

### File đã có trong thư mục `forex_bot/`

#### `data_provider.py` ✅
- Kết nối Finnhub API (free tier, cần key)
- Lấy giá hiện tại các cặp forex: EUR/USD, GBP/USD, USD/JPY, USD/CHF, AUD/USD, USD/CAD, NZD/USD
- Tính % thay đổi 1h / 24h dựa trên lịch sử tự ghi lại (file `price_history.json`)
- Lấy tin tức forex mới nhất (category=forex từ Finnhub)
- Xử lý lỗi gọn, không crash khi API lỗi

#### `crypto_provider.py` ✅
- Kết nối Binance Futures public API (KHÔNG cần key)
  - Funding rate hiện tại (`/fapi/v1/premiumIndex`)
  - Open Interest hiện tại + lịch sử (`/fapi/v1/openInterest`, `/futures/data/openInterestHist`)
  - Long/Short ratio (`/futures/data/globalLongShortAccountRatio`)
- Kết nối Whale Alert API (optional, cần key riêng)
  - Lấy giao dịch on-chain > $1M trong 60 phút qua
- Hàm `build_text_summary()`: tóm tắt trạng thái bằng lời
  - Ví dụ output: "Funding rate: +0.08% — dương cao (phe long đang trả phí lớn). OI 1h: tăng 3.2%. Tỷ lệ: 62% long / 38% short."
  - Kèm cảnh báo rõ: đây là mô tả dữ liệu, không phải dự đoán

#### `bot.py` ✅
- Bot Telegram đầy đủ với các lệnh:
  - `/start` `/help` — giới thiệu
  - `/forex` — giá major pairs
  - `/crypto [symbol]` — funding/OI/L-S (mặc định BTC+ETH, có thể thêm coin khác)
  - `/news` — tin tức mới nhất
  - `/whale` — giao dịch on-chain lớn (cần Whale Alert key)
  - `/subscribe` `/unsubscribe` — nhận/dừng cập nhật định kỳ
- Job định kỳ: tự gửi cập nhật cho subscriber theo `ALERT_INTERVAL_SECONDS`
- Xử lý lỗi từng lệnh độc lập (1 lệnh lỗi không làm sập bot)

#### `.env.example` ✅
```
TELEGRAM_BOT_TOKEN=
FINNHUB_API_KEY=
WHALE_ALERT_API_KEY=          # optional
WATCHLIST=OANDA:EUR_USD,...
ALERT_INTERVAL_SECONDS=3600
ALERT_THRESHOLD_PERCENT=0.5
```

#### `requirements.txt` ✅
```
python-telegram-bot==21.6
requests==2.32.3
python-dotenv==1.0.1
```

---

## 4. CẦN LÀM TIẾP — THEO THỨ TỰ ƯU TIÊN

---

### GIAI ĐOẠN 1 — Hoàn thiện nền tảng (Tuần 1-2)
*Mục tiêu: Bot chạy ổn định 24/7, tự thu thập dữ liệu vào database*

#### `collector.py` ❌ CHƯA LÀM
**Mục đích:** Thu thập dữ liệu tự động mỗi giờ, lưu vào SQLite
**Chi tiết:**
```python
# Chạy job mỗi giờ:
# 1. Lấy giá forex (Finnhub)          → bảng forex_prices
# 2. Lấy funding/OI/LS (Binance)      → bảng crypto_derivatives
# 3. Lấy tin tức (Finnhub)            → bảng news_items
# 4. Lấy whale tx (Whale Alert)       → bảng whale_transactions
# 5. Lấy Fear & Greed (alternative.me)→ bảng market_sentiment
# 6. Lấy Economic Calendar             → bảng economic_events
```
**Schema SQLite:**
```sql
CREATE TABLE snapshots (
  id INTEGER PRIMARY KEY,
  asset TEXT,           -- 'BTCUSDT', 'EUR_USD'...
  timestamp INTEGER,    -- unix timestamp
  price REAL,
  funding_rate REAL,
  oi_value REAL,
  oi_change_1h REAL,
  long_ratio REAL,
  short_ratio REAL,
  fear_greed INTEGER,
  -- label (điền sau 4h)
  label TEXT,           -- 'UP', 'DOWN', 'SIDEWAYS', NULL (chưa label)
  price_4h_later REAL   -- giá 4h sau, điền bởi labeler.py
);

CREATE TABLE news_items (
  id INTEGER PRIMARY KEY,
  timestamp INTEGER,
  headline TEXT,
  source TEXT,
  url TEXT,
  sentiment_score REAL  -- điền bởi NLP sau này
);

CREATE TABLE whale_transactions (
  id INTEGER PRIMARY KEY,
  timestamp INTEGER,
  symbol TEXT,
  amount_usd REAL,
  from_type TEXT,
  to_type TEXT
);

CREATE TABLE signals (
  id INTEGER PRIMARY KEY,
  asset TEXT,
  timestamp INTEGER,
  direction TEXT,       -- 'UP' hoặc 'DOWN'
  probability REAL,     -- 0.0 - 1.0
  features_json TEXT,   -- dữ liệu đầu vào của model lúc ra signal
  outcome TEXT,         -- 'CORRECT', 'WRONG', NULL (chưa biết)
  outcome_checked_at INTEGER
);
```

#### `economic_calendar.py` ❌ CHƯA LÀM
**Mục đích:** Lấy lịch sự kiện vĩ mô sắp tới (NFP, CPI, lãi suất Fed...)
**Nguồn:** Finnhub `/calendar/economic` (free) hoặc TradingEconomics (free tier giới hạn)
**Output Telegram:**
```
📅 Sự kiện vĩ mô sắp tới (24h):
• 14:30 UTC — USD Non-Farm Payrolls (tác động: 🔴 CAO)
  Dự báo: 185K | Trước: 175K
• 18:00 UTC — EUR ECB Interest Rate Decision (tác động: 🔴 CAO)
```

#### Lệnh `/summary` ❌ CHƯA LÀM
**Mục đích:** 1 lệnh duy nhất gộp toàn bộ thông tin
**Output mẫu:**
```
📊 TỔNG HỢP THỊ TRƯỜNG — 15:30 UTC

FOREX:
• EUR/USD: 1.08542 | ▼ -0.12% (1h) | ▼ -0.34% (24h)
• GBP/USD: 1.27831 | ▲ +0.08% (1h) | ▼ -0.21% (24h)

CRYPTO DERIVATIVES (BTC):
• Funding: +0.078% — dương cao
• OI: tăng 4.2% trong 1h qua
• L/S ratio: 1.84 (62% tài khoản đang long)

TÂM LÝ: Fear & Greed = 71 (GREED)

SỰ KIỆN SẮP TỚI: NFP lúc 14:30 UTC (2h nữa) 🔴

🐳 WHALE (1h qua): 2 giao dịch lớn
• $45M BTC: unknown → Binance
• $28M ETH: Coinbase → unknown

⚠️ Dữ liệu tham khảo, không phải khuyến nghị giao dịch.
```

#### Cảnh báo biến động đột biến ❌ CHƯA LÀM
**Mục đích:** Bot tự phát hiện biến động bất thường và gửi ngay
**Logic:**
```python
# Kiểm tra mỗi 15 phút:
if abs(price_change_15m) > THRESHOLD_PERCENT:
    send_alert("⚡ EUR/USD tăng đột biến +0.8% trong 15 phút")
if abs(funding_rate) > 0.1:
    send_alert("⚡ BTC funding rate cực cao: +0.12%")
if whale_usd > 50_000_000:
    send_alert("🐳 Giao dịch whale khổng lồ: $78M BTC vào Binance")
```

---

### GIAI ĐOẠN 2 — Hệ thống tự train (Tuần 3-8)
*Cần: ít nhất 2 tuần dữ liệu từ Giai đoạn 1*

#### `labeler.py` ❌ CHƯA LÀM
**Mục đích:** Nhìn lại snapshots đã qua 4h, gán nhãn kết quả
```python
# Chạy mỗi giờ:
# Tìm snapshots có timestamp <= now - 4h và label IS NULL
# So sánh price lúc snapshot vs price hiện tại
# UP: tăng > 0.3%
# DOWN: giảm > 0.3%
# SIDEWAYS: dao động trong ±0.3%
# Ghi label + price_4h_later vào database
```

#### `trainer.py` ❌ CHƯA LÀM
**Mục đích:** Train model mỗi ngày lúc 00:00 UTC
```python
# Features (input của model):
features = [
    'funding_rate',       # float, %
    'oi_change_1h',       # float, %
    'long_ratio',         # float, 0-1
    'price_change_1h',    # float, %
    'price_change_4h',    # float, %
    'fear_greed',         # int, 0-100
    'has_high_whale',     # bool: có whale > $50M trong 4h qua không
    'hours_to_event',     # float: còn bao nhiêu giờ đến sự kiện vĩ mô lớn tiếp theo
]

# Target (output của model):
target = 'label'  # 'UP', 'DOWN', 'SIDEWAYS'

# Model: Random Forest (sklearn)
# - Giải thích được (feature importance)
# - Ổn định với dữ liệu ít
# - Không cần GPU

# Lưu model: model_BTCUSDT_20260615.pkl
# Lưu metadata: n_samples, accuracy_train, accuracy_test, top_features
```
**Cảnh báo khi dữ liệu ít:**
```
⚠️ Model BTC hiện có 89 điểm dữ liệu (cần ~300+ để tin cậy hơn).
   Signal hiện tại chỉ mang tính tham khảo sơ bộ.
```

#### `signal.py` ❌ CHƯA LÀM
**Mục đích:** Tạo gợi ý lệnh khi có điều kiện
```
Lệnh /signal BTCUSDT — Output mẫu:

📈 GỢI Ý LỆNH BTC — 15:47 UTC

Hướng: GIẢM (SHORT)
Xác suất model: 67%
Ngưỡng kích hoạt: 65% ✅

Dữ liệu đầu vào:
• Funding: +0.082% (dương cao — long đang trả phí nhiều)
• OI 1h: +4.8% (vị thế mở đang tăng nhanh)
• L/S ratio: 1.91 (thiên long rõ rệt)
• Fear & Greed: 74 (Greed)
• Sự kiện vĩ mô gần nhất: 6.2h nữa

Pattern tương tự trong lịch sử:
→ Tìm thấy 41 lần tương tự trong 312 điểm dữ liệu
→ 28/41 lần (68%) giá giảm >0.3% trong 4h tiếp theo

⚠️ Đây là gợi ý dựa trên pattern thống kê, KHÔNG phải
   khuyến nghị tài chính. Bạn tự quyết định vào lệnh.
   Win rate lịch sử model: 61.4% (7 ngày qua)
```

#### `backtest.py` ❌ CHƯA LÀM
**Mục đích:** Theo dõi accuracy signal theo thời gian thực
```python
# Mỗi giờ: kiểm tra signal đã gửi 4h trước
# So sánh hướng signal với giá thực tế đi
# Lưu outcome: CORRECT / WRONG
# Tính rolling win rate: 7 ngày, 30 ngày

# Lệnh /accuracy — Output mẫu:
# 📊 ĐỘ CHÍNH XÁC MODEL (cập nhật liên tục)
# 
# BTC: 7 ngày: 61.4% (27/44) | 30 ngày: 58.2% (89/153)
# ETH: 7 ngày: 58.0% (29/50) | 30 ngày: 55.9% (95/170)
# 
# ⚠️ Win rate < 55% trong 7 ngày → model cần thêm dữ liệu
```

---

### GIAI ĐOẠN 3 — Web App (Tháng 2)
*Stack: FastAPI (Python) + Lightweight Charts (JS) + HTML thuần*

#### `api_server.py` ❌ CHƯA LÀM
**Mục đích:** FastAPI expose dữ liệu từ SQLite ra HTTP endpoints
```
GET /api/candles?asset=BTCUSDT&tf=1h&limit=200
GET /api/signals?asset=BTCUSDT&limit=50
GET /api/derivatives?asset=BTCUSDT
GET /api/news?limit=20
GET /api/whale?hours=24
GET /api/accuracy
GET /api/summary
GET /api/calendar
```

#### `dashboard/index.html` ❌ CHƯA LÀM
**Mục đích:** Giao diện web hoàn chỉnh
**Tính năng:**
- Chart nến (dùng Lightweight Charts — open source của TradingView)
- Overlay funding rate + OI dưới chart
- Đánh dấu signal ▲▼ lên chart với màu + xác suất
- Panel bên phải: tin tức + whale + economic calendar
- Bảng win rate theo thời gian
- Chọn asset từ dropdown
- Dark theme, responsive

---

### GIAI ĐOẠN 4 — Mở rộng nguồn dữ liệu (Tháng 2-3)

| Nguồn | Thêm gì | API | Chi phí |
|---|---|---|---|
| Bybit | Funding/OI để so sánh cross-exchange | Public free | Free |
| OKX | Tương tự | Public free | Free |
| Fear & Greed | Tâm lý tổng quát | alternative.me | Free |
| CoinGecko | Giá + volume altcoin | Free tier | Free |
| Glassnode | On-chain metrics (NVT, SOPR...) | Free tier giới hạn | Free tier |

**Cross-exchange funding arbitrage detector:**
```
⚡ CHÊNH LỆCH FUNDING RATE CROSS-EXCHANGE (BTC):
• Binance: +0.082%
• Bybit:   +0.031%
• OKX:     +0.067%
Chênh lệch cao nhất: Binance vs Bybit = 0.051%
```

---

### GIAI ĐOẠN 5 — Nâng cấp model (Tháng 3-6)
*Chỉ làm khi: model Random Forest có đủ 300+ điểm và accuracy ổn định*

```
Phase 5A: Ensemble
Random Forest + XGBoost → vote có trọng số

Phase 5B: Sentiment NLP
Phân tích tin tức → điểm cảm xúc -1 đến +1
Thêm vào features của model

Phase 5C: LSTM (nếu đủ dữ liệu ~1000+ điểm)
Học pattern chuỗi thời gian
Cần GPU hoặc cloud inference

Phase 5D: Multi-timeframe
Hiện tại: predict 4h tới
Thêm: 1h, 8h, 24h với model riêng từng timeframe
```

---

### GIAI ĐOẠN 6 — Hạ tầng (khi cần)

```
Hiện tại: chạy local/VPS đơn giản
Nâng cấp khi: nhiều user hoặc cần uptime cao

Docker Compose:
├── container: bot Telegram
├── container: collector (chạy jobs định kỳ)
├── container: FastAPI server
└── container: PostgreSQL (thay SQLite)

Monitoring:
├── Healthcheck tự động
├── Alert khi bot chết
└── Grafana dashboard hệ thống (CPU, RAM, DB size)
```

---

## 5. NGUỒN DỮ LIỆU & KEY CẦN THIẾT

| Dịch vụ | Dùng cho | Lấy key ở đâu | Bắt buộc? | Giới hạn free |
|---|---|---|---|---|
| Telegram BotFather | Token bot | Chat @BotFather | Có | Không giới hạn |
| Finnhub | Giá forex + tin tức + calendar | finnhub.io/register | Có | 60 calls/phút |
| Binance Futures | Funding, OI, L/S ratio | Không cần key | Có (auto) | Rộng rãi |
| Whale Alert | Giao dịch on-chain lớn | whale-alert.io | Không | Giới hạn/tháng |
| alternative.me | Fear & Greed Index | Không cần key | Không | Không giới hạn |
| Bybit | Cross-exchange funding | Không cần key | Không | Rộng rãi |

---

## 6. GIỚI HẠN THẬT — KHÔNG THỂ THAY ĐỔI

### Về dữ liệu
- **Coinglass Pro / Glassnode Pro / Nansen**: không thể scrape — vi phạm ToS, không bền vững
- **Dữ liệu tick real-time**: free tier Finnhub là giá tham chiếu, không phải giá bid/ask thật của broker (Exness, v.v.). Chênh lệch nhỏ nhưng cần biết.

### Về model
- Model cần **ít nhất 2-4 tuần dữ liệu** trước khi có ý nghĩa
- Accuracy 60-65% trên live data là **tốt thực tế** — không kỳ vọng 80-90%
- Thị trường thay đổi cấu trúc (regime change) → model có thể mất accuracy đột ngột → cần monitor liên tục
- Win rate 60% + risk/reward tốt = có edge thật. Win rate 60% + risk/reward tệ = vẫn thua

### Về bot
- **Bot KHÔNG tự vào lệnh** — kết nối broker để auto-trade đòi hỏi thêm nhiều lớp risk management phức tạp, nằm ngoài scope dự án này
- Subscriber list lưu RAM → mất khi restart (sẽ fix ở giai đoạn 1)

---

## 7. CẤU TRÚC THƯ MỤC CUỐI CÙNG

```
trading-intelligence/
│
├── .env                        # Key thật (KHÔNG commit lên git)
├── .env.example                # Mẫu cấu hình ✅
├── requirements.txt            # Dependencies ✅
├── README.md                   # Hướng dẫn cài đặt ✅
│
├── bot/
│   ├── bot.py                  # Bot Telegram chính ✅
│   ├── data_provider.py        # Forex data (Finnhub) ✅
│   ├── crypto_provider.py      # Crypto data (Binance + Whale) ✅
│   ├── collector.py            # Thu thập + lưu SQLite ❌
│   ├── economic_calendar.py    # Lịch sự kiện vĩ mô ❌
│   ├── labeler.py              # Gán nhãn dữ liệu ❌
│   ├── trainer.py              # Train model hàng ngày ❌
│   ├── signal.py               # Tạo gợi ý lệnh ❌
│   └── backtest.py             # Theo dõi accuracy ❌
│
├── api/
│   └── api_server.py           # FastAPI server ❌
│
├── dashboard/
│   ├── index.html              # Giao diện web ❌
│   ├── chart.js                # Logic chart ❌
│   └── style.css               # Dark theme ❌
│
├── data/
│   ├── market.db               # SQLite database (tạo tự động)
│   └── models/                 # File model đã train (.pkl)
│
└── docker/
    ├── Dockerfile              # ❌ (Giai đoạn 6)
    └── docker-compose.yml      # ❌ (Giai đoạn 6)
```

---

## 8. LỊCH TRÌNH THỰC HIỆN

```
TUẦN 1-2: Giai đoạn 1 (Nền tảng)
  □ collector.py — thu thập + lưu SQLite
  □ economic_calendar.py
  □ Lệnh /summary
  □ Cảnh báo biến động đột biến
  □ Fix: lưu subscriber list xuống file (không mất khi restart)
  → KẾT QUẢ: Bot chạy 24/7, dữ liệu tự động vào DB mỗi giờ

TUẦN 3-4: Giai đoạn 1 tiếp tục + bắt đầu Giai đoạn 2
  □ labeler.py — gán nhãn dữ liệu đã qua
  □ trainer.py — train model đầu tiên (dù ít dữ liệu, để test pipeline)
  □ signal.py — gợi ý lệnh đầu tiên (với cảnh báo "ít dữ liệu")
  → KẾT QUẢ: Signal đầu tiên xuất hiện, pipeline hoàn chỉnh

TUẦN 5-8: Giai đoạn 2 chạy ổn định
  □ backtest.py — theo dõi accuracy liên tục
  □ Thêm Bybit/OKX cross-exchange
  □ Thêm Fear & Greed
  → KẾT QUẢ: Model có 100-200 điểm dữ liệu, signal có cơ sở hơn

THÁNG 2: Giai đoạn 3 (Web App)
  □ api_server.py (FastAPI)
  □ dashboard/index.html (chart + signal markers)
  → KẾT QUẢ: Có giao diện web hoàn chỉnh

THÁNG 2-3: Giai đoạn 4 (Mở rộng dữ liệu)
  □ Thêm các nguồn: Glassnode, sentiment...
  → KẾT QUẢ: Model có nhiều features hơn

THÁNG 3-6: Giai đoạn 5 (Nâng cấp model)
  □ Chỉ làm khi model hiện tại có đủ dữ liệu + accuracy ổn định
  □ Ensemble, NLP sentiment, multi-timeframe
```

---

## 9. CÁCH CHẠY HIỆN TẠI (Bot đã làm xong)

```bash
# 1. Cài dependencies
pip install -r requirements.txt

# 2. Cấu hình
cp .env.example .env
# Mở .env, điền:
# TELEGRAM_BOT_TOKEN=your_token
# FINNHUB_API_KEY=your_key

# 3. Chạy bot
python bot/bot.py

# 4. Mở Telegram, chat với bot của bạn:
# /start → xem hướng dẫn
# /forex → giá major pairs
# /crypto → BTC + ETH derivatives
# /crypto SOLUSDT → bất kỳ symbol Binance Futures nào
# /news → tin tức mới nhất
# /whale → cần cấu hình Whale Alert key
# /subscribe → nhận cập nhật mỗi giờ
```

---

*Tài liệu này sẽ được cập nhật sau mỗi giai đoạn hoàn thành.*

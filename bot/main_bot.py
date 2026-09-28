"""
main_bot.py — Bot Telegram tổng hợp dữ liệu Forex + Crypto + ML Signals.

CHẠY: python -m bot.main_bot  (từ thư mục gốc CrypT/)
HOẶC: python run_bot.py

YÊU CẦU: tạo file .env (xem env.example)
"""

import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from .database import CryptDB
from .data_provider import FinnhubClient, format_news_item
from .crypto_provider import BinanceFuturesClient, WhaleAlertClient, format_whale_tx, build_text_summary
from .bybit_provider import BybitClient, compare_funding_rates, format_cross_exchange_telegram
from .collector import collect_all, check_volatility_alerts, fetch_fear_greed, fear_greed_label
from .economic_calendar import (
    get_upcoming_high_impact,
    get_events_by_currency,
    hours_to_next_high_event,
    format_calendar_block,
    get_this_week_events,
)
from .labeler import label_snapshots, get_label_stats
from .signal import generate_signal, format_signal_telegram
from .backtest import check_signal_outcomes, format_accuracy_telegram
from .trainer import train_all_assets, load_latest_model

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─────────────── Config ───────────────

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
WHALE_ALERT_API_KEY = os.getenv("WHALE_ALERT_API_KEY", "")

WATCHLIST = [p.strip() for p in os.getenv(
    "WATCHLIST", "OANDA:EUR_USD,OANDA:GBP_USD,OANDA:USD_JPY"
).split(",") if p.strip()]

CRYPTO_WATCHLIST = [s.strip() for s in os.getenv(
    "CRYPTO_WATCHLIST", "BTCUSDT,ETHUSDT"
).split(",") if s.strip()]

ALERT_INTERVAL = int(os.getenv("ALERT_INTERVAL_SECONDS", "3600"))
ALERT_THRESHOLD = float(os.getenv("ALERT_THRESHOLD_PERCENT", "0.5"))
ALERT_FUNDING_THRESHOLD = float(os.getenv("ALERT_FUNDING_THRESHOLD", "0.1"))
ALERT_OI_THRESHOLD = float(os.getenv("ALERT_OI_THRESHOLD", "5.0"))
ALERT_WHALE_USD = float(os.getenv("ALERT_WHALE_USD", "50000000"))
ALERT_CHECK_INTERVAL = int(os.getenv("ALERT_CHECK_INTERVAL", "120"))

if not TELEGRAM_BOT_TOKEN:
    raise SystemExit("Missing TELEGRAM_BOT_TOKEN in .env")
if not FINNHUB_API_KEY:
    raise SystemExit("Missing FINNHUB_API_KEY in .env. Get free key at https://finnhub.io/register")

# ─────────────── Init Services ───────────────

db = CryptDB()
finnhub_client = FinnhubClient(FINNHUB_API_KEY, db=db)
binance_client = BinanceFuturesClient()
bybit_client = BybitClient()
whale_client = WhaleAlertClient(WHALE_ALERT_API_KEY) if WHALE_ALERT_API_KEY else None


# ─────────────── Helper format ───────────────

def _fmt_change(pct):
    if pct is None:
        return "—"
    arrow = "▲" if pct > 0 else "▼" if pct < 0 else "→"
    return f"{arrow} {pct:+.2f}%"


def format_forex_block(prices: dict) -> str:
    lines = ["*FOREX - Current prices (source: Finnhub)*"]
    for pair, info in prices.items():
        if "error" in info:
            lines.append(f"  {pair}: error ({info['error']})")
            continue
        lines.append(
            f"  {info['symbol']}: `{info['price']:.5f}` "
            f"| 1h: {_fmt_change(info['change_1h'])} "
            f"| 24h: {_fmt_change(info['change_24h'])}"
        )
    return "\n".join(lines)


def format_crypto_block(symbols: list[str]) -> str:
    lines = ["*CRYPTO - Funding / OI / Long-Short (source: Binance Futures)*"]
    for sym in symbols:
        summary = binance_client.get_summary(sym)
        lines.append(f"\n*{sym}*")
        lines.append(build_text_summary(sym, summary))
    return "\n".join(lines)


# ─────────────── Command handlers ───────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hello! Trading Intelligence Bot\n\n"
        "*Market data:*\n"
        "/forex - current major pairs\n"
        "/crypto BTCUSDT ETHUSDT - funding/OI/long-short\n"
        "/funding BTCUSDT - cross-exchange funding comparison\n"
        "/news - latest forex news\n"
        "/whale - large on-chain transactions\n\n"
        "*Summary:*\n"
        "/summary - all-in-one summary\n"
        "/calendar - upcoming macro events\n\n"
        "*ML Signals (needs data):*\n"
        "/signal BTCUSDT - ML signal with probability\n"
        "/accuracy - model win rate tracking\n\n"
        "*Admin:*\n"
        "/dbstats - database statistics\n\n"
        "*Subscribe:*\n"
        "/subscribe - get updates + alerts\n"
        "/unsubscribe - stop updates\n\n"
        "Bot provides data + ML suggestions, NOT financial advice.\n"
        "You decide all trades.",
        parse_mode="Markdown",
    )


async def cmd_forex(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Fetching forex data...")
    try:
        prices = finnhub_client.get_watchlist_prices(WATCHLIST)
        text = format_forex_block(prices)
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        logger.exception("Error /forex")
        await update.message.reply_text(f"Error fetching forex data: {e}")


async def cmd_crypto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbols = [s.upper() for s in context.args] if context.args else CRYPTO_WATCHLIST
    await update.message.reply_text(f"Fetching crypto data for {', '.join(symbols)}...")
    try:
        text = format_crypto_block(symbols)
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        logger.exception("Error /crypto")
        await update.message.reply_text(f"Error fetching crypto data: {e}")


async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Fetching news...")
    try:
        items = finnhub_client.get_forex_news(limit=6)
        if not items:
            await update.message.reply_text("No recent news.")
            return
        text = "*Latest forex news*\n\n" + "\n\n".join(format_news_item(i) for i in items)
        await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)
    except Exception as e:
        logger.exception("Error /news")
        await update.message.reply_text(f"Error fetching news: {e}")


async def cmd_whale(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if whale_client is None:
        await update.message.reply_text(
            "WHALE_ALERT_API_KEY not configured in .env.\n"
            "Get free key at https://whale-alert.io/ then add to .env."
        )
        return
    await update.message.reply_text("Fetching large transactions...")
    try:
        txs = whale_client.get_recent_transactions(min_value_usd=1000000, minutes_back=60)
        if isinstance(txs, dict) and "error" in txs:
            await update.message.reply_text(txs["error"])
            return
        if not txs:
            await update.message.reply_text("No large transactions in last 60 minutes (>$1M).")
            return
        text = "*Large on-chain transactions (>$1M, 60m)*\n\n" + "\n".join(
            format_whale_tx(t) for t in txs[:10]
        )
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        logger.exception("Error /whale")
        await update.message.reply_text(f"Error fetching whale data: {e}")


async def cmd_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/summary - all-in-one market summary."""
    await update.message.reply_text("Compiling market summary...")

    from datetime import datetime, timezone
    now_str = datetime.now(timezone.utc).strftime("%H:%M UTC")
    sections = [f"*MARKET SUMMARY - {now_str}*"]

    # 1. Forex
    try:
        prices = finnhub_client.get_watchlist_prices(WATCHLIST)
        lines = ["\n*FOREX:*"]
        for pair, info in prices.items():
            if "error" in info:
                continue
            lines.append(
                f"  {info['symbol']}: `{info['price']:.5f}` "
                f"| 1h: {_fmt_change(info['change_1h'])} "
                f"| 24h: {_fmt_change(info['change_24h'])}"
            )
        sections.append("\n".join(lines))
    except Exception as e:
        sections.append(f"\n*FOREX:* Error ({e})")

    # 2. Crypto Derivatives
    try:
        for sym in CRYPTO_WATCHLIST:
            summary = binance_client.get_summary(sym)
            sections.append(f"\n*CRYPTO ({sym}):*")
            funding = summary.get("funding", {})
            oi = summary.get("oi_change_1h", {})
            ls = summary.get("long_short", {})

            if funding:
                fr = funding.get("last_funding_rate", 0)
                sections.append(f"  Funding: {fr:+.4f}%")
            if oi:
                chg = oi.get("oi_change_percent", 0)
                sections.append(f"  OI: {'+' if chg > 0 else ''}{chg:.1f}% (1h)")
            if ls:
                ratio = ls.get("long_short_ratio", 1)
                long_pct = ls.get("long_account_pct", 50)
                sections.append(f"  L/S ratio: {ratio:.2f} ({long_pct:.0f}% long)")
    except Exception as e:
        sections.append(f"\n*CRYPTO:* Error ({e})")

    # 3. Fear & Greed
    try:
        fg = fetch_fear_greed()
        sections.append(f"\n*SENTIMENT:* Fear & Greed = {fear_greed_label(fg)}")
    except Exception:
        pass

    # 4. Calendar
    try:
        upcoming = get_upcoming_high_impact(hours=24)
        if upcoming:
            ev = upcoming[0]
            title = ev.get("title", "?")
            country = ev.get("country", "?")
            h_left = hours_to_next_high_event()
            if h_left is not None:
                sections.append(f"\n*UPCOMING EVENT:* {country} {title} ({h_left:.1f}h)")
            else:
                sections.append(f"\n*UPCOMING EVENT:* {country} {title}")
        else:
            sections.append("\n*EVENTS:* No High impact events in 24h")
    except Exception:
        pass

    # 5. Whale
    if whale_client:
        try:
            txs = whale_client.get_recent_transactions(min_value_usd=1000000, minutes_back=60)
            if isinstance(txs, list) and txs:
                sections.append(f"\n*WHALE (1h):* {len(txs)} large transactions")
                for tx in txs[:3]:
                    sections.append(format_whale_tx(tx))
        except Exception:
            pass

    sections.append("\nData for reference only, not trading advice.")

    full_text = "\n".join(sections)
    if len(full_text) > 4000:
        full_text = full_text[:3990] + "\n..."

    await update.message.reply_text(full_text, parse_mode="Markdown", disable_web_page_preview=True)


async def cmd_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/calendar [currency] - upcoming macro events."""
    try:
        if context.args:
            arg = context.args[0].upper()
            if arg == "ALL":
                events = get_this_week_events()
                title = "All events this week"
            else:
                events = get_events_by_currency(arg)
                title = f"{arg} events this week"
        else:
            events = get_upcoming_high_impact(hours=48)
            title = "High/Medium impact events (48h)"

        text = format_calendar_block(events, title)
        if len(text) > 4000:
            text = text[:3990] + "\n..."

        await update.message.reply_text(text, disable_web_page_preview=True)
    except Exception as e:
        logger.exception("Error /calendar")
        await update.message.reply_text(f"Error fetching calendar: {e}")


async def cmd_signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/signal BTCUSDT - ML signal."""
    asset = context.args[0].upper() if context.args else "BTCUSDT"
    await update.message.reply_text(f"Analyzing {asset}...")
    try:
        signal_info = generate_signal(db, asset)
        text = format_signal_telegram(signal_info)
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        logger.exception("Error /signal")
        await update.message.reply_text(f"Error: {e}")


async def cmd_accuracy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/accuracy - model win rate."""
    try:
        text = format_accuracy_telegram(db, CRYPTO_WATCHLIST)
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        logger.exception("Error /accuracy")
        await update.message.reply_text(f"Error: {e}")


async def cmd_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.add_subscriber(update.effective_chat.id)
    await update.message.reply_text(
        f"Subscribed to updates every {ALERT_INTERVAL//60} minutes + volatility alerts.\n"
        f"Use /unsubscribe to stop."
    )


async def cmd_unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.remove_subscriber(update.effective_chat.id)
    await update.message.reply_text("Unsubscribed from periodic updates.")


async def cmd_funding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/funding BTCUSDT - cross-exchange funding rate comparison."""
    symbols = [s.upper() for s in context.args] if context.args else CRYPTO_WATCHLIST
    await update.message.reply_text(f"Comparing funding rates for {', '.join(symbols)}...")
    try:
        lines = ["*CROSS-EXCHANGE FUNDING RATES*\n"]
        for sym in symbols:
            # Get Binance funding
            binance_summary = binance_client.get_summary(sym)
            binance_fr = binance_summary.get("funding", {}).get("last_funding_rate")

            # Get Bybit funding
            bybit_data = bybit_client.get_funding_rate(sym)

            comparison = compare_funding_rates(binance_fr, bybit_data)
            lines.append(format_cross_exchange_telegram(sym, comparison))
            lines.append("")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.exception("Error /funding")
        await update.message.reply_text(f"Error: {e}")


async def cmd_dbstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/dbstats - database statistics."""
    try:
        stats = db.get_db_stats()
        lines = ["*DATABASE STATISTICS*\n"]
        for table, count in stats.items():
            if table == "db_size_mb":
                lines.append(f"  DB Size: {count} MB")
            else:
                lines.append(f"  {table}: {count:,} rows")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.exception("Error /dbstats")
        await update.message.reply_text(f"Error: {e}")


# ─────────────── Jobs (background) ───────────────

async def job_collect_data(context: ContextTypes.DEFAULT_TYPE):
    try:
        result = collect_all(
            db=db, finnhub=finnhub_client, binance=binance_client,
            whale=whale_client, bybit=bybit_client,
            forex_watchlist=WATCHLIST, crypto_symbols=CRYPTO_WATCHLIST,
        )
        logger.info(
            f"Collected: forex={result['forex_count']}, crypto={result['crypto_count']}, "
            f"bybit={result['bybit_count']}, news={result['news_count']}, "
            f"whale={result['whale_count']}, FG={result['fear_greed']}, "
            f"calendar={result['calendar_count']}"
        )
    except Exception as e:
        logger.exception(f"Error job_collect_data: {e}")


async def job_label_data(context: ContextTypes.DEFAULT_TYPE):
    try:
        stats = label_snapshots(db)
        if stats["labeled"] > 0:
            logger.info(f"Labeled: {stats}")
    except Exception as e:
        logger.exception(f"Error job_label_data: {e}")


async def job_check_outcomes(context: ContextTypes.DEFAULT_TYPE):
    try:
        stats = check_signal_outcomes(db)
        if stats["checked"] > 0:
            logger.info(f"Signal outcomes: {stats}")
    except Exception as e:
        logger.exception(f"Error job_check_outcomes: {e}")


async def job_train_model(context: ContextTypes.DEFAULT_TYPE):
    try:
        results = train_all_assets(db, CRYPTO_WATCHLIST)
        for r in results:
            if "error" in r:
                logger.info(f"Train {r['asset']}: {r['error']}")
            else:
                logger.info(
                    f"Train {r['asset']}: {r['n_samples']} samples, "
                    f"test_acc={r.get('accuracy_test', 'N/A')}%"
                )
    except Exception as e:
        logger.exception(f"Error job_train_model: {e}")


async def job_check_alerts(context: ContextTypes.DEFAULT_TYPE):
    try:
        alerts = check_volatility_alerts(
            db=db, binance=binance_client, forex_watchlist=WATCHLIST,
            crypto_symbols=CRYPTO_WATCHLIST, threshold_price=ALERT_THRESHOLD,
            threshold_funding=ALERT_FUNDING_THRESHOLD, threshold_oi=ALERT_OI_THRESHOLD,
            threshold_whale_usd=ALERT_WHALE_USD,
        )
        if not alerts:
            return

        subscribers = db.get_subscribers()
        if not subscribers:
            return

        alert_text = "*VOLATILITY ALERT*\n\n" + "\n\n".join(alerts)
        alert_text += "\n\nThis is a volatility alert, not a buy/sell signal."

        for chat_id in subscribers:
            try:
                await context.bot.send_message(chat_id=chat_id, text=alert_text, parse_mode="Markdown")
            except Exception as e:
                logger.warning(f"Cannot send alert to {chat_id}: {e}")
    except Exception as e:
        logger.exception(f"Error job_check_alerts: {e}")


async def job_periodic_update(context: ContextTypes.DEFAULT_TYPE):
    subscribers = db.get_subscribers()
    if not subscribers:
        return

    try:
        prices = finnhub_client.get_watchlist_prices(WATCHLIST)
        forex_text = format_forex_block(prices)
    except Exception as e:
        forex_text = f"Error fetching forex: {e}"

    try:
        crypto_text = format_crypto_block(CRYPTO_WATCHLIST)
    except Exception as e:
        crypto_text = f"Error fetching crypto: {e}"

    fg_text = ""
    try:
        fg = fetch_fear_greed()
        if fg is not None:
            fg_text = f"\n\n*Sentiment:* Fear & Greed = {fear_greed_label(fg)}"
    except Exception:
        pass

    full_text = (
        f"*Periodic Update*\n\n"
        f"{forex_text}\n\n{crypto_text}{fg_text}\n\n"
        f"Data for reference only, not trading advice."
    )

    if len(full_text) > 4000:
        full_text = full_text[:3990] + "\n..."

    for chat_id in subscribers:
        try:
            await context.bot.send_message(chat_id=chat_id, text=full_text, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Cannot send update to {chat_id}: {e}")


async def job_cleanup(context: ContextTypes.DEFAULT_TYPE):
    try:
        db.cleanup_old(days=60)
        logger.info("Cleanup old data done")
    except Exception as e:
        logger.exception(f"Error cleanup: {e}")


# ─────────────── Main ───────────────

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("forex", cmd_forex))
    app.add_handler(CommandHandler("crypto", cmd_crypto))
    app.add_handler(CommandHandler("funding", cmd_funding))
    app.add_handler(CommandHandler("news", cmd_news))
    app.add_handler(CommandHandler("whale", cmd_whale))
    app.add_handler(CommandHandler("summary", cmd_summary))
    app.add_handler(CommandHandler("calendar", cmd_calendar))
    app.add_handler(CommandHandler("signal", cmd_signal))
    app.add_handler(CommandHandler("accuracy", cmd_accuracy))
    app.add_handler(CommandHandler("dbstats", cmd_dbstats))
    app.add_handler(CommandHandler("subscribe", cmd_subscribe))
    app.add_handler(CommandHandler("unsubscribe", cmd_unsubscribe))

    # Scheduled Jobs
    app.job_queue.run_repeating(job_collect_data, interval=3600, first=10)
    app.job_queue.run_repeating(job_label_data, interval=3600, first=60)
    app.job_queue.run_repeating(job_check_outcomes, interval=3600, first=120)
    app.job_queue.run_repeating(job_train_model, interval=86400, first=300)
    app.job_queue.run_repeating(job_check_alerts, interval=ALERT_CHECK_INTERVAL, first=30)
    app.job_queue.run_repeating(job_periodic_update, interval=ALERT_INTERVAL, first=ALERT_INTERVAL)
    app.job_queue.run_repeating(job_cleanup, interval=86400, first=3600)

    logger.info("========================================")
    logger.info("  Trading Intelligence Bot running...")
    logger.info(f"  Forex watchlist: {WATCHLIST}")
    logger.info(f"  Crypto watchlist: {CRYPTO_WATCHLIST}")
    logger.info(f"  Alert interval: {ALERT_INTERVAL}s")
    logger.info(f"  Whale Alert: {'yes' if whale_client else 'no'}")
    logger.info(f"  Bybit: yes")
    logger.info(f"  DB: PostgreSQL")
    logger.info("========================================")

    app.run_polling()


if __name__ == "__main__":
    main()

"""
run.py --- Chay toan bo Trading Intelligence System bang 1 lenh duy nhat.

Usage: python run.py

Se khoi dong:
1. API Server (FastAPI + Dashboard) tren port 8877
2. Telegram Bot (polling)
3. Tu dong mo browser dashboard

Tat ca chay trong 1 process, Ctrl+C de dung tat ca.
"""

import os
import sys
import time
import signal
import logging
import threading
import webbrowser

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("run")


def start_api_server(port: int = 8877):
    """Start FastAPI server in a thread."""
    import uvicorn
    from api.api_server import app

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    server.run()


def start_telegram_bot():
    """Start Telegram bot (blocking)."""
    from bot.main_bot import main
    main()


def main():
    port = int(os.getenv("API_PORT", "8877"))

    print("=" * 50)
    print("  Trading Intelligence System")
    print("=" * 50)
    print()

    # Check required env vars
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    finnhub = os.getenv("FINNHUB_API_KEY", "")
    db_url = os.getenv("DATABASE_URL", "")

    missing = []
    if not token:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not finnhub:
        missing.append("FINNHUB_API_KEY")
    if not db_url:
        missing.append("DATABASE_URL")

    if missing:
        print(f"  MISSING in .env: {', '.join(missing)}")
        print("  Fix .env and try again.")
        sys.exit(1)

    print(f"  Telegram Bot: starting...")
    print(f"  API Server:   http://localhost:{port}")
    print(f"  Dashboard:    http://localhost:{port}/dashboard/index.html")
    print(f"  API Docs:     http://localhost:{port}/docs")
    print()
    print("  Press Ctrl+C to stop everything")
    print("=" * 50)

    # Start API in background thread
    api_thread = threading.Thread(
        target=start_api_server,
        args=(port,),
        daemon=True,
        name="api-server",
    )
    api_thread.start()
    logger.info(f"API server starting on port {port}")

    # Wait a moment then open browser
    def open_browser():
        time.sleep(2)
        url = f"http://localhost:{port}/dashboard/index.html"
        webbrowser.open(url)
        logger.info(f"Browser opened: {url}")

    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()

    # Start Telegram bot (blocking - runs in main thread)
    try:
        start_telegram_bot()
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        logger.error(f"Bot error: {e}")
        # Keep API running even if bot fails
        print(f"\nBot failed: {e}")
        print(f"API still running at http://localhost:{port}")
        print("Press Ctrl+C to stop API")
        try:
            api_thread.join()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()

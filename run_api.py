"""
Entry point — Chạy API server + Web Dashboard.
Usage: python run_api.py
Dashboard: http://localhost:8877/dashboard/index.html
"""
import os
import sys
import uvicorn
from dotenv import load_dotenv

load_dotenv()

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.api_server import app

if __name__ == "__main__":
    port = int(os.getenv("API_PORT", "8877"))
    print(f"Starting Trading Intelligence API on port {port}")
    print(f"Dashboard: http://localhost:{port}/dashboard/index.html")
    uvicorn.run(app, host="127.0.0.1", port=port)

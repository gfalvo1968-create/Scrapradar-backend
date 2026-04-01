from fastapi import FastAPI
import yfinance as yf
import numpy as np
import sqlite3
from contextlib import closing

print("Backend file loaded successfully")

# ------------------------
# APP SETUP
# ------------------------
app = FastAPI()

# ------------------------
# DATA STORAGE (Stage 1)
# ------------------------
manual_prices = []

DB_NAME = "scrapradar.db"

def init_db():
    with closing(sqlite3.connect(DB_NAME)) as conn:
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS prices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    metal TEXT NOT NULL,
                    price REAL NOT NULL,
                    yard TEXT NOT NULL
                )
            """)

init_db()
# ------------------------
# STATIC DATA
# ------------------------
yards = [
    {"name": "Langley Recycling", "lat": 34.5, "lng": -78.8, "base_price": 2.50},
    {"name": "Metro Scrap", "lat": 34.3, "lng": -78.7, "base_price": 2.30},
]

# ------------------------
# LIVE DATA FUNCTION
# ------------------------
def get_copper_series():
    copper = yf.Ticker("HG=F")
    data = copper.history(period="7d")["Close"]
    return list(data)

# ------------------------
# SIMPLE TREND LOGIC
# ------------------------
def predict_prices(prices):
    x = np.arange(len(prices))
    y = np.array(prices)

    coeffs = np.polyfit(x, y, 1)
    trend = coeffs[0]

    future = []
    for i in range(1, 4):
        future.append(float(y[-1] + trend * i))

    return future, trend

# ------------------------
# ROUTES
# ------------------------

# Home
@app.get("/")
def home():
    return {"status": "scrapradar is live 🚀"}

# Add manual price (Stage 1 core)
@app.post("/add-price")
def add_price(data: dict):
    manual_prices.append(data)
    return {"status": "saved"}

# Market data (combined)
@app.get("/market")
def market():
    copper_prices = get_copper_series()
    future, trend = predict_prices(copper_prices)

    return {
        "current": copper_prices[-1],
        "forecast": future,
        "trend": trend,
        "manual_entries": manual_prices
    }


# Yards
@app.get("/yards")
def get_yards():
    return yards

# Decision logic
@app.get("/decision")
def decision():
    if not manual_prices:
        return {"decision": "No data yet"}

    latest = manual_prices[-1]

    if latest.get("price", 0) > 4:
        return {"decision": "SELL NOW"}
    else:
        return {"decision": "HOLD"}

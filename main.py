from fastapi import FastAPI
import yfinance as yf
import numpy as np

print("Backend file loaded successfully")

app = FastAPI()

yards = [
    {"name": "Langley Recycling", "lat": 34.5, "lng": -78.8, "base_price": 2.50},
    {"name": "Metro Scrap", "lat": 34.3, "lng": -78.7, "base_price": 2.30},
]

manual_prices = []

def get_copper_series():
    copper = yf.Ticker("HG=F")
    data = copper.history(period="7d")["Close"]
    return list(data)

def predict_prices(prices):
    x = np.arange(len(prices))
    y = np.array(prices)
    coeffs = np.polyfit(x, y, 1)
    trend = coeffs[0]

    future = []
    for i in range(1, 4):
        future.append(float(y[-1] + trend * i))

    return future, trend

@app.get("/market")
def market():
    series = get_copper_series()
    future, trend = predict_prices(series)

    return {
        "current": series[-1],
        "forecast": future,
        "trend": trend
    }

@app.post("/add-price")
def add_price(data: dict):
    manual_prices.append(data)
    return {"status": "saved"}

@app.get("/yards")
def get_yards():
    series = get_copper_series()
    current = series[-1]

    enriched = []

    for y in yards:
        adjusted = y["base_price"] * (current / 4.0)

        override = next(
            (m for m in manual_prices if m["name"] == y["name"]),
            None
        )

        if override:
            adjusted = override["price"]

        enriched.append({
            "name": y["name"],
            "lat": y["lat"],
            "lng": y["lng"],
            "price": round(adjusted, 2),
            "profit": int(adjusted * 800),
            "manual": override is not None
        })

    return enriched

@app.get("/decision")
def decision():
    series = get_copper_series()
    future, trend = predict_prices(series)

    yard_list = get_yards()
    best = max(yard_list, key=lambda x: x["profit"])

    action = "WAIT" if trend > 0 else "GO SELL"

    return {
        "action": action,
        "yard": best["name"],
        "profit": best["profit"],
        "forecast": future
    }
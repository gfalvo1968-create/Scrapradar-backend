from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from datetime import datetime, timezone
import time
import yfinance as yf

app = FastAPI(title="Scrap Radar Market API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Yahoo Finance futures/reference symbols.
# These are market reference prices, not scrap-yard payout prices.
MARKET_SYMBOLS = {
    "gold": {"ticker": "GC=F", "unit": "troy_oz", "symbol": "XAU"},
    "silver": {"ticker": "SI=F", "unit": "troy_oz", "symbol": "XAG"},
    "copper": {"ticker": "HG=F", "unit": "lb", "symbol": "XCU"},
    "platinum": {"ticker": "PL=F", "unit": "troy_oz", "symbol": "XPT"},
    "palladium": {"ticker": "PA=F", "unit": "troy_oz", "symbol": "XPD"},
}

PRICE_CACHE_TTL_SECONDS = 60
_price_cache = {"timestamp": 0.0, "payload": None}


def _latest_close(ticker_symbol):
    ticker = yf.Ticker(ticker_symbol)
    data = ticker.history(period="5d", interval="1d")
    if data.empty or "Close" not in data:
        return None
    prices = data["Close"].dropna().tolist()
    if not prices:
        return None
    return round(float(prices[-1]), 4)


def _build_prices_payload():
    metals = {}
    available = 0

    for name, config in MARKET_SYMBOLS.items():
        try:
            price = _latest_close(config["ticker"])
        except Exception as exc:
            print(f"[Price Feed Error] {name}: {exc}")
            price = None

        is_available = price is not None
        if is_available:
            available += 1

        metals[name] = {
            "symbol": config["symbol"],
            "ticker": config["ticker"],
            "price": price,
            "currency": "USD",
            "unit": config["unit"],
            "available": is_available,
        }

    return {
        "status": "live" if available else "unavailable",
        "source": "Yahoo Finance futures/reference market data",
        "price_type": "market_reference",
        "currency": "USD",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "available_metals": available,
        "metals": metals,
        "note": "Market reference prices are not scrap-yard payout prices.",
    }


@app.get("/prices")
def prices():
    now = time.time()

    if (
        _price_cache["payload"] is not None
        and now - _price_cache["timestamp"] < PRICE_CACHE_TTL_SECONDS
    ):
        payload = dict(_price_cache["payload"])
        payload["cache"] = "hit"
        return payload

    payload = _build_prices_payload()
    _price_cache["timestamp"] = now
    _price_cache["payload"] = payload

    response = dict(payload)
    response["cache"] = "miss"
    return response


# ---------------- EXISTING COPPER MARKET API ----------------
@app.get("/market")
def market():
    ticker = yf.Ticker("HG=F")
    data = ticker.history(period="5d")

    prices = data["Close"].dropna().tolist()

    if len(prices) < 3:
        return {"error": "Not enough data"}

    current = round(float(prices[-1]), 3)
    forecast = [round(float(p) * 1.01, 4) for p in prices[-3:]]
    trend = round((float(prices[-1]) - float(prices[0])) / float(prices[0]), 3)

    return {
        "current": current,
        "forecast": forecast,
        "trend": trend,
    }


# ---------------- DASHBOARD ----------------
@app.get("/", response_class=HTMLResponse)
def home():
    return """
<!DOCTYPE html>
<html>
<head>
    <title>ScrapRadar Market API</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
</head>
<body style="font-family:Arial;padding:20px;background:#111;color:#0f0;">
    <h1>📡 Scrap Radar Market API</h1>
    <p>Central live/reference pricing service for Scrap Radar Family.</p>
    <p><a href="/prices" style="color:#00d4ff;">Open /prices JSON</a></p>
    <p><a href="/market" style="color:#00d4ff;">Open legacy copper /market JSON</a></p>
    <pre id="output" style="background:#000;padding:12px;color:#0f0;">Loading prices...</pre>
    <script>
    fetch('/prices?nocache=' + Date.now())
      .then(r => r.json())
      .then(data => document.getElementById('output').innerText = JSON.stringify(data, null, 2))
      .catch(() => document.getElementById('output').innerText = 'Error loading prices');
    </script>
</body>
</html>
"""

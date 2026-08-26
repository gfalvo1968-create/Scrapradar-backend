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

MARKET_SYMBOLS = {
    "gold": {"ticker": "GC=F", "unit": "troy_oz", "symbol": "XAU"},
    "silver": {"ticker": "SI=F", "unit": "troy_oz", "symbol": "XAG"},
    "copper": {"ticker": "HG=F", "unit": "lb", "symbol": "XCU"},
    "platinum": {"ticker": "PL=F", "unit": "troy_oz", "symbol": "XPT"},
    "palladium": {"ticker": "PA=F", "unit": "troy_oz", "symbol": "XPD"},
}

PRICE_CACHE_TTL_SECONDS = 60
_price_cache = {"timestamp": 0.0, "payload": None}


def _history(ticker_symbol, period="1mo"):
    data = yf.Ticker(ticker_symbol).history(period=period, interval="1d")
    if data.empty or "Close" not in data:
        return []
    return [float(p) for p in data["Close"].dropna().tolist()]


def _market_intelligence(prices):
    if len(prices) < 5:
        return {
            "trend": "UNKNOWN",
            "signal": "WAIT FOR DATA",
            "confidence": 0,
            "change_5d_pct": None,
            "change_20d_pct": None,
            "position_20d": None,
            "forecast_note": "Not enough market history for a useful trend signal.",
        }

    current = prices[-1]
    five_start = prices[-5]
    twenty_window = prices[-20:] if len(prices) >= 20 else prices
    twenty_start = twenty_window[0]
    low20 = min(twenty_window)
    high20 = max(twenty_window)

    change5 = ((current - five_start) / five_start) * 100 if five_start else 0
    change20 = ((current - twenty_start) / twenty_start) * 100 if twenty_start else 0
    position = ((current - low20) / (high20 - low20)) if high20 > low20 else 0.5

    if change5 > 1.0 and change20 > 1.5:
        trend = "RISING"
    elif change5 < -1.0 and change20 < -1.5:
        trend = "FALLING"
    else:
        trend = "SIDEWAYS"

    # Conservative decision support, not a guarantee or trading instruction.
    if trend == "RISING" and position < 0.90:
        signal = "HOLD / WATCH"
        note = "Momentum is positive and the market is not yet at the top of its recent range. Watch for continued strength or a reversal."
    elif position >= 0.90 and change5 <= 0.5:
        signal = "FAVORABLE SELL WINDOW"
        note = "Price is near the top of its recent range while short-term momentum is flattening or weakening."
    elif trend == "FALLING":
        signal = "SELL / PROTECT VALUE"
        note = "Recent momentum is negative. Selling sooner may reduce exposure to further weakness."
    else:
        signal = "WATCH"
        note = "The market does not show a strong directional edge right now."

    strength = min(abs(change5) * 8 + abs(change20) * 3, 45)
    range_certainty = abs(position - 0.5) * 30
    confidence = int(max(35, min(85, 40 + strength + range_certainty)))

    return {
        "trend": trend,
        "signal": signal,
        "confidence": confidence,
        "change_5d_pct": round(change5, 2),
        "change_20d_pct": round(change20, 2),
        "position_20d": round(position, 3),
        "forecast_note": note,
    }


def _build_prices_payload():
    metals = {}
    available = 0

    for name, config in MARKET_SYMBOLS.items():
        try:
            history = _history(config["ticker"], "1mo")
            price = round(history[-1], 4) if history else None
            intelligence = _market_intelligence(history)
        except Exception as exc:
            print(f"[Price Feed Error] {name}: {exc}")
            price = None
            intelligence = _market_intelligence([])

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
            "intelligence": intelligence,
        }

    return {
        "status": "live" if available else "unavailable",
        "source": "Yahoo Finance futures/reference market data",
        "price_type": "market_reference",
        "currency": "USD",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "available_metals": available,
        "metals": metals,
        "note": "Market reference prices are not scrap-yard payout prices. Trend and sell/hold signals are decision-support estimates, not guarantees.",
    }


@app.get("/prices")
def prices():
    now = time.time()
    if _price_cache["payload"] is not None and now - _price_cache["timestamp"] < PRICE_CACHE_TTL_SECONDS:
        payload = dict(_price_cache["payload"])
        payload["cache"] = "hit"
        return payload

    payload = _build_prices_payload()
    _price_cache["timestamp"] = now
    _price_cache["payload"] = payload
    response = dict(payload)
    response["cache"] = "miss"
    return response


@app.get("/market")
def market():
    prices = _history("HG=F", "1mo")
    if len(prices) < 5:
        return {"error": "Not enough data"}
    return {
        "current": round(prices[-1], 4),
        "intelligence": _market_intelligence(prices),
    }


@app.get("/", response_class=HTMLResponse)
def home():
    return """
<!DOCTYPE html>
<html>
<head><title>ScrapRadar Market API</title><meta name="viewport" content="width=device-width, initial-scale=1" /></head>
<body style="font-family:Arial;padding:20px;background:#111;color:#0f0;">
<h1>📡 Scrap Radar Market API</h1>
<p>Central market pricing, trend and sell-window intelligence for Scrap Radar Family.</p>
<p><a href="/prices" style="color:#00d4ff;">Open /prices JSON</a></p>
<pre id="output" style="background:#000;padding:12px;color:#0f0;">Loading prices...</pre>
<script>
fetch('/prices?nocache=' + Date.now()).then(r=>r.json()).then(data=>document.getElementById('output').innerText=JSON.stringify(data,null,2)).catch(()=>document.getElementById('output').innerText='Error loading prices');
</script>
</body>
</html>
"""

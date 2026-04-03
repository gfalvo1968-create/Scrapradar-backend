from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import yfinance as yf

app = FastAPI()

@app.get("/market")
def market():
    ticker = yf.Ticker("HG=F")
    data = ticker.history(period="5d")
    prices = data["Close"].tolist()

    if len(prices) < 3:
        return {"error": "Not enough data"}

    current = round(prices[-1], 3)
    forecast = [round(p * 1.01, 4) for p in prices[-3:]]
    trend = round((prices[-1] - prices[0]) / prices[0], 3)

    return {
        "current": current,
        "forecast": forecast,
        "trend": trend
    }

@app.get("/", response_class=HTMLResponse)
def home():
    return """
<!DOCTYPE html>
<html>
<head>
    <title>ScrapRadar Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
</head>
<body style="font-family: Arial; padding: 20px; background:#111; color:#0f0;">

<h1>ScrapRadar Dashboard</h1>

<button onclick="loadData()" style="padding:10px; font-size:16px;">
    Load Market Data
</button>

<pre id="output" style="margin-top:20px; background:#000; padding:10px; color:#0f0;">
Waiting...
</pre>

<script>
async function loadData() {
    try {
        const res = await fetch('/market');
        const data = await res.json();
        document.getElementById('output').innerText =
            JSON.stringify(data, null, 2);
    } catch (err) {
        document.getElementById('output').innerText = "Error loading data";
    }
}
</script>

</body>
</html>
"""

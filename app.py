from flask import Flask, jsonify
import yfinance as yf
from datetime import datetime, timedelta
import time

app = Flask(__name__)

SYMBOL = "^SET.BK"

CACHE_SECONDS = 60

cached_today = None
cached_time = 0
last_error = ""

def get_last_digit(value):
    text = str(value)
    digits = "".join(ch for ch in text if ch.isdigit())

    if len(digits) == 0:
        return "0"

    return digits[-1]

def get_set_decimal_two(close_price):
    set_text = f"{close_price:.2f}"
    decimal_part = set_text.split(".")[1]
    return decimal_part[-2:]

def fetch_market_data():
    ticker = yf.Ticker(SYMBOL)

    hist = ticker.history(period="1d", interval="1m")

    if hist is None or hist.empty:
        raise Exception("No market data found")

    hist = hist.dropna()

    if hist.empty:
        raise Exception("No valid market data found")

    last_row = hist.tail(1).iloc[0]

    close_price = float(last_row["Close"])

    try:
        market_value = int(last_row["Volume"])
    except:
        market_value = 0

    set_decimal_two = get_set_decimal_two(close_price)

    set_last_digit = set_decimal_two[-1]
    value_last_digit = get_last_digit(market_value)

    result_2d = set_last_digit + value_last_digit

    thailand_time = datetime.utcnow() + timedelta(hours=7)

    return {
        "success": True,
        "date": thailand_time.strftime("%Y-%m-%d"),
        "symbol": SYMBOL,

        "set": f"{close_price:.2f}",
        "value": str(market_value),

        "setDecimalTwo": set_decimal_two,
        "setLastDigit": set_last_digit,
        "valueLastDigit": value_last_digit,

        "result2d": result_2d,
        "morningResult": result_2d,
        "eveningResult": result_2d,

        "updatedAt": thailand_time.strftime("%Y-%m-%d %H:%M:%S"),
        "cached": False
    }

@app.route("/")
def home():
    return jsonify({
        "success": True,
        "message": "YFinance SET API running with cache"
    })

@app.route("/today")
def today():
    global cached_today
    global cached_time
    global last_error

    now_time = time.time()

    if cached_today is not None and now_time - cached_time < CACHE_SECONDS:
        cached_today["cached"] = True
        cached_today["lastError"] = last_error
        return jsonify(cached_today)

    try:
        fresh_data = fetch_market_data()

        cached_today = fresh_data
        cached_time = now_time
        last_error = ""

        return jsonify(fresh_data)

    except Exception as e:
        last_error = str(e)

        if cached_today is not None:
            cached_today["cached"] = True
            cached_today["lastError"] = last_error
            return jsonify(cached_today)

        return jsonify({
            "success": False,
            "message": last_error
        }), 429

@app.route("/status")
def status():
    thailand_time = datetime.utcnow() + timedelta(hours=7)
    current = thailand_time.hour * 60 + thailand_time.minute

    morning_open = 420
    morning_close = 715

    evening_open = 765
    evening_close = 955

    market_status = "CLOSE"
    session = "none"

    if current >= morning_open and current <= morning_close:
        market_status = "OPEN"
        session = "morning"
    elif current >= evening_open and current <= evening_close:
        market_status = "OPEN"
        session = "evening"

    return jsonify({
        "success": True,
        "status": market_status,
        "session": session,
        "current": current,
        "time": thailand_time.strftime("%H:%M:%S")
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)

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


def thailand_now():
    return datetime.utcnow() + timedelta(hours=7)


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


def get_market_session():
    now = thailand_now()
    current = now.hour * 60 + now.minute

    # User requested time
    morning_open = 480      # 08:00 AM
    morning_close = 721     # 12:01 PM

    evening_open = 780      # 01:00 PM
    evening_close = 991     # 04:31 PM

    status = "CLOSE"
    session = "none"
    display_session = "none"

    if current >= morning_open and current <= morning_close:
        status = "OPEN"
        session = "morning"
        display_session = "morning"

    elif current > morning_close and current < evening_open:
        status = "CLOSE"
        session = "none"
        display_session = "morning"

    elif current >= evening_open and current <= evening_close:
        status = "OPEN"
        session = "evening"
        display_session = "evening"

    elif current > evening_close:
        status = "CLOSE"
        session = "none"
        display_session = "evening"

    else:
        status = "CLOSE"
        session = "none"
        display_session = "none"

    return {
        "status": status,
        "session": session,
        "displaySession": display_session,
        "current": current,
        "time": now.strftime("%H:%M:%S"),
        "date": now.strftime("%Y-%m-%d")
    }


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

    session_info = get_market_session()
    display_session = session_info["displaySession"]

    morning_result = "--"
    evening_result = "--"

    if display_session == "morning":
        morning_result = result_2d
        evening_result = "--"

    elif display_session == "evening":
        morning_result = "--"
        evening_result = result_2d

    now = thailand_now()

    return {
        "success": True,
        "date": now.strftime("%Y-%m-%d"),
        "symbol": SYMBOL,

        "status": session_info["status"],
        "session": session_info["session"],
        "displaySession": session_info["displaySession"],

        "set": f"{close_price:.2f}",
        "value": str(market_value),

        "setDecimalTwo": set_decimal_two,
        "setLastDigit": set_last_digit,
        "valueLastDigit": value_last_digit,

        "result2d": result_2d,
        "morningResult": morning_result,
        "eveningResult": evening_result,

        "updatedAt": now.strftime("%Y-%m-%d %H:%M:%S"),
        "cached": False
    }


@app.route("/")
def home():
    return jsonify({
        "success": True,
        "message": "YFinance SET API running with session time 08:00-12:01 and 13:00-16:31"
    })


@app.route("/today")
def today():
    global cached_today
    global cached_time
    global last_error

    now_time = time.time()

    if cached_today is not None and now_time - cached_time < CACHE_SECONDS:
        response = dict(cached_today)
        response["cached"] = True
        response["lastError"] = last_error
        return jsonify(response)

    try:
        fresh_data = fetch_market_data()

        cached_today = fresh_data
        cached_time = now_time
        last_error = ""

        return jsonify(fresh_data)

    except Exception as e:
        last_error = str(e)

        if cached_today is not None:
            response = dict(cached_today)
            response["cached"] = True
            response["lastError"] = last_error
            return jsonify(response)

        return jsonify({
            "success": False,
            "message": last_error
        }), 429


@app.route("/status")
def status():
    session_info = get_market_session()

    return jsonify({
        "success": True,
        "status": session_info["status"],
        "session": session_info["session"],
        "displaySession": session_info["displaySession"],
        "current": session_info["current"],
        "time": session_info["time"],
        "date": session_info["date"]
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)

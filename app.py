from flask import Flask, jsonify
import yfinance as yf
from datetime import datetime, timedelta
import time

app = Flask(__name__)

SYMBOL = "^SET.BK"

# 10 seconds live cache
CACHE_SECONDS = 10

cached_today = None
cached_time = 0
last_error = ""


def myanmar_now():
    return datetime.utcnow() + timedelta(hours=6, minutes=30)


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
    now = myanmar_now()
    current = now.hour * 60 + now.minute

    # Myanmar Time
    # Morning: 08:00 AM - 12:01 PM
    morning_open = 480
    morning_close = 721

    # Evening: 01:00 PM - 04:31 PM
    evening_open = 780
    evening_close = 991

    status = "CLOSE"
    session = "none"
    display_session = "none"
    next_session = "Morning Session 08:00 AM"

    if current >= morning_open and current <= morning_close:
        status = "OPEN"
        session = "morning"
        display_session = "morning"
        next_session = "Evening Session 01:00 PM"

    elif current > morning_close and current < evening_open:
        status = "CLOSE"
        session = "none"
        display_session = "morning"
        next_session = "Evening Session 01:00 PM"

    elif current >= evening_open and current <= evening_close:
        status = "OPEN"
        session = "evening"
        display_session = "evening"
        next_session = "Tomorrow Morning 08:00 AM"

    elif current > evening_close:
        status = "CLOSE"
        session = "none"
        display_session = "evening"
        next_session = "Tomorrow Morning 08:00 AM"

    else:
        status = "CLOSE"
        session = "none"
        display_session = "none"
        next_session = "Morning Session 08:00 AM"

    return {
        "status": status,
        "session": session,
        "displaySession": display_session,
        "nextSession": next_session,
        "current": current,
        "time": now.strftime("%H:%M:%S"),
        "date": now.strftime("%Y-%m-%d")
    }


def build_result_data(close_price, market_value, data_source):
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

    now = myanmar_now()

    return {
        "success": True,
        "date": now.strftime("%Y-%m-%d"),
        "symbol": SYMBOL,

        "status": session_info["status"],
        "session": session_info["session"],
        "displaySession": session_info["displaySession"],
        "nextSession": session_info["nextSession"],

        "set": f"{close_price:.2f}",
        "value": str(market_value),

        "setDecimalTwo": set_decimal_two,
        "setLastDigit": set_last_digit,
        "valueLastDigit": value_last_digit,

        "result2d": result_2d,
        "morningResult": morning_result,
        "eveningResult": evening_result,

        "updatedAt": now.strftime("%Y-%m-%d %H:%M:%S"),
        "cached": False,
        "dataSource": data_source,
        "timezone": "Myanmar Time UTC+6:30"
    }


def fetch_market_data():
    ticker = yf.Ticker(SYMBOL)

    hist = ticker.history(period="5d", interval="1m")

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

    return build_result_data(close_price, market_value, "yfinance")


def get_fallback_data(error_message):
    close_price = 1611.99
    market_value = 0

    data = build_result_data(close_price, market_value, "fallback")
    data["cached"] = True
    data["lastError"] = error_message

    return data


@app.route("/")
def home():
    return jsonify({
        "success": True,
        "message": "YFinance SET API running with Myanmar time UTC+6:30"
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

        fallback_data = get_fallback_data(last_error)

        cached_today = fallback_data
        cached_time = now_time

        return jsonify(fallback_data)


@app.route("/status")
def status():
    session_info = get_market_session()

    return jsonify({
        "success": True,
        "status": session_info["status"],
        "session": session_info["session"],
        "displaySession": session_info["displaySession"],
        "nextSession": session_info["nextSession"],
        "current": session_info["current"],
        "time": session_info["time"],
        "date": session_info["date"],
        "timezone": "Myanmar Time UTC+6:30"
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)

from flask import Flask, jsonify
from datetime import datetime, timedelta
import time
import json
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from urllib.error import HTTPError

app = Flask(__name__)

# API key တခါထဲထည့်ထားတဲ့ version
TWELVE_DATA_API_KEY = "4e63156501494425a166daf42bd1f88e"

QUOTE_URL = "https://api.twelvedata.com/quote"
TIME_SERIES_URL = "https://api.twelvedata.com/time_series"

# 10 seconds cache = around 6 requests/minute
CACHE_SECONDS = 10

cached_today = None
cached_time = 0
last_error = ""


def myanmar_now():
    return datetime.utcnow() + timedelta(hours=6, minutes=30)


def get_digits(value):
    text = str(value)
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits


def get_last_digit(value):
    digits = get_digits(value)

    if len(digits) == 0:
        return "0"

    return digits[-1]


def get_set_decimal_two(price):
    try:
        price_float = float(price)
        price_text = f"{price_float:.2f}"
        decimal_part = price_text.split(".")[1]
        return decimal_part[-2:]
    except:
        return "--"


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


def fetch_json(url, params):
    full_url = url + "?" + urlencode(params)

    request = Request(
        full_url,
        headers={
            "User-Agent": "MM2D3DInfo/1.0"
        }
    )

    try:
        with urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8")
            data = json.loads(body)
            return data

    except HTTPError as e:
        try:
            body = e.read().decode("utf-8")
            data = json.loads(body)
            message = data.get("message", body)
        except:
            message = str(e)

        raise Exception(message)


def validate_twelve_data_response(data):
    if data is None:
        raise Exception("Empty Twelve Data response")

    if "status" in data and str(data.get("status")).lower() == "error":
        raise Exception(data.get("message", "Twelve Data API error"))

    if "code" in data and "message" in data:
        raise Exception(data.get("message", "Twelve Data API error"))


def call_quote_symbol_exchange():
    params = {
        "symbol": "SET",
        "exchange": "XBKK",
        "apikey": TWELVE_DATA_API_KEY
    }

    data = fetch_json(QUOTE_URL, params)
    validate_twelve_data_response(data)

    return {
        "sourceSymbol": "SET:XBKK",
        "raw": data
    }


def call_quote_colon_symbol():
    params = {
        "symbol": "SET:XBKK",
        "apikey": TWELVE_DATA_API_KEY
    }

    data = fetch_json(QUOTE_URL, params)
    validate_twelve_data_response(data)

    return {
        "sourceSymbol": "SET:XBKK",
        "raw": data
    }


def call_time_series_symbol_exchange():
    params = {
        "symbol": "SET",
        "exchange": "XBKK",
        "interval": "1min",
        "outputsize": "1",
        "apikey": TWELVE_DATA_API_KEY
    }

    data = fetch_json(TIME_SERIES_URL, params)
    validate_twelve_data_response(data)

    values = data.get("values")

    if values is None or len(values) == 0:
        raise Exception("No time_series values found")

    latest = values[0]

    quote_like = {
        "open": latest.get("open", "--"),
        "high": latest.get("high", "--"),
        "low": latest.get("low", "--"),
        "close": latest.get("close", "--"),
        "volume": latest.get("volume", "0"),
        "datetime": latest.get("datetime", "--")
    }

    return {
        "sourceSymbol": "SET:XBKK",
        "raw": quote_like
    }


def call_time_series_colon_symbol():
    params = {
        "symbol": "SET:XBKK",
        "interval": "1min",
        "outputsize": "1",
        "apikey": TWELVE_DATA_API_KEY
    }

    data = fetch_json(TIME_SERIES_URL, params)
    validate_twelve_data_response(data)

    values = data.get("values")

    if values is None or len(values) == 0:
        raise Exception("No time_series values found")

    latest = values[0]

    quote_like = {
        "open": latest.get("open", "--"),
        "high": latest.get("high", "--"),
        "low": latest.get("low", "--"),
        "close": latest.get("close", "--"),
        "volume": latest.get("volume", "0"),
        "datetime": latest.get("datetime", "--")
    }

    return {
        "sourceSymbol": "SET:XBKK",
        "raw": quote_like
    }


def call_twelve_data():
    errors = []

    callers = [
        call_quote_symbol_exchange,
        call_quote_colon_symbol,
        call_time_series_symbol_exchange,
        call_time_series_colon_symbol
    ]

    for caller in callers:
        try:
            return caller()
        except Exception as e:
            errors.append(str(e))

    raise Exception("Twelve Data failed: " + " | ".join(errors))


def build_result_data(api_result):
    now = myanmar_now()
    session_info = get_market_session()

    quote_data = api_result["raw"]
    source_symbol = api_result["sourceSymbol"]

    close_price = quote_data.get("close")

    if close_price is None or close_price == "" or close_price == "--":
        close_price = quote_data.get("price")

    if close_price is None or close_price == "" or close_price == "--":
        close_price = quote_data.get("previous_close")

    if close_price is None or close_price == "" or close_price == "--":
        raise Exception("SET index price not found in Twelve Data response")

    market_value = quote_data.get("volume")

    if market_value is None or market_value == "" or market_value == "--":
        market_value = quote_data.get("average_volume")

    if market_value is None or market_value == "" or market_value == "--":
        market_value = "0"

    # SET Index 1342.56 => decimal two = 56 => last digit = 6
    set_decimal_two = get_set_decimal_two(close_price)

    if set_decimal_two == "--":
        set_last_digit = "0"
    else:
        set_last_digit = set_decimal_two[-1]

    # Market Turnover / Volume 45821900 => last digit = 0
    value_last_digit = get_last_digit(market_value)

    # 6 + 0 = 60
    result_2d = set_last_digit + value_last_digit

    display_session = session_info["displaySession"]

    morning_result = "--"
    evening_result = "--"

    if display_session == "morning":
        morning_result = result_2d
        evening_result = "--"

    elif display_session == "evening":
        morning_result = "--"
        evening_result = result_2d

    return {
        "success": True,
        "date": now.strftime("%Y-%m-%d"),
        "symbol": source_symbol,

        "status": session_info["status"],
        "session": session_info["session"],
        "displaySession": session_info["displaySession"],
        "nextSession": session_info["nextSession"],

        "set": str(close_price),
        "value": str(market_value),

        "setDecimalTwo": set_decimal_two,
        "setLastDigit": set_last_digit,
        "valueLastDigit": value_last_digit,

        "result2d": result_2d,
        "morningResult": morning_result,
        "eveningResult": evening_result,

        "updatedAt": now.strftime("%Y-%m-%d %H:%M:%S"),
        "cached": False,
        "dataSource": "Twelve Data",
        "timezone": "Myanmar Time UTC+6:30",

        "open": quote_data.get("open", "--"),
        "high": quote_data.get("high", "--"),
        "low": quote_data.get("low", "--"),
        "close": quote_data.get("close", "--"),
        "previousClose": quote_data.get("previous_close", "--"),
        "change": quote_data.get("change", "--"),
        "percentChange": quote_data.get("percent_change", "--")
    }


@app.route("/")
def home():
    return jsonify({
        "success": True,
        "message": "Twelve Data SET API running with direct API key",
        "symbol": "SET:XBKK"
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
        api_result = call_twelve_data()
        fresh_data = build_result_data(api_result)

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
            "message": last_error,
            "dataSource": "Twelve Data",
            "symbol": "SET:XBKK",
            "cached": False
        }), 429


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

from flask import Flask, jsonify
from datetime import datetime, timedelta
import time
import os
import json
from urllib.request import urlopen, Request
from urllib.parse import urlencode

app = Flask(__name__)

# Twelve Data SET Index symbol
SYMBOL = "SET:XBKK"
API_URL = "https://api.twelvedata.com/quote"

# Twelve Data Basic plan = 8 requests/minute
# 10 seconds cache = 6 requests/minute
CACHE_SECONDS = 10

# Render Environment Variable ထဲမှာ TD_API_KEY ထည့်ထားရမယ်
TD_API_KEY = os.environ.get("TD_API_KEY", "")

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


def call_twelve_data_quote():
    if TD_API_KEY == "":
        raise Exception("TD_API_KEY is missing in Render Environment")

    params = urlencode({
        "symbol": SYMBOL,
        "apikey": TD_API_KEY
    })

    url = API_URL + "?" + params

    request = Request(
        url,
        headers={
            "User-Agent": "MM2D3DInfo/1.0"
        }
    )

    with urlopen(request, timeout=20) as response:
        body = response.read().decode("utf-8")
        data = json.loads(body)

    # Twelve Data error response
    if "status" in data and str(data.get("status")).lower() == "error":
        raise Exception(data.get("message", "Twelve Data API error"))

    if "code" in data and "message" in data:
        raise Exception(data.get("message", "Twelve Data API error"))

    return data


def build_result_data(quote_data):
    now = myanmar_now()
    session_info = get_market_session()

    # Twelve Data quote မှာ close ကိုအဓိကယူမယ်
    close_price = quote_data.get("close")

    if close_price is None or close_price == "":
        close_price = quote_data.get("price")

    if close_price is None or close_price == "":
        close_price = quote_data.get("previous_close")

    if close_price is None or close_price == "":
        raise Exception("SET index price not found in Twelve Data response")

    # quote endpoint မှာ Market Turnover အစစ်မပါနိုင်ပါ
    # volume ရှိရင် volume ကိုယူမယ်။ မရှိရင် 0 ထားမယ်။
    market_value = quote_data.get("volume")

    if market_value is None or market_value == "":
        market_value = quote_data.get("average_volume")

    if market_value is None or market_value == "":
        market_value = "0"

    # Example:
    # SET Index 1342.56 -> decimal two = 56 -> last digit = 6
    set_decimal_two = get_set_decimal_two(close_price)

    if set_decimal_two == "--":
        set_last_digit = "0"
    else:
        set_last_digit = set_decimal_two[-1]

    # Example:
    # Market Turnover / Volume 45821900 -> last digit = 0
    value_last_digit = get_last_digit(market_value)

    # Result:
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
        "symbol": SYMBOL,

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
        "message": "Twelve Data SET API running",
        "symbol": SYMBOL
    })


@app.route("/today")
def today():
    global cached_today
    global cached_time
    global last_error

    now_time = time.time()

    # cache ရှိပြီး 10 seconds မကျော်သေးရင် Twelve Data ကိုထပ်မခေါ်တော့ဘူး
    if cached_today is not None and now_time - cached_time < CACHE_SECONDS:
        response = dict(cached_today)
        response["cached"] = True
        response["lastError"] = last_error
        return jsonify(response)

    try:
        quote_data = call_twelve_data_quote()
        fresh_data = build_result_data(quote_data)

        cached_today = fresh_data
        cached_time = now_time
        last_error = ""

        return jsonify(fresh_data)

    except Exception as e:
        last_error = str(e)

        # API error ဖြစ်ရင် အရင် cache ရှိတာ ပြန်ပြမယ်
        if cached_today is not None:
            response = dict(cached_today)
            response["cached"] = True
            response["lastError"] = last_error
            return jsonify(response)

        return jsonify({
            "success": False,
            "message": last_error,
            "dataSource": "Twelve Data",
            "symbol": SYMBOL,
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

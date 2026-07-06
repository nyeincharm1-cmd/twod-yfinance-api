from flask import Flask, jsonify
from datetime import datetime, timedelta
import time
import re
import html
from urllib.request import urlopen, Request

app = Flask(__name__)

SET_URL = "https://www.set.or.th/en/home"

CACHE_SECONDS = 10

cached_today = None
cached_time = 0
last_error = ""


def myanmar_now():
    return datetime.utcnow() + timedelta(hours=6, minutes=30)


def clean_text(raw_html):
    text = re.sub(r"<script[\s\S]*?</script>", " ", raw_html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def get_set_decimal_two(price):
    try:
        price_float = float(str(price).replace(",", ""))
        price_text = f"{price_float:.2f}"
        decimal_part = price_text.split(".")[1]
        return decimal_part[-2:]
    except:
        return "--"


def get_value_last_digit(value):
    text = str(value)

    # decimal မတိုင်ခင် integer part ပဲယူမယ်
    # Example: 52,662.47 -> 52,662
    integer_part = text.split(".")[0]

    # comma ဖယ်မယ်
    # Example: 52,662 -> 52662
    digits = "".join(ch for ch in integer_part if ch.isdigit())

    if len(digits) == 0:
        return "0"

    # Example: 52662 -> 2
    return digits[-1]


def get_market_session():
    now = myanmar_now()
    current = now.hour * 60 + now.minute

    # Myanmar Time
    morning_open = 480      # 08:00 AM
    morning_close = 721     # 12:01 PM

    evening_open = 780      # 01:00 PM
    evening_close = 991     # 04:31 PM

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

    return {
        "status": status,
        "session": session,
        "displaySession": display_session,
        "nextSession": next_session,
        "current": current,
        "time": now.strftime("%H:%M:%S"),
        "date": now.strftime("%Y-%m-%d")
    }


def fetch_set_official():
    request = Request(
        SET_URL,
        headers={
            "User-Agent": "Mozilla/5.0 MM2D3DInfo/1.0"
        }
    )

    with urlopen(request, timeout=20) as response:
        body = response.read().decode("utf-8", errors="ignore")

    text = clean_text(body)

    market_status = "--"
    last_update = "--"

    status_match = re.search(r"Market Status\s+([A-Za-z0-9]+)", text)
    if status_match:
        market_status = status_match.group(1)
        market_status = market_status.replace("2", "")

    update_match = re.search(
        r"Last Update\s+(\d{2}\s+[A-Za-z]{3}\s+\d{4}\s+\d{2}:\d{2}:\d{2})",
        text
    )
    if update_match:
        last_update = update_match.group(1)

    # Official SET row example:
    # SET 1,616.34 +5.06 7,205,959 50,797.41
    set_pattern = r"\bSET\s+([\d,]+\.\d{2})\s+([+-][\d,]+\.\d{2})\s+([\d,]+)\s+([\d,]+\.\d{2})"
    set_match = re.search(set_pattern, text)

    if not set_match:
        raise Exception("SET row not found from official SET website")

    set_index = set_match.group(1)
    change = set_match.group(2)
    volume = set_match.group(3)
    trading_value = set_match.group(4)

    return {
        "setIndex": set_index,
        "change": change,
        "volume": volume,
        "tradingValue": trading_value,
        "marketStatusFromSET": market_status,
        "lastUpdateFromSET": last_update
    }


def build_result_data(set_data):
    now = myanmar_now()
    session_info = get_market_session()

    set_index = set_data["setIndex"]
    trading_value = set_data["tradingValue"]

    # SET Index 1342.56 -> decimal two = 56 -> last digit = 6
    set_decimal_two = get_set_decimal_two(set_index)

    if set_decimal_two == "--":
        set_last_digit = "0"
    else:
        set_last_digit = set_decimal_two[-1]

    # Market Turnover 52,662.47 -> integer 52662 -> last digit = 2
    value_last_digit = get_value_last_digit(trading_value)

    # Correct 2D formula:
    # SET last digit + Market Turnover last digit
    # Example: 6 + 0 = 60
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
        "symbol": "SET Official",

        "status": session_info["status"],
        "session": session_info["session"],
        "displaySession": session_info["displaySession"],
        "nextSession": session_info["nextSession"],

        "set": str(set_index),
        "value": str(trading_value),
        "volume": str(set_data["volume"]),

        "setDecimalTwo": set_decimal_two,
        "setLastDigit": set_last_digit,
        "valueLastDigit": value_last_digit,

        "result2d": result_2d,
        "morningResult": morning_result,
        "eveningResult": evening_result,

        "updatedAt": now.strftime("%Y-%m-%d %H:%M:%S"),
        "setLastUpdate": set_data["lastUpdateFromSET"],
        "setMarketStatus": set_data["marketStatusFromSET"],

        "cached": False,
        "dataSource": "SET Official Website",
        "timezone": "Myanmar Time UTC+6:30",

        "change": set_data["change"],
        "sourceUrl": SET_URL
    }


@app.route("/")
def home():
    return jsonify({
        "success": True,
        "message": "SET Official Website API running with correct 2D formula",
        "source": SET_URL
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
        set_data = fetch_set_official()
        fresh_data = build_result_data(set_data)

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
            "dataSource": "SET Official Website",
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

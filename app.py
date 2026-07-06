from flask import Flask, jsonify, request
from datetime import datetime, timedelta
import time
import os
import json
import gzip
import zlib
from urllib.request import urlopen, Request
from urllib.error import HTTPError

app = Flask(__name__)

THAI_LIVE_URL = os.environ.get(
    "THAI_LIVE_URL",
    "https://api.thaistock2d.com/live"
)

THAI_RESULT_URL = os.environ.get(
    "THAI_RESULT_URL",
    "https://api.thaistock2d.com/2d_result"
)

CACHE_SECONDS = 10
HISTORY_CACHE_SECONDS = 300

cached_today = None
cached_today_time = 0

cached_history = None
cached_history_time = 0


def myanmar_now():
    return datetime.utcnow() + timedelta(hours=6, minutes=30)


def fetch_json(url):
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Android) MM2D3DInfo/1.0",
            "Accept": "application/json,text/plain,*/*",
            "Accept-Encoding": "gzip, deflate, identity",
            "Connection": "close"
        }
    )

    try:
        with urlopen(req, timeout=30) as response:
            raw_body = response.read()
            encoding = str(response.headers.get("Content-Encoding", "")).lower()

            if "gzip" in encoding:
                raw_body = gzip.decompress(raw_body)

            elif "deflate" in encoding:
                try:
                    raw_body = zlib.decompress(raw_body)
                except:
                    raw_body = zlib.decompress(raw_body, -zlib.MAX_WBITS)

            body = raw_body.decode("utf-8-sig", errors="replace").strip()

            if body == "":
                raise Exception("Empty response")

            if not body.startswith("{") and not body.startswith("["):
                raise Exception("Non JSON response: " + body[:200])

            return json.loads(body)

    except HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        raise Exception("HTTP " + str(e.code) + ": " + body[:300])


def get_market_session():
    now = myanmar_now()
    current = now.hour * 60 + now.minute

    morning_open = 570
    morning_close = 721

    evening_open = 840
    evening_close = 990

    status = "CLOSE"
    session = "none"
    display_session = "none"
    next_session = "Morning Session 09:30 AM"

    if current >= morning_open and current <= morning_close:
        status = "OPEN"
        session = "morning"
        display_session = "morning"
        next_session = "Evening Session 02:00 PM"

    elif current > morning_close and current < evening_open:
        status = "CLOSE"
        session = "none"
        display_session = "morning"
        next_session = "Evening Session 02:00 PM"

    elif current >= evening_open and current <= evening_close:
        status = "OPEN"
        session = "evening"
        display_session = "evening"
        next_session = "Tomorrow Morning 09:30 AM"

    elif current > evening_close:
        status = "CLOSE"
        session = "none"
        display_session = "evening"
        next_session = "Tomorrow Morning 09:30 AM"

    return {
        "status": status,
        "session": session,
        "displaySession": display_session,
        "nextSession": next_session,
        "current": current,
        "time": now.strftime("%H:%M:%S"),
        "date": now.strftime("%Y-%m-%d")
    }


def value_or_dash(item, key):
    if item is None or not isinstance(item, dict):
        return "--"

    value = item.get(key, "--")

    if value is None or str(value).strip() == "":
        return "--"

    return str(value)


def calculate_2d_from_set_value(set_value, market_value):
    try:
        set_text = str(set_value).replace(",", "").strip()
        value_text = str(market_value).replace(",", "").strip()

        if set_text == "" or value_text == "":
            return "--"

        if set_text == "--" or value_text == "--":
            return "--"

        if "." not in set_text:
            return "--"

        set_decimal = set_text.split(".")[1]

        if len(set_decimal) == 0:
            return "--"

        first_digit = set_decimal[-1]

        value_integer = value_text.split(".")[0]
        value_digits = "".join(ch for ch in value_integer if ch.isdigit())

        if len(value_digits) == 0:
            return "--"

        second_digit = value_digits[-1]

        return first_digit + second_digit

    except:
        return "--"


def normalize_2d_text(value):
    if value is None:
        return "--"

    text = str(value).strip()

    if text == "":
        return "--"

    digits = "".join(ch for ch in text if ch.isdigit())

    if len(digits) == 0:
        return "--"

    if len(digits) == 1:
        return "0" + digits

    return digits[-2:]


def twod_or_dash(item):
    if item is None or not isinstance(item, dict):
        return "--"

    set_value = value_or_dash(item, "set")
    market_value = value_or_dash(item, "value")

    calculated = calculate_2d_from_set_value(set_value, market_value)

    if calculated != "--":
        return calculated

    value = item.get("twod", None)

    if value is None:
        value = item.get("result", None)

    return normalize_2d_text(value)


def find_by_time(result_list, target_time):
    if not isinstance(result_list, list):
        return None

    for item in result_list:
        if not isinstance(item, dict):
            continue

        item_time = str(item.get("open_time", item.get("time", "")))

        if item_time == target_time:
            return item

    return None


def format_date_slash(date_text):
    try:
        dt = datetime.strptime(date_text, "%Y-%m-%d")
        return dt.strftime("%d/%m/%Y")
    except:
        return str(date_text)


def format_date_title(date_text):
    try:
        dt = datetime.strptime(date_text, "%Y-%m-%d")
        return dt.strftime("%B %d, %Y (%A)").replace(" 0", " ")
    except:
        return str(date_text)


def build_history_days(raw_data):
    days = []

    if not isinstance(raw_data, list):
        return days

    for day in raw_data:
        if not isinstance(day, dict):
            continue

        date_iso = str(day.get("date", "--"))
        date_text = format_date_slash(date_iso)
        date_title = format_date_title(date_iso)

        child = day.get("child", [])

        item_1100 = None
        item_1201 = None
        item_1500 = None
        item_1630 = None

        if isinstance(child, list):
            for item in child:
                if not isinstance(item, dict):
                    continue

                item_time = str(item.get("time", "--"))

                if item_time == "11:00:00":
                    item_1100 = item

                elif item_time == "12:01:00":
                    item_1201 = item

                elif item_time == "15:00:00":
                    item_1500 = item

                elif item_time == "16:30:00":
                    item_1630 = item

        one_day = {
            "date": date_iso,
            "dateText": date_text,
            "dateTitle": date_title,

            "morningOpenTime": "11:00 AM",
            "morningOpenSet": value_or_dash(item_1100, "set"),
            "morningOpenValue": value_or_dash(item_1100, "value"),
            "morningOpenResult": twod_or_dash(item_1100),

            "morningTime": "12:01 PM",
            "morningSet": value_or_dash(item_1201, "set"),
            "morningValue": value_or_dash(item_1201, "value"),
            "morningResult": twod_or_dash(item_1201),

            "eveningOpenTime": "03:00 PM",
            "eveningOpenSet": value_or_dash(item_1500, "set"),
            "eveningOpenValue": value_or_dash(item_1500, "value"),
            "eveningOpenResult": twod_or_dash(item_1500),

            "eveningTime": "04:30 PM",
            "eveningSet": value_or_dash(item_1630, "set"),
            "eveningValue": value_or_dash(item_1630, "value"),
            "eveningResult": twod_or_dash(item_1630),

            "set": value_or_dash(item_1201, "set"),
            "val": value_or_dash(item_1201, "value"),
            "twoD": twod_or_dash(item_1201)
        }

        days.append(one_day)

    return days


def build_history_response(month_filter):
    raw_data = fetch_json(THAI_RESULT_URL)
    all_days = build_history_days(raw_data)

    filtered = []

    for day in all_days:
        date_iso = str(day.get("date", ""))

        if month_filter != "" and not date_iso.startswith(month_filter):
            continue

        filtered.append(day)

    return {
        "success": True,
        "status": True,
        "message": "success",
        "dataSource": "ThaiStock2D API",
        "sourceUrl": THAI_RESULT_URL,
        "date": month_filter,
        "count": len(filtered),
        "data": filtered
    }


def build_old_history_response():
    raw_data = fetch_json(THAI_RESULT_URL)
    data = build_history_days(raw_data)

    days = []
    flat = []

    for item in data:
        day = {
            "date": item.get("dateText", "--"),
            "dateIso": item.get("date", "--"),
            "dateTitle": item.get("dateTitle", "--"),

            "morningOpen": {
                "time": "11:00 AM",
                "set": item.get("morningOpenSet", "--"),
                "value": item.get("morningOpenValue", "--"),
                "result": item.get("morningOpenResult", "--")
            },

            "morning": {
                "time": "12:01 PM",
                "set": item.get("morningSet", "--"),
                "value": item.get("morningValue", "--"),
                "result": item.get("morningResult", "--")
            },

            "eveningOpen": {
                "time": "03:00 PM",
                "set": item.get("eveningOpenSet", "--"),
                "value": item.get("eveningOpenValue", "--"),
                "result": item.get("eveningOpenResult", "--")
            },

            "evening": {
                "time": "04:30 PM",
                "set": item.get("eveningSet", "--"),
                "value": item.get("eveningValue", "--"),
                "result": item.get("eveningResult", "--")
            }
        }

        days.append(day)

        flat.append({
            "date": item.get("dateText", "--"),
            "dateIso": item.get("date", "--"),
            "dateTitle": item.get("dateTitle", "--"),
            "time": "12:01 PM",
            "rawTime": "12:01:00",
            "set": item.get("morningSet", "--"),
            "value": item.get("morningValue", "--"),
            "result": item.get("morningResult", "--"),
            "twod": item.get("morningResult", "--")
        })

        flat.append({
            "date": item.get("dateText", "--"),
            "dateIso": item.get("date", "--"),
            "dateTitle": item.get("dateTitle", "--"),
            "time": "04:30 PM",
            "rawTime": "16:30:00",
            "set": item.get("eveningSet", "--"),
            "value": item.get("eveningValue", "--"),
            "result": item.get("eveningResult", "--"),
            "twod": item.get("eveningResult", "--")
        })

    return {
        "success": True,
        "dataSource": "ThaiStock2D API",
        "sourceUrl": THAI_RESULT_URL,
        "count": len(flat),
        "daysCount": len(days),
        "history": flat,
        "days": days,
        "cached": False
    }


@app.route("/")
def home():
    return jsonify({
        "success": True,
        "message": "MM 2D History API running with ThaiStock2D",
        "today": "/today",
        "history": "/history",
        "api2d": "/api/v3/2d",
        "calendar": "/api/v3/2d-calendar?date=2026-07",
        "statusApi": "/status",
        "dataSource": "ThaiStock2D API"
    })


@app.route("/today")
def today():
    global cached_today
    global cached_today_time

    now_time = time.time()

    if cached_today is not None and now_time - cached_today_time < CACHE_SECONDS:
        response = dict(cached_today)
        response["cached"] = True
        return jsonify(response)

    try:
        live_data = fetch_json(THAI_LIVE_URL)

        session_info = get_market_session()

        live = live_data.get("live", {})
        result_list = live_data.get("result", [])

        item_1100 = find_by_time(result_list, "11:00:00")
        item_1201 = find_by_time(result_list, "12:01:00")
        item_1500 = find_by_time(result_list, "15:00:00")
        item_1630 = find_by_time(result_list, "16:30:00")

        response = {
            "success": True,

            "date": str(live.get("date", session_info["date"])),
            "symbol": "ThaiStock2D",

            "status": session_info["status"],
            "session": session_info["session"],
            "displaySession": session_info["displaySession"],
            "nextSession": session_info["nextSession"],

            "set": value_or_dash(live, "set"),
            "value": value_or_dash(live, "value"),
            "result2d": twod_or_dash(live),

            "morningOpenTime": "11:00 AM",
            "morningOpenSet": value_or_dash(item_1100, "set"),
            "morningOpenValue": value_or_dash(item_1100, "value"),
            "morningOpenResult": twod_or_dash(item_1100),

            "morningTime": "12:01 PM",
            "morningSet": value_or_dash(item_1201, "set"),
            "morningValue": value_or_dash(item_1201, "value"),
            "morningResult": twod_or_dash(item_1201),

            "eveningOpenTime": "03:00 PM",
            "eveningOpenSet": value_or_dash(item_1500, "set"),
            "eveningOpenValue": value_or_dash(item_1500, "value"),
            "eveningOpenResult": twod_or_dash(item_1500),

            "eveningTime": "04:30 PM",
            "eveningSet": value_or_dash(item_1630, "set"),
            "eveningValue": value_or_dash(item_1630, "value"),
            "eveningResult": twod_or_dash(item_1630),

            "updatedAt": str(live.get("time", "--")),
            "serverTime": str(live_data.get("server_time", "--")),

            "cached": False,
            "dataSource": "ThaiStock2D API",
            "sourceUrl": THAI_LIVE_URL,
            "timezone": "Myanmar Time UTC+6:30"
        }

        cached_today = response
        cached_today_time = now_time

        return jsonify(response)

    except Exception as e:
        if cached_today is not None:
            response = dict(cached_today)
            response["cached"] = True
            response["lastError"] = str(e)
            return jsonify(response)

        return jsonify({
            "success": False,
            "message": str(e),
            "cached": False
        }), 500


@app.route("/history")
def history():
    global cached_history
    global cached_history_time

    now_time = time.time()

    if cached_history is not None and now_time - cached_history_time < HISTORY_CACHE_SECONDS:
        response = dict(cached_history)
        response["cached"] = True
        return jsonify(response)

    try:
        response = build_old_history_response()

        cached_history = response
        cached_history_time = now_time

        return jsonify(response)

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e),
            "cached": False
        }), 500


@app.route("/api/v3/2d")
def api_v3_2d():
    try:
        response = build_history_response("")
        return jsonify(response)

    except Exception as e:
        return jsonify({
            "success": False,
            "status": False,
            "message": str(e),
            "data": []
        }), 500


@app.route("/api/v3/2d-calendar")
def api_v3_2d_calendar():
    try:
        month_filter = request.args.get("date", "")

        if month_filter is None or str(month_filter).strip() == "":
            month_filter = myanmar_now().strftime("%Y-%m")

        month_filter = str(month_filter).strip()

        response = build_history_response(month_filter)
        response["date"] = month_filter

        return jsonify(response)

    except Exception as e:
        return jsonify({
            "success": False,
            "status": False,
            "message": str(e),
            "date": request.args.get("date", ""),
            "data": []
        }), 500


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

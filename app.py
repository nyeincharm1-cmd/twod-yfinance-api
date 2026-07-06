from flask import Flask, jsonify, request
from datetime import datetime, timedelta
import time
import os
import json
import gzip
import zlib
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from urllib.parse import urlencode

app = Flask(__name__)

THAI_LIVE_URL = os.environ.get(
    "THAI_LIVE_URL",
    "https://api.thaistock2d.com/live"
)

THAI_RESULT_URL = os.environ.get(
    "THAI_RESULT_URL",
    "https://api.thaistock2d.com/2d_result"
)

THAI_HISTORY_URL = os.environ.get(
    "THAI_HISTORY_URL",
    "https://api.thaistock2d.com/history"
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
    request_obj = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Android) MM2D3DInfo/1.0",
            "Accept": "application/json,text/plain,*/*",
            "Accept-Encoding": "gzip, deflate, identity",
            "Connection": "close"
        }
    )

    try:
        with urlopen(request_obj, timeout=30) as response:
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
                raise Exception("Non JSON response: " + body[:150])

            return json.loads(body)

    except HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        raise Exception(body)


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
    if item is None:
        return "--"

    value = item.get(key, "--")

    if value is None or str(value).strip() == "":
        return "--"

    return str(value)


def get_set_value(item):
    if item is None or not isinstance(item, dict):
        return "--"

    possible_keys = ["set", "SET", "setIndex", "index"]

    for key in possible_keys:
        value = item.get(key)

        if value is not None and str(value).strip() != "":
            return str(value)

    return "--"


def get_market_value(item):
    if item is None or not isinstance(item, dict):
        return "--"

    possible_keys = ["value", "val", "VALUE", "marketValue"]

    for key in possible_keys:
        value = item.get(key)

        if value is not None and str(value).strip() != "":
            return str(value)

    return "--"


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

    set_value = get_set_value(item)
    market_value = get_market_value(item)

    calculated = calculate_2d_from_set_value(set_value, market_value)

    if calculated != "--":
        return calculated

    value = item.get("twod", None)

    if value is None:
        value = item.get("result", None)

    if value is None:
        value = item.get("number", None)

    return normalize_2d_text(value)


def find_by_time(result_list, open_time):
    if not isinstance(result_list, list):
        return None

    for item in result_list:
        if not isinstance(item, dict):
            continue

        item_time = str(item.get("open_time", item.get("time", "")))

        if item_time == open_time:
            return item

    return None


def time_to_seconds(time_text):
    try:
        time_text = str(time_text).strip()

        if ":" not in time_text:
            return -1

        parts = time_text.split(":")
        hour = int(parts[0])
        minute = int(parts[1])
        second = 0

        if len(parts) >= 3:
            second = int(parts[2])

        return hour * 3600 + minute * 60 + second

    except:
        return -1


def extract_time(item):
    if not isinstance(item, dict):
        return ""

    if item.get("time"):
        return str(item.get("time"))

    if item.get("stock_time"):
        return str(item.get("stock_time"))

    if item.get("open_time"):
        return str(item.get("open_time"))

    stock_datetime = str(item.get("stock_datetime", ""))

    if " " in stock_datetime:
        return stock_datetime.split(" ")[1]

    return ""


def extract_twod(item):
    return twod_or_dash(item)


def normalize_history_change_items(raw_data):
    if isinstance(raw_data, list):
        return raw_data

    if not isinstance(raw_data, dict):
        return []

    possible_keys = [
        "data",
        "history",
        "result",
        "items",
        "child",
        "stock",
        "stocks"
    ]

    for key in possible_keys:
        value = raw_data.get(key)

        if isinstance(value, list):
            return value

        if isinstance(value, dict):
            child = value.get("child")

            if isinstance(child, list):
                return child

    return []


def fetch_change_history_for_date(date_iso, allow_current_fallback):
    try:
        params = urlencode({"date": date_iso})
        date_url = THAI_HISTORY_URL + "?" + params
        data = fetch_json(date_url)
        items = normalize_history_change_items(data)

        if len(items) > 0:
            return items

    except:
        pass

    if allow_current_fallback:
        try:
            data = fetch_json(THAI_HISTORY_URL)
            items = normalize_history_change_items(data)
            return items

        except:
            return []

    return []


def find_first_twod_between(items, start_time, end_time):
    start_sec = time_to_seconds(start_time)
    end_sec = time_to_seconds(end_time)

    best_item = None
    best_sec = None

    if not isinstance(items, list):
        return "--"

    for item in items:
        if not isinstance(item, dict):
            continue

        item_time = extract_time(item)
        sec = time_to_seconds(item_time)

        if sec < 0:
            continue

        if sec >= start_sec and sec <= end_sec:
            twod = extract_twod(item)

            if twod == "--":
                continue

            if best_sec is None or sec < best_sec:
                best_sec = sec
                best_item = item

    return extract_twod(best_item)


def find_second_different_twod_between(items, start_time, end_time, first_twod):
    start_sec = time_to_seconds(start_time)
    end_sec = time_to_seconds(end_time)

    best_item = None
    best_sec = None

    if not isinstance(items, list):
        return "--"

    for item in items:
        if not isinstance(item, dict):
            continue

        item_time = extract_time(item)
        sec = time_to_seconds(item_time)

        if sec < 0:
            continue

        if sec >= start_sec and sec <= end_sec:
            twod = extract_twod(item)

            if twod == "--":
                continue

            if first_twod != "--" and twod == first_twod:
                continue

            if best_sec is None or sec < best_sec:
                best_sec = sec
                best_item = item

    return extract_twod(best_item)


def get_modern_internet_for_date(date_iso, allow_current_fallback=False):
    items = fetch_change_history_for_date(date_iso, allow_current_fallback)

    morning_modern = find_first_twod_between(
        items,
        "09:30:00",
        "10:59:59"
    )

    morning_internet = find_second_different_twod_between(
        items,
        "09:30:00",
        "10:59:59",
        morning_modern
    )

    evening_modern = find_first_twod_between(
        items,
        "14:00:00",
        "14:59:59"
    )

    evening_internet = find_second_different_twod_between(
        items,
        "14:00:00",
        "14:59:59",
        evening_modern
    )

    return {
        "morningModern": morning_modern,
        "morningInternet": morning_internet,
        "morningTW": "--",
        "eveningModern": evening_modern,
        "eveningInternet": evening_internet
    }


def format_time_12h(raw_time):
    if raw_time == "11:00:00":
        return "11:00 AM"

    if raw_time == "12:01:00":
        return "12:01 PM"

    if raw_time == "15:00:00":
        return "03:00 PM"

    if raw_time == "16:30:00":
        return "04:30 PM"

    try:
        dt = datetime.strptime(raw_time, "%H:%M:%S")
        return dt.strftime("%I:%M %p")
    except:
        return str(raw_time)


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


def build_today_response(live_data):
    session_info = get_market_session()

    live = live_data.get("live", {})
    result_list = live_data.get("result", [])

    morning_1100 = find_by_time(result_list, "11:00:00")
    morning_1201 = find_by_time(result_list, "12:01:00")
    evening_1500 = find_by_time(result_list, "15:00:00")
    evening_1630 = find_by_time(result_list, "16:30:00")

    live_set = value_or_dash(live, "set")
    live_value = value_or_dash(live, "value")
    live_twod = twod_or_dash(live)

    live_date = str(live.get("date", session_info["date"]))
    live_time = str(live.get("time", "--"))

    modern_data = get_modern_internet_for_date(live_date, True)

    if modern_data["morningModern"] == "--":
        modern_data["morningModern"] = twod_or_dash(morning_1100)

    if modern_data["morningInternet"] == "--":
        modern_data["morningInternet"] = twod_or_dash(morning_1201)

    if modern_data["eveningModern"] == "--":
        modern_data["eveningModern"] = twod_or_dash(evening_1500)

    if modern_data["eveningInternet"] == "--":
        modern_data["eveningInternet"] = twod_or_dash(evening_1630)

    return {
        "success": True,

        "date": live_date,
        "symbol": "ThaiStock2D",

        "status": session_info["status"],
        "session": session_info["session"],
        "displaySession": session_info["displaySession"],
        "nextSession": session_info["nextSession"],

        "set": live_set,
        "value": live_value,
        "result2d": live_twod,

        "morningOpenTime": "11:00 AM",
        "morningOpenSet": value_or_dash(morning_1100, "set"),
        "morningOpenValue": value_or_dash(morning_1100, "value"),
        "morningOpenResult": twod_or_dash(morning_1100),

        "morningTime": "12:01 PM",
        "morningSet": value_or_dash(morning_1201, "set"),
        "morningValue": value_or_dash(morning_1201, "value"),
        "morningResult": twod_or_dash(morning_1201),
        "morningUpdatedAt": str(morning_1201.get("stock_datetime", "--")) if morning_1201 else "--",

        "eveningOpenTime": "03:00 PM",
        "eveningOpenSet": value_or_dash(evening_1500, "set"),
        "eveningOpenValue": value_or_dash(evening_1500, "value"),
        "eveningOpenResult": twod_or_dash(evening_1500),

        "eveningTime": "04:30 PM",
        "eveningSet": value_or_dash(evening_1630, "set"),
        "eveningValue": value_or_dash(evening_1630, "value"),
        "eveningResult": twod_or_dash(evening_1630),
        "eveningUpdatedAt": str(evening_1630.get("stock_datetime", "--")) if evening_1630 else "--",

        "morningModern": modern_data["morningModern"],
        "morningInternet": modern_data["morningInternet"],
        "morningTW": "--",

        "eveningModern": modern_data["eveningModern"],
        "eveningInternet": modern_data["eveningInternet"],

        "updatedAt": live_time,
        "serverTime": str(live_data.get("server_time", "--")),

        "cached": False,
        "dataSource": "ThaiStock2D API - calculated from Thai SET and Value",
        "sourceUrl": THAI_LIVE_URL,
        "timezone": "Myanmar Time UTC+6:30"
    }


def normalize_history(raw_data):
    flat_history = []
    day_list = []

    if not isinstance(raw_data, list):
        return flat_history, day_list

    seen = set()

    max_days_to_enrich = 20
    day_counter = 0

    for day in raw_data:
        if not isinstance(day, dict):
            continue

        date_iso = str(day.get("date", "--"))
        date_slash = format_date_slash(date_iso)
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

        modern_data = {
            "morningModern": "--",
            "morningInternet": "--",
            "morningTW": "--",
            "eveningModern": "--",
            "eveningInternet": "--"
        }

        if day_counter < max_days_to_enrich:
            modern_data = get_modern_internet_for_date(date_iso, False)

        day_data = {
            "date": date_slash,
            "dateIso": date_iso,
            "dateTitle": date_title,

            "morningOpen": {
                "time": "11:00 AM",
                "set": value_or_dash(item_1100, "set"),
                "value": value_or_dash(item_1100, "value"),
                "result": twod_or_dash(item_1100)
            },

            "morning": {
                "time": "12:01 PM",
                "set": value_or_dash(item_1201, "set"),
                "value": value_or_dash(item_1201, "value"),
                "result": twod_or_dash(item_1201)
            },

            "eveningOpen": {
                "time": "03:00 PM",
                "set": value_or_dash(item_1500, "set"),
                "value": value_or_dash(item_1500, "value"),
                "result": twod_or_dash(item_1500)
            },

            "evening": {
                "time": "04:30 PM",
                "set": value_or_dash(item_1630, "set"),
                "value": value_or_dash(item_1630, "value"),
                "result": twod_or_dash(item_1630)
            },

            "morningModern": modern_data["morningModern"],
            "morningInternet": modern_data["morningInternet"],
            "morningTW": "--",
            "eveningModern": modern_data["eveningModern"],
            "eveningInternet": modern_data["eveningInternet"]
        }

        day_list.append(day_data)
        day_counter += 1

        for item in [item_1201, item_1630]:
            if item is None:
                continue

            raw_time = str(item.get("time", "--"))
            time_text = format_time_12h(raw_time)
            result = twod_or_dash(item)
            set_value = value_or_dash(item, "set")
            market_value = value_or_dash(item, "value")

            unique_key = date_slash + "|" + time_text + "|" + result + "|" + set_value + "|" + market_value

            if unique_key in seen:
                continue

            seen.add(unique_key)

            flat_history.append({
                "date": date_slash,
                "dateIso": date_iso,
                "dateTitle": date_title,
                "time": time_text,
                "rawTime": raw_time,
                "result": result,
                "twod": result,
                "set": set_value,
                "value": market_value,

                "morningModern": modern_data["morningModern"],
                "morningInternet": modern_data["morningInternet"],
                "morningTW": "--",
                "eveningModern": modern_data["eveningModern"],
                "eveningInternet": modern_data["eveningInternet"]
            })

    return flat_history, day_list


def convert_day_to_marketdata_style(day):
    morning_open = day.get("morningOpen", {})
    morning = day.get("morning", {})
    evening_open = day.get("eveningOpen", {})
    evening = day.get("evening", {})

    return {
        "date": day.get("dateIso", "--"),
        "dateText": day.get("date", "--"),
        "dateTitle": day.get("dateTitle", "--"),

        "modern": day.get("morningModern", "--"),
        "internet": day.get("morningInternet", "--"),
        "tw": "--",

        "modern2": day.get("eveningModern", "--"),
        "internet2": day.get("eveningInternet", "--"),

        "set": morning.get("set", "--"),
        "val": morning.get("value", "--"),
        "twoD": morning.get("result", "--"),

        "morningOpenSet": morning_open.get("set", "--"),
        "morningOpenValue": morning_open.get("value", "--"),
        "morningOpenResult": morning_open.get("result", "--"),

        "morningSet": morning.get("set", "--"),
        "morningValue": morning.get("value", "--"),
        "morningResult": morning.get("result", "--"),

        "eveningOpenSet": evening_open.get("set", "--"),
        "eveningOpenValue": evening_open.get("value", "--"),
        "eveningOpenResult": evening_open.get("result", "--"),

        "eveningSet": evening.get("set", "--"),
        "eveningValue": evening.get("value", "--"),
        "eveningResult": evening.get("result", "--")
    }


def build_marketdata_2d_response(month_filter):
    raw_data = fetch_json(THAI_RESULT_URL)
    flat_history, day_list = normalize_history(raw_data)

    data = []

    for day in day_list:
        date_iso = str(day.get("dateIso", ""))

        if month_filter != "" and not date_iso.startswith(month_filter):
            continue

        data.append(convert_day_to_marketdata_style(day))

    return {
        "success": True,
        "status": True,
        "message": "success",
        "dataSource": "ThaiStock2D API - Thai SET and Value calculated",
        "date": month_filter,
        "count": len(data),
        "data": data
    }


@app.route("/")
def home():
    return jsonify({
        "success": True,
        "message": "MM 2D 3D API running with ThaiStock2D only",
        "today": "/today",
        "history": "/history",
        "statusApi": "/status",
        "marketData2D": "/api/v3/2d",
        "marketData2DCalendar": "/api/v3/2d-calendar?date=2026-07",
        "dataSource": "ThaiStock2D API - calculated from Thai SET and Value",
        "tw": "disabled"
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
        response = build_today_response(live_data)

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
            "dataSource": "ThaiStock2D API",
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
        raw_data = fetch_json(THAI_RESULT_URL)
        flat_history, day_list = normalize_history(raw_data)

        response = {
            "success": True,
            "dataSource": "ThaiStock2D API - Thai SET and Value calculated",
            "count": len(flat_history),
            "daysCount": len(day_list),
            "history": flat_history,
            "days": day_list,
            "cached": False,
            "sourceUrl": THAI_RESULT_URL,
            "tw": "disabled"
        }

        cached_history = response
        cached_history_time = now_time

        return jsonify(response)

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e),
            "dataSource": "ThaiStock2D API",
            "cached": False
        }), 500


@app.route("/api/v3/2d")
def api_v3_2d():
    try:
        response = build_marketdata_2d_response("")
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

        response = build_marketdata_2d_response(month_filter)
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

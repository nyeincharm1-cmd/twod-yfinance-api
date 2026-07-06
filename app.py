from flask import Flask, jsonify
from datetime import datetime, timedelta
import time
import os
import json
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
    request = Request(
        url,
        headers={
            "User-Agent": "MM2D3DInfo/1.0",
            "Accept": "application/json"
        }
    )

    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", errors="ignore")
            return json.loads(body)

    except HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        raise Exception(body)


def get_market_session():
    now = myanmar_now()
    current = now.hour * 60 + now.minute

    morning_open = 570      # 09:30 AM
    morning_close = 721     # 12:01 PM

    evening_open = 840      # 02:00 PM
    evening_close = 990     # 04:30 PM

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


def value_or_dash(item, key):
    if item is None:
        return "--"

    value = item.get(key, "--")

    if value is None or str(value).strip() == "":
        return "--"

    return str(value)


def twod_or_dash(item):
    if item is None:
        return "--"

    value = item.get("twod", item.get("result", "--"))

    if value is None or str(value).strip() == "":
        return "--"

    return str(value)


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
        return dt.strftime("%B %-d, %Y (%A)")
    except:
        try:
            dt = datetime.strptime(date_text, "%Y-%m-%d")
            return dt.strftime("%B %d, %Y (%A)").replace(" 0", " ")
        except:
            return str(date_text)


def build_today_response(raw_data):
    session_info = get_market_session()

    live = raw_data.get("live", {})
    result_list = raw_data.get("result", [])

    morning_1100 = find_by_time(result_list, "11:00:00")
    morning_1201 = find_by_time(result_list, "12:01:00")
    evening_1500 = find_by_time(result_list, "15:00:00")
    evening_1630 = find_by_time(result_list, "16:30:00")

    live_set = value_or_dash(live, "set")
    live_value = value_or_dash(live, "value")
    live_twod = twod_or_dash(live)

    live_date = str(live.get("date", session_info["date"]))
    live_time = str(live.get("time", "--"))

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

        "updatedAt": live_time,
        "serverTime": str(raw_data.get("server_time", "--")),

        "holiday": raw_data.get("holiday", {}),
        "cached": False,
        "dataSource": "ThaiStock2D API",
        "sourceUrl": THAI_LIVE_URL,
        "timezone": "Myanmar Time UTC+6:30"
    }


def normalize_history(raw_data):
    flat_history = []
    day_list = []

    if not isinstance(raw_data, list):
        return flat_history, day_list

    seen = set()

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
            }
        }

        day_list.append(day_data)

        # Old Android HistoryActivity အတွက် flat list ပြန်ပေးမယ်
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
                "value": market_value
            })

    return flat_history, day_list


@app.route("/")
def home():
    return jsonify({
        "success": True,
        "message": "MM 2D 3D API running with ThaiStock2D",
        "today": "/today",
        "history": "/history",
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
        raw_data = fetch_json(THAI_LIVE_URL)
        response = build_today_response(raw_data)

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
            "dataSource": "ThaiStock2D API",
            "count": len(flat_history),
            "daysCount": len(day_list),
            "history": flat_history,
            "days": day_list,
            "cached": False,
            "sourceUrl": THAI_RESULT_URL
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

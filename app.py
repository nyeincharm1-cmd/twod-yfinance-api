from flask import Flask, jsonify
from datetime import datetime, timedelta
import time
import os
import json
import ssl
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

FINMIND_API_URL = os.environ.get(
    "FINMIND_API_URL",
    "https://api.finmindtrade.com/api/v4/data"
)

FINMIND_TOKEN = os.environ.get(
    "FINMIND_TOKEN",
    ""
)

CACHE_SECONDS = 10
HISTORY_CACHE_SECONDS = 300
TW_CACHE_SECONDS = 300

cached_today = None
cached_today_time = 0

cached_history = None
cached_history_time = 0

cached_tw_info = None
cached_tw_time = 0


def myanmar_now():
    return datetime.utcnow() + timedelta(hours=6, minutes=30)


def taiwan_now():
    return datetime.utcnow() + timedelta(hours=8)


def fetch_json(url):
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Android) MM2D3DInfo/1.0",
            "Accept": "application/json,text/plain,*/*",
            "Accept-Encoding": "gzip, deflate, identity",
            "Connection": "close"
        }
    )

    try:
        ssl_context = None

        if "openapi.twse.com.tw" in url:
            ssl_context = ssl._create_unverified_context()

        with urlopen(request, timeout=30, context=ssl_context) as response:
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
                raise Exception("Empty response from " + url)

            if not body.startswith("{") and not body.startswith("["):
                raise Exception("Non JSON response from " + url + " => " + body[:200])

            return json.loads(body)

    except HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        raise Exception(body)


def build_url(base_url, params):
    query = urlencode(params)
    return base_url + "?" + query


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


def twod_or_dash(item):
    if item is None:
        return "--"

    value = item.get("twod", item.get("result", "--"))

    if value is None or str(value).strip() == "":
        return "--"

    text = str(value).strip()

    if len(text) == 1:
        return "0" + text

    return text[-2:]


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
    if not isinstance(item, dict):
        return "--"

    value = item.get("twod", None)

    if value is None:
        value = item.get("result", None)

    if value is None:
        value = item.get("number", None)

    if value is None:
        return "--"

    text = str(value).strip()

    if text == "":
        return "--"

    if len(text) == 1:
        return "0" + text

    return text[-2:]


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
        date_url = THAI_HISTORY_URL + "?date=" + date_iso
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


def get_tw_result_from_index(index_value):
    try:
        text = str(index_value).replace(",", "").strip()

        if text == "" or text == "--" or text.lower() == "none":
            return "--"

        if "." in text:
            decimal_part = text.split(".")[1]

            if len(decimal_part) >= 2:
                return decimal_part[:2]

            if len(decimal_part) == 1:
                return decimal_part + "0"

        digits = "".join(ch for ch in text if ch.isdigit())

        if len(digits) >= 2:
            return digits[-2:]

        return "--"

    except:
        return "--"


def normalize_finmind_items(raw_data):
    if isinstance(raw_data, list):
        return raw_data

    if not isinstance(raw_data, dict):
        return []

    data = raw_data.get("data", [])

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        rows = []

        keys = list(data.keys())
        if len(keys) == 0:
            return []

        first_value = data.get(keys[0])

        if isinstance(first_value, list):
            row_count = len(first_value)

            for i in range(row_count):
                row = {}

                for key in keys:
                    value_list = data.get(key, [])

                    if isinstance(value_list, list) and i < len(value_list):
                        row[key] = value_list[i]

                rows.append(row)

            return rows

    return []


def get_item_time_text(item):
    if not isinstance(item, dict):
        return ""

    value = item.get("date", "")

    if value is None or str(value).strip() == "":
        value = item.get("time", "")

    return str(value)


def get_taiex_value(item):
    if not isinstance(item, dict):
        return "--"

    possible_keys = [
        "TAIEX",
        "taiex",
        "TAIEXIndex",
        "index",
        "Index",
        "value",
        "Value",
        "close",
        "Close"
    ]

    for key in possible_keys:
        value = item.get(key)

        if value is not None and str(value).strip() != "":
            return str(value)

    return "--"


def get_finmind_tw_latest_info():
    global cached_tw_info
    global cached_tw_time

    now_time = time.time()

    if cached_tw_info is not None and cached_tw_info.get("result", "--") != "--":
        if now_time - cached_tw_time < TW_CACHE_SECONDS:
            return cached_tw_info

    info = {
        "result": "--",
        "latestTime": "--",
        "latestTAIEX": "--",
        "sourceUrl": FINMIND_API_URL,
        "dataset": "TaiwanVariousIndicators5Seconds",
        "startDate": "--",
        "endDate": "none",
        "count": 0,
        "error": "",
        "triedDates": []
    }

    # ဒီ dataset က end_date ထည့်လို့မရပါ
    # start_date တစ်ခုတည်းနဲ့ နောက်ပြန် 14 ရက်ထိ စမ်းမယ်
    for day_back in range(0, 14):
        check_date = (taiwan_now() - timedelta(days=day_back)).strftime("%Y-%m-%d")

        params = {
            "dataset": "TaiwanVariousIndicators5Seconds",
            "start_date": check_date
        }

        if FINMIND_TOKEN is not None and FINMIND_TOKEN.strip() != "":
            params["token"] = FINMIND_TOKEN.strip()

        url = build_url(FINMIND_API_URL, params)
        info["triedDates"].append(check_date)

        try:
            raw_data = fetch_json(url)
            items = normalize_finmind_items(raw_data)

            if len(items) == 0:
                if isinstance(raw_data, dict):
                    msg = raw_data.get("msg", "")
                    if msg:
                        info["error"] = str(msg)
                continue

            latest_item = None
            latest_time = ""

            for item in items:
                if not isinstance(item, dict):
                    continue

                time_text = get_item_time_text(item)

                if latest_item is None or time_text > latest_time:
                    latest_item = item
                    latest_time = time_text

            if latest_item is None:
                continue

            taiex_value = get_taiex_value(latest_item)
            tw_result = get_tw_result_from_index(taiex_value)

            if tw_result != "--":
                info["startDate"] = check_date
                info["count"] = len(items)
                info["latestTime"] = latest_time
                info["latestTAIEX"] = taiex_value
                info["result"] = tw_result
                info["error"] = ""

                cached_tw_info = info
                cached_tw_time = now_time

                return info

            info["error"] = "TAIEX field not found or invalid"

        except Exception as e:
            info["error"] = str(e)

    return info


def get_tw_result():
    info = get_finmind_tw_latest_info()
    return info.get("result", "--")


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
    tw_result = get_tw_result()

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
        "morningTW": tw_result,

        "eveningModern": modern_data["eveningModern"],
        "eveningInternet": modern_data["eveningInternet"],

        "updatedAt": live_time,
        "serverTime": str(live_data.get("server_time", "--")),

        "cached": False,
        "dataSource": "ThaiStock2D + FinMind API",
        "sourceUrl": THAI_LIVE_URL,
        "twSourceUrl": FINMIND_API_URL,
        "twDataset": "TaiwanVariousIndicators5Seconds",
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

    tw_result = get_tw_result()

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
            "morningTW": tw_result,
            "eveningModern": "--",
            "eveningInternet": "--"
        }

        if day_counter < max_days_to_enrich:
            modern_data = get_modern_internet_for_date(date_iso, False)
            modern_data["morningTW"] = tw_result

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
            "morningTW": modern_data["morningTW"],
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
                "morningTW": modern_data["morningTW"],
                "eveningModern": modern_data["eveningModern"],
                "eveningInternet": modern_data["eveningInternet"]
            })

    return flat_history, day_list


@app.route("/")
def home():
    return jsonify({
        "success": True,
        "message": "MM 2D 3D API running with ThaiStock2D + FinMind",
        "today": "/today",
        "history": "/history",
        "statusApi": "/status",
        "twCheck": "/tw-check",
        "dataSource": "ThaiStock2D + FinMind API"
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
            "dataSource": "ThaiStock2D + FinMind API",
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
            "dataSource": "ThaiStock2D + FinMind API",
            "count": len(flat_history),
            "daysCount": len(day_list),
            "history": flat_history,
            "days": day_list,
            "cached": False,
            "sourceUrl": THAI_RESULT_URL,
            "twSourceUrl": FINMIND_API_URL,
            "twDataset": "TaiwanVariousIndicators5Seconds"
        }

        cached_history = response
        cached_history_time = now_time

        return jsonify(response)

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e),
            "dataSource": "ThaiStock2D + FinMind API",
            "cached": False
        }), 500


@app.route("/tw-check")
def tw_check():
    info = get_finmind_tw_latest_info()

    return jsonify({
        "success": True,
        "source": "FinMind",
        "sourceUrl": FINMIND_API_URL,
        "dataset": info.get("dataset", "TaiwanVariousIndicators5Seconds"),
        "startDate": info.get("startDate", "--"),
        "endDate": info.get("endDate", "none"),
        "triedDates": info.get("triedDates", []),
        "count": info.get("count", 0),
        "latestTime": info.get("latestTime", "--"),
        "latestTAIEX": info.get("latestTAIEX", "--"),
        "finalTW": info.get("result", "--"),
        "error": info.get("error", "")
    })


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

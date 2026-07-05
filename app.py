from flask import Flask, jsonify
import yfinance as yf
from datetime import datetime, timedelta

app = Flask(__name__)

SYMBOL = "^SET.BK"

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

@app.route("/")
def home():
    return jsonify({
        "success": True,
        "message": "YFinance SET API running"
    })

@app.route("/today")
def today():
    try:
        ticker = yf.Ticker(SYMBOL)

        # last 5 days 1 minute data
        hist = ticker.history(period="5d", interval="1m")

        if hist is None or hist.empty:
            return jsonify({
                "success": False,
                "message": "No market data found"
            }), 404

        hist = hist.dropna()

        if hist.empty:
            return jsonify({
                "success": False,
                "message": "No valid market data found"
            }), 404

        last_row = hist.tail(1).iloc[0]

        close_price = float(last_row["Close"])

        try:
            market_value = int(last_row["Volume"])
        except:
            market_value = 0

        # Example: SET 1342.56 -> 56
        set_decimal_two = get_set_decimal_two(close_price)

        # 2D rule:
        # SET last decimal digit + Value last digit
        # 1342.56 + 45821900 => 6 + 0 = 60
        set_last_digit = set_decimal_two[-1]
        value_last_digit = get_last_digit(market_value)

        result_2d = set_last_digit + value_last_digit

        thailand_time = datetime.utcnow() + timedelta(hours=7)

        return jsonify({
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

            "updatedAt": thailand_time.strftime("%Y-%m-%d %H:%M:%S")
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

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

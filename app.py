from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({
        "success": True,
        "message": "API running"
    })

@app.route("/today")
def today():
    return jsonify({
        "success": True,
        "date": "2026-07-06",
        "set": "1234.56",
        "value": "987654",
        "morningResult": "56",
        "eveningResult": "56"
    })

@app.route("/status")
def status():
    return jsonify({
        "success": True,
        "status": "OPEN",
        "session": "morning",
        "current": "test"
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)

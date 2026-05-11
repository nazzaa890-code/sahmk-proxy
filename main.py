from flask import Flask, jsonify, request
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)  # يسمح لأي موقع يتصل بالسيرفر

SAHMK_KEY = "shmk_live_660edcf31ba6d20dce46460f446ac851d758a73ade00c1ba"
SAHMK_BASE = "https://app.sahmk.sa/api/v1"

@app.route("/quote/<symbol>")
def quote(symbol):
    try:
        res = requests.get(
            f"{SAHMK_BASE}/quote/{symbol}/",
            headers={"X-API-Key": SAHMK_KEY},
            timeout=10
        )
        return jsonify(res.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/quotes")
def quotes():
    """جلب أسعار عدة أسهم دفعة واحدة"""
    symbols = request.args.get("symbols", "").split(",")
    results = {}
    for sym in symbols:
        sym = sym.strip()
        if not sym:
            continue
        try:
            res = requests.get(
                f"{SAHMK_BASE}/quote/{sym}/",
                headers={"X-API-Key": SAHMK_KEY},
                timeout=10
            )
            results[sym] = res.json()
        except Exception as e:
            results[sym] = {"error": str(e)}
    return jsonify(results)

@app.route("/health")
def health():
    return jsonify({"status": "ok", "message": "SAHMK Proxy يعمل!"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

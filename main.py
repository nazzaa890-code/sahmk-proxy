from flask import Flask, jsonify, request
from flask_cors import CORS
import requests, os, json, re

app = Flask(__name__)
CORS(app)

SAHMK_KEY = "shmk_live_660edcf31ba6d20dce46460f446ac851d758a73ade00c1ba"
SAHMK_BASE = "https://app.sahmk.sa/api/v1"
CLAUDE_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_URL = "https://api.anthropic.com/v1/messages"

def claude_call(prompt, max_tokens=1000):
    res = requests.post(CLAUDE_URL, headers={
        "Content-Type": "application/json",
        "x-api-key": CLAUDE_KEY,
        "anthropic-version": "2023-06-01"
    }, json={
        "model": "claude-sonnet-4-20250514",
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}]
    }, timeout=30)
    return res.json().get("content", [{}])[0].get("text", "")

@app.route("/quote/<symbol>")
def quote(symbol):
    try:
        res = requests.get(f"{SAHMK_BASE}/quote/{symbol}/",
            headers={"X-API-Key": SAHMK_KEY}, timeout=10)
        return jsonify(res.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/quotes")
def quotes():
    symbols = request.args.get("symbols", "").split(",")
    results = {}
    for sym in [s.strip() for s in symbols if s.strip()]:
        try:
            res = requests.get(f"{SAHMK_BASE}/quote/{sym}/",
                headers={"X-API-Key": SAHMK_KEY}, timeout=8)
            results[sym] = res.json()
        except Exception as e:
            results[sym] = {"error": str(e)}
    return jsonify(results)

@app.route("/us_quote/<symbol>")
def us_quote(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=10)
        data = res.json()
        meta = data["chart"]["result"][0]["meta"]
        price = meta.get("regularMarketPrice", 0)
        prev = meta.get("chartPreviousClose", price)
        change = price - prev
        change_pct = (change / prev * 100) if prev else 0
        volume = meta.get("regularMarketVolume", 0)
        return jsonify({
            "symbol": symbol,
            "price": round(price, 2),
            "change": round(change, 2),
            "change_percent": round(change_pct, 2),
            "volume": volume,
            "source": "yahoo"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/us_quotes")
def us_quotes():
    symbols = request.args.get("symbols", "").split(",")
    results = {}
    for sym in [s.strip() for s in symbols if s.strip()]:
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
            headers = {"User-Agent": "Mozilla/5.0"}
            res = requests.get(url, headers=headers, timeout=8)
            data = res.json()
            meta = data["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice", 0)
            prev = meta.get("chartPreviousClose", price)
            change = price - prev
            change_pct = (change / prev * 100) if prev else 0
            volume = meta.get("regularMarketVolume", 0)
            results[sym] = {
                "price": round(price, 2),
                "change": round(change, 2),
                "change_percent": round(change_pct, 2),
                "volume": volume,
                "source": "yahoo"
            }
        except Exception as e:
            results[sym] = {"error": str(e)}
    return jsonify(results)

@app.route("/news", methods=["POST"])
def get_news():
    if not CLAUDE_KEY:
        return jsonify({"error": "ANTHROPIC_API_KEY مفقود"}), 500
    try:
        data = request.get_json()
        stocks = data.get("stocks", [])
        market = data.get("market", "SA")
        syms = "، ".join([f"{s['code']} {s['name']}" for s in stocks])
        ctx = "سوق تداول السعودي" if market == "SA" else "السوق الأمريكي NYSE/NASDAQ"
        prompt = f'محلل مالي في {ctx}. للأسهم: {syms}\nلكل سهم خبرين واقعيين.\nأجب بـ JSON فقط:\n{{"stocks":{{"رمز":{{"news":[{{"headline":"نص","sentiment":"positive|negative|neutral","source":"مصدر","time":"منذ X ساعة"}}],"overall_sentiment":"positive|negative|neutral"}}}}}}'
        text = claude_call(prompt)
        text = re.sub(r'```json|```', '', text).strip()
        return jsonify(json.loads(text))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/analyze", methods=["POST"])
def analyze_stock():
    if not CLAUDE_KEY:
        return jsonify({"error": "ANTHROPIC_API_KEY مفقود"}), 500
    try:
        d = request.get_json()
        sa = d.get("market", "SA") == "SA"
        cu = "ريال" if sa else "دولار"
        news_str = "\n".join([f"- {n['headline']} ({n['sentiment']})" for n in d.get("news", [])]) or "لا أخبار"
        prompt = f"""محلل مضاربة يومية {"تاسي" if sa else "أمريكي"}. تحليل موجز:

{d['code']} {d['name']} — {d['sector']}
السعر: {d['price']} {cu} ({d['change_pct']}%)
RSI:{d['rsi']} | Stoch:{d['stoch']} | MACD:{d['macd']}
حجم:{d['vol_m']}x | ATR:{d['atr']}% | قوة:{d['score']}/100

الأخبار:
{news_str}

5 نقاط:
1. توصية + سبب
2. دخول ووقف خسارة ({cu})
3. الهدف اليومي
4. تأثير الأخبار
5. أبرز مخاطرة"""
        text = claude_call(prompt)
        return jsonify({"analysis": text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "sa_market": "سهمك API",
        "us_market": "Yahoo Finance",
        "claude": "متصل" if CLAUDE_KEY else "مفتاح مفقود"
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

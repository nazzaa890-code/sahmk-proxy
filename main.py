from flask import Flask, jsonify, request
from flask_cors import CORS
import requests, os, json, re
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

SAHMK_KEY  = os.environ.get("SAHMK_API_KEY", "")
SAHMK_BASE = "https://app.sahmk.sa/api/v1"
CLAUDE_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_URL = "https://api.anthropic.com/v1/messages"
FINNHUB_KEY= os.environ.get("FINNHUB_API_KEY", "")
FINNHUB_URL= "https://finnhub.io/api/v1"

def claude_call(prompt, max_tokens=1000):
    if not CLAUDE_KEY:
        return "مفتاح Claude API مفقود"
    try:
        res = requests.post(CLAUDE_URL, headers={
            "Content-Type": "application/json",
            "x-api-key": CLAUDE_KEY,
            "anthropic-version": "2023-06-01"
        }, json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}]
        }, timeout=30)
        data = res.json()
        return data.get("content", [{}])[0].get("text", "")
    except Exception as e:
        return f"خطأ: {str(e)}"

@app.route("/quote/<symbol>")
def quote(symbol):
    if not SAHMK_KEY:
        return jsonify({"error": "SAHMK_API_KEY مفقود"}), 500
    try:
        res = requests.get(f"{SAHMK_BASE}/quote/{symbol}/",
            headers={"X-API-Key": SAHMK_KEY}, timeout=10)
        return jsonify(res.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/quotes")
def quotes():
    if not SAHMK_KEY:
        return jsonify({"error": "SAHMK_API_KEY مفقود"}), 500
    symbols = [s.strip() for s in request.args.get("symbols","").split(",") if s.strip()]
    results = {}
    for sym in symbols:
        try:
            res = requests.get(f"{SAHMK_BASE}/quote/{sym}/",
                headers={"X-API-Key": SAHMK_KEY}, timeout=8)
            results[sym] = res.json()
        except Exception as e:
            results[sym] = {"error": str(e)}
    return jsonify(results)

@app.route("/us_quote/<symbol>")
def us_quote(symbol):
    if not FINNHUB_KEY:
        return jsonify({"error": "FINNHUB_API_KEY مفقود"}), 500
    try:
        res = requests.get(f"{FINNHUB_URL}/quote",
            params={"symbol": symbol, "token": FINNHUB_KEY}, timeout=10)
        data = res.json()
        price  = float(data.get("c", 0))
        prev   = float(data.get("pc", price))
        change = float(data.get("d", price - prev))
        chgpct = float(data.get("dp", 0))
        return jsonify({
            "symbol": symbol,
            "price": round(price, 2),
            "change": round(change, 2),
            "change_percent": round(chgpct, 2),
            "volume": 0,
            "source": "finnhub"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/us_quotes")
def us_quotes():
    if not FINNHUB_KEY:
        return jsonify({"error": "FINNHUB_API_KEY مفقود"}), 500
    symbols = [s.strip() for s in request.args.get("symbols","").split(",") if s.strip()]
    results = {}
    for sym in symbols:
        try:
            res = requests.get(f"{FINNHUB_URL}/quote",
                params={"symbol": sym, "token": FINNHUB_KEY}, timeout=8)
            data = res.json()
            price  = float(data.get("c", 0))
            prev   = float(data.get("pc", price))
            change = float(data.get("d", price - prev))
            chgpct = float(data.get("dp", 0))
            results[sym] = {
                "price": round(price, 2),
                "change": round(change, 2),
                "change_percent": round(chgpct, 2),
                "volume": 0,
                "source": "finnhub"
            }
        except Exception as e:
            results[sym] = {"error": str(e)}
    return jsonify(results)

@app.route("/us_news/<symbol>")
def us_news(symbol):
    if not FINNHUB_KEY:
        return jsonify({"error": "FINNHUB_API_KEY مفقود"}), 500
    try:
        today    = datetime.now().strftime("%Y-%m-%d")
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        res = requests.get(f"{FINNHUB_URL}/company-news",
            params={"symbol": symbol, "from": week_ago, "to": today, "token": FINNHUB_KEY},
            timeout=10)
        news = res.json()[:5]
        return jsonify({"news": news})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/news", methods=["POST"])
def get_news():
    if not CLAUDE_KEY:
        return jsonify({"error": "ANTHROPIC_API_KEY مفقود"}), 500
    try:
        data   = request.get_json()
        stocks = data.get("stocks", [])
        market = data.get("market", "SA")
        syms   = "، ".join([f"{s['code']} {s['name']}" for s in stocks])
        ctx    = "سوق تداول السعودي" if market == "SA" else "السوق الأمريكي"
        prompt = f'محلل مالي في {ctx}. للأسهم: {syms}\nلكل سهم خبرين واقعيين.\nأجب بـ JSON فقط:\n{{"stocks":{{"رمز":{{"news":[{{"headline":"نص","sentiment":"positive|negative|neutral","source":"مصدر","time":"منذ X ساعة"}}],"overall_sentiment":"positive|negative|neutral"}}}}}}'
        text = claude_call(prompt)
        text = re.sub(r'```json|```', '', text).strip()
        try:
            return jsonify(json.loads(text))
        except:
            return jsonify({"stocks": {s['code']: {"news":[],"overall_sentiment":"neutral"} for s in stocks}})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/analyze", methods=["POST"])
def analyze_stock():
    if not CLAUDE_KEY:
        return jsonify({"error": "ANTHROPIC_API_KEY مفقود"}), 500
    try:
        d  = request.get_json()
        sa = d.get("market", "SA") == "SA"
        cu = "ريال" if sa else "دولار"
        news_str = "\n".join([f"- {n['headline']} ({n['sentiment']})" for n in d.get("news",[])]) or "لا أخبار"
        prompt = f"""محلل مضاربة يومية {"تاسي" if sa else "أمريكي"}. تحليل موجز:

{d.get('code')} {d.get('name')} — {d.get('sector')}
السعر: {d.get('price')} {cu} ({d.get('change_pct')}%)
RSI:{d.get('rsi')} | Stoch:{d.get('stoch')} | MACD:{d.get('macd')}
حجم:{d.get('vol_m')}x | ATR:{d.get('atr')}% | قوة:{d.get('score')}/100

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
        "sahmk":   "✅" if SAHMK_KEY  else "❌ مفقود",
        "finnhub": "✅" if FINNHUB_KEY else "❌ مفقود",
        "claude":  "✅" if CLAUDE_KEY  else "❌ مفقود",
        "version": "3.0"
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

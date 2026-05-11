from flask import Flask, jsonify, request
from flask_cors import CORS
import requests, os, json, re
from datetime import datetime

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# =====================================================
# إصلاح 1: استخدام متغيرات بيئة بدلاً من مفاتيح مكتوبة
# =====================================================
SAHMK_KEY = os.environ.get("SAHMK_API_KEY", "")
SAHMK_BASE = "https://app.sahmk.sa/api/v1"

CLAUDE_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_URL = "https://api.anthropic.com/v1/messages"

# =====================================================
# إصلاح 2: دالة claude_call محسّنة مع معالجة أخطاء أفضل
# =====================================================
def claude_call(prompt, max_tokens=1000):
    if not CLAUDE_KEY:
        return "مفتاح Claude API مفقود. يرجى إضافة ANTHROPIC_API_KEY في متغيرات البيئة."
    
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
        
        if not res.ok:
            return f"خطأ في Claude API: {res.status_code} - {res.text[:200]}"
        
        data = res.json()
        if "content" in data and len(data["content"]) > 0:
            return data["content"][0].get("text", "")
        return "رد فارغ من Claude"
    except requests.exceptions.Timeout:
        return "انتهت مهلة الاتصال بـ Claude API (30 ثانية)"
    except requests.exceptions.ConnectionError:
        return "فشل الاتصال بـ Claude API"
    except Exception as e:
        return f"خطأ غير متوقع: {str(e)}"

# =====================================================
# إصلاح 3: دالة مساعدة للتحقق من مفتاح SAHMK
# =====================================================
def check_sahmk_key():
    if not SAHMK_KEY:
        return False, "مفتاح SAHMK API مفقود. يرجى إضافة SAHMK_API_KEY في متغيرات البيئة."
    return True, None

# =====================================================
# إصلاح 4: endpoint /quote محسّن
# =====================================================
@app.route("/quote/<symbol>")
def quote(symbol):
    valid, error = check_sahmk_key()
    if not valid:
        return jsonify({"error": error}), 500
    
    try:
        res = requests.get(f"{SAHMK_BASE}/quote/{symbol}/",
            headers={"X-API-Key": SAHMK_KEY}, timeout=10)
        
        if res.status_code == 401:
            return jsonify({"error": "مفتاح SAHMK API غير صالح"}), 401
        if res.status_code == 429:
            return jsonify({"error": "تم تجاوز حد الطلبات - جرب لاحقاً"}), 429
        
        return jsonify(res.json())
    except requests.exceptions.Timeout:
        return jsonify({"error": "انتهت مهلة الاتصال بـ SAHMK API"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "فشل الاتصال بـ SAHMK API"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# =====================================================
# إصلاح 5: endpoint /quotes محسّن مع batch أفضل
# =====================================================
@app.route("/quotes")
def quotes():
    valid, error = check_sahmk_key()
    if not valid:
        return jsonify({"error": error}), 500
    
    symbols = request.args.get("symbols", "").split(",")
    symbols = [s.strip() for s in symbols if s.strip()]
    
    if not symbols:
        return jsonify({"error": "لا توجد رموز أسهم محددة"}), 400
    
    # إصلاح: استخدام endpoint batch quotes إذا كان متاحاً
    if len(symbols) > 1:
        try:
            symbols_param = ",".join(symbols)
            res = requests.get(f"{SAHMK_BASE}/quotes/?symbols={symbols_param}",
                headers={"X-API-Key": SAHMK_KEY}, timeout=15)
            
            if res.ok:
                data = res.json()
                results = {}
                if "quotes" in data:
                    for q in data["quotes"]:
                        sym = q.get("symbol", "")
                        if sym:
                            results[sym] = q
                return jsonify(results)
        except:
            pass  # fallback to individual requests
    
    # طلب فردي لكل سهم
    results = {}
    for sym in symbols:
        try:
            res = requests.get(f"{SAHMK_BASE}/quote/{sym}/",
                headers={"X-API-Key": SAHMK_KEY}, timeout=8)
            results[sym] = res.json() if res.ok else {"error": f"HTTP {res.status_code}"}
        except Exception as e:
            results[sym] = {"error": str(e)}
    return jsonify(results)

# =====================================================
# إصلاح 6: endpoint /us_quote محسّن
# =====================================================
@app.route("/us_quote/<symbol>")
def us_quote(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        res = requests.get(url, headers=headers, timeout=10)
        
        if not res.ok:
            return jsonify({"error": f"Yahoo API error: {res.status_code}"}), res.status_code
        
        data = res.json()
        if "chart" not in data or "result" not in data["chart"] or not data["chart"]["result"]:
            return jsonify({"error": "لا توجد بيانات متاحة لهذا السهم"}), 404
        
        meta = data["chart"]["result"][0]["meta"]
        price = meta.get("regularMarketPrice", 0)
        prev = meta.get("chartPreviousClose", price) or meta.get("previousClose", price)
        change = price - prev if price and prev else 0
        change_pct = (change / prev * 100) if prev and prev != 0 else 0
        volume = meta.get("regularMarketVolume", 0)
        
        return jsonify({
            "symbol": symbol,
            "price": round(price, 2),
            "change": round(change, 2),
            "change_percent": round(change_pct, 2),
            "volume": volume,
            "source": "yahoo",
            "timestamp": datetime.now().isoformat()
        })
    except requests.exceptions.Timeout:
        return jsonify({"error": "انتهت مهلة الاتصال بـ Yahoo Finance"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "فشل الاتصال بـ Yahoo Finance"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# =====================================================
# إصلاح 7: endpoint /us_quotes محسّن
# =====================================================
@app.route("/us_quotes")
def us_quotes():
    symbols = request.args.get("symbols", "").split(",")
    symbols = [s.strip() for s in symbols if s.strip()]
    
    if not symbols:
        return jsonify({"error": "لا توجد رموز أسهم محددة"}), 400
    
    results = {}
    for sym in symbols:
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            res = requests.get(url, headers=headers, timeout=8)
            
            if not res.ok:
                results[sym] = {"error": f"Yahoo API error: {res.status_code}"}
                continue
            
            data = res.json()
            if "chart" not in data or "result" not in data["chart"] or not data["chart"]["result"]:
                results[sym] = {"error": "لا توجد بيانات متاحة"}
                continue
            
            meta = data["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice", 0)
            prev = meta.get("chartPreviousClose", price) or meta.get("previousClose", price)
            change = price - prev if price and prev else 0
            change_pct = (change / prev * 100) if prev and prev != 0 else 0
            volume = meta.get("regularMarketVolume", 0)
            
            results[sym] = {
                "price": round(price, 2),
                "change": round(change, 2),
                "change_percent": round(change_pct, 2),
                "volume": volume,
                "source": "yahoo",
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            results[sym] = {"error": str(e)}
    return jsonify(results)

# =====================================================
# إصلاح 8: endpoint /news محسّن
# =====================================================
@app.route("/news", methods=["POST"])
def get_news():
    if not CLAUDE_KEY:
        return jsonify({"error": "ANTHROPIC_API_KEY مفقود"}), 500
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "لا توجد بيانات مرسلة"}), 400
        
        stocks = data.get("stocks", [])
        if not stocks:
            return jsonify({"error": "لا توجد أسهم محددة"}), 400
        
        market = data.get("market", "SA")
        syms = "، ".join([f"{s['code']} {s['name']}" for s in stocks])
        ctx = "سوق تداول السعودي" if market == "SA" else "السوق الأمريكي NYSE/NASDAQ"
        
        prompt = f'محلل مالي في {ctx}. للأسهم: {syms}\nلكل سهم خبرين واقعيين.\nأجب بـ JSON فقط:\n{{"stocks":{{"رمز":{{"news":[{{"headline":"نص","sentiment":"positive|negative|neutral","source":"مصدر","time":"منذ X ساعة"}}],"overall_sentiment":"positive|negative|neutral"}}}}}}'
        
        text = claude_call(prompt)
        
        if text.startswith("خطأ") or text.startswith("مفتاح"):
            return jsonify({"error": text}), 500
        
        text = re.sub(r'```json|```', '', text).strip()
        
        try:
            parsed = json.loads(text)
            return jsonify(parsed)
        except json.JSONDecodeError:
            # إصلاح: إرجاع هيكل JSON صحيح حتى لو فشل Claude
            fallback = {"stocks": {}}
            for s in stocks:
                fallback["stocks"][s['code']] = {
                    "news": [],
                    "overall_sentiment": "neutral"
                }
            return jsonify(fallback)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# =====================================================
# إصلاح 9: endpoint /analyze محسّن
# =====================================================
@app.route("/analyze", methods=["POST"])
def analyze_stock():
    if not CLAUDE_KEY:
        return jsonify({"error": "ANTHROPIC_API_KEY مفقود"}), 500
    
    try:
        d = request.get_json()
        if not d:
            return jsonify({"error": "لا توجد بيانات مرسلة"}), 400
        
        sa = d.get("market", "SA") == "SA"
        cu = "ريال" if sa else "دولار"
        
        news_list = d.get("news", [])
        news_str = "\n".join([f"- {n['headline']} ({n['sentiment']})" for n in news_list]) if news_list else "لا أخبار"
        
        prompt = f"""محلل مضاربة يومية {"تاسي" if sa else "أمريكي"}. تحليل موجز:

{d.get('code', 'N/A')} {d.get('name', 'N/A')} — {d.get('sector', 'N/A')}
السعر: {d.get('price', 'N/A')} {cu} ({d.get('change_pct', 'N/A')}%)
RSI:{d.get('rsi', 'N/A')} | Stoch:{d.get('stoch', 'N/A')} | MACD:{d.get('macd', 'N/A')}
حجم:{d.get('vol_m', 'N/A')}x | ATR:{d.get('atr', 'N/A')}% | قوة:{d.get('score', 'N/A')}/100

الأخبار:
{news_str}

5 نقاط:
1. توصية + سبب
2. دخول ووقف خسارة ({cu})
3. الهدف اليومي
4. تأثير الأخبار
5. أبرز مخاطرة"""
        
        text = claude_call(prompt)
        
        if text.startswith("خطأ") or text.startswith("مفتاح"):
            return jsonify({"error": text}), 500
        
        return jsonify({"analysis": text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# =====================================================
# إصلاح 10: endpoint /health محسّن
# =====================================================
@app.route("/health")
def health():
    sahmk_status = "متصل" if SAHMK_KEY else "مفتاح مفقود"
    claude_status = "متصل" if CLAUDE_KEY else "مفتاح مفقود"
    
    # التحقق من SAHMK API
    if SAHMK_KEY:
        try:
            res = requests.get(f"{SAHMK_BASE}/quote/2222/",
                headers={"X-API-Key": SAHMK_KEY}, timeout=5)
            if res.ok:
                sahmk_status = "متصل ✅"
            else:
                sahmk_status = f"خطأ {res.status_code}"
        except:
            sahmk_status = "غير متصل ❌"
    
    return jsonify({
        "status": "ok",
        "sa_market": "سهمك API",
        "us_market": "Yahoo Finance",
        "sahmk_api": sahmk_status,
        "claude": claude_status,
        "timestamp": datetime.now().isoformat(),
        "version": "2.0"
    })

# =====================================================
# إضافة: endpoint جديد /market/summary
# =====================================================
@app.route("/market_summary")
def market_summary():
    valid, error = check_sahmk_key()
    if not valid:
        return jsonify({"error": error}), 500
    
    try:
        res = requests.get(f"{SAHMK_BASE}/market/summary/",
            headers={"X-API-Key": SAHMK_KEY}, timeout=10)
        return jsonify(res.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# =====================================================
# إضافة: endpoint جديد /market/sectors
# =====================================================
@app.route("/market_sectors")
def market_sectors():
    valid, error = check_sahmk_key()
    if not valid:
        return jsonify({"error": error}), 500
    
    try:
        res = requests.get(f"{SAHMK_BASE}/market/sectors/",
            headers={"X-API-Key": SAHMK_KEY}, timeout=10)
        return jsonify(res.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

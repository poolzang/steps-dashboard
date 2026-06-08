from flask import Flask, render_template, request, jsonify, send_file
import json, csv, io, os, requests
from datetime import datetime, timedelta
import random

app = Flask(__name__)
DATA_FILE = "data.json"
SETTINGS_FILE = "settings.json"
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY", "")

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"goal": 10000}

def save_settings(s):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False)

def generate_sample():
    weathers = ["맑음","맑음","구름많음","흐림","비","맑음","구름많음"]
    records = []
    base = datetime(2025, 3, 1)
    for i in range(90):
        dt = base + timedelta(days=i)
        mo = dt.month - 3
        base_temp = 5 + mo * 2.5
        tmax = round(base_temp + 8 + random.uniform(0, 6), 1)
        tmin = round(base_temp - 2 + random.uniform(0, 4), 1)
        weather = random.choice(weathers)
        humidity = random.randint(35, 80)
        sleep = round(random.uniform(5.5, 8.5), 1)
        rain = -2500 if weather == "비" else 0
        steps = max(1500, int(7500 + (tmax-15)*150 + rain + (sleep-7)*300 + random.gauss(0,1200)))
        records.append({"date": dt.strftime("%Y-%m-%d"), "steps": steps,
            "tmax": tmax, "tmin": tmin, "weather": weather,
            "humidity": humidity, "sleep": sleep, "goal": 10000})
    return records

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return generate_sample()

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

def get_today_weather():
    if not WEATHER_API_KEY:
        return None
    try:
        now = datetime.now()
        # base_time은 1시간 전 정시로
        base_time = (now - timedelta(hours=1)).strftime("%H00")
        base_date = now.strftime("%Y%m%d")
        nx, ny = 60, 127  # 서울 좌표
        url = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst"
        params = {
            "serviceKey": WEATHER_API_KEY,
            "numOfRows": 10, "pageNo": 1,
            "dataType": "JSON",
            "base_date": base_date,
            "base_time": base_time,
            "nx": nx, "ny": ny,
        }
        res = requests.get(url, params=params, timeout=5)
        items = res.json()["response"]["body"]["items"]["item"]
        result = {}
        for item in items:
            if item["category"] == "T1H":
                result["temp"] = float(item["obsrValue"])
            if item["category"] == "REH":
                result["humidity"] = int(item["obsrValue"])
            if item["category"] == "PTY":
                pty = int(item["obsrValue"])
                result["weather"] = "비" if pty in [1,4] else "눈" if pty in [2,3] else "맑음"
            if item["category"] == "SKY" and "weather" not in result:
                sky = int(item["obsrValue"])
                result["weather"] = "맑음" if sky==1 else "구름많음" if sky==3 else "흐림"
        return result
    except Exception as e:
        print("날씨 API 오류:", e)
        return None

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/data")
def get_data():
    return jsonify(load_data())

@app.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify(load_settings())

@app.route("/api/settings", methods=["POST"])
def update_settings():
    settings = load_settings()
    settings.update(request.json)
    save_settings(settings)
    if "goal" in request.json:
        data = load_data()
        for d in data:
            d["goal"] = request.json["goal"]
        save_data(data)
    return jsonify({"ok": True})

@app.route("/api/weather/today")
def today_weather():
    w = get_today_weather()
    now = datetime.now()
    result = {
        "date": now.strftime("%Y-%m-%d"),
        "dateKr": now.strftime("%Y년 %m월 %d일"),
        "weekday": ["월","화","수","목","금","토","일"][now.weekday()],
        "time": now.strftime("%H:%M"),
    }
    if w: result.update(w)
    return jsonify(result)

@app.route("/api/add", methods=["POST"])
def add_entry():
    data = load_data()
    entry = request.json
    entry["goal"] = load_settings().get("goal", 10000)
    idx = next((i for i,d in enumerate(data) if d["date"]==entry["date"]), None)
    if idx is not None: data[idx] = entry
    else: data.append(entry)
    save_data(data)
    return jsonify({"ok": True})

@app.route("/api/delete", methods=["POST"])
def delete_entry():
    data = [d for d in load_data() if d["date"] != request.json.get("date")]
    save_data(data)
    return jsonify({"ok": True})

@app.route("/api/delete-all", methods=["POST"])
def delete_all():
    save_data(generate_sample())
    return jsonify({"ok": True})

@app.route("/api/export")
def export_csv():
    data = sorted(load_data(), key=lambda d: d["date"])
    si = io.StringIO()
    writer = csv.DictWriter(si, fieldnames=["date","steps","tmax","tmin","weather","humidity","sleep","goal"])
    writer.writeheader(); writer.writerows(data)
    output = io.BytesIO(si.getvalue().encode("utf-8-sig"))
    return send_file(output, mimetype="text/csv", as_attachment=True, download_name="steps_data.csv")

@app.route("/api/import", methods=["POST"])
def import_csv():
    file = request.files.get("file")
    if not file: return jsonify({"ok": False})
    content = file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    data = load_data(); added = 0
    for row in reader:
        try:
            entry = {
                "date": row.get("날짜") or row.get("date",""),
                "steps": int(row.get("걸음수") or row.get("steps",0)),
                "tmax": float(row.get("최고기온") or row.get("tmax",20)),
                "tmin": float(row.get("최저기온") or row.get("tmin",10)),
                "weather": row.get("날씨") or row.get("weather","맑음"),
                "humidity": int(row.get("습도") or row.get("humidity",60)),
                "sleep": float(row.get("수면시간") or row.get("sleep",7)),
                "goal": int(row.get("목표걸음수") or row.get("goal",10000)),
            }
            if entry["date"] and entry["steps"]:
                idx = next((i for i,d in enumerate(data) if d["date"]==entry["date"]), None)
                if idx is not None: data[idx] = entry
                else: data.append(entry); added += 1
        except: continue
    save_data(data)
    return jsonify({"ok": True, "added": added})

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

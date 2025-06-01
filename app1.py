from flask import Flask, render_template, request, jsonify,
import datetime
import os
import threading
import csv
import atexit
import utm

app = Flask(__name__)
DUMMY_MODE = os.getenv("DUMMY_MODE", "True").lower() == "true"
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

log_lock = threading.Lock()
current_log_file = None
current_log_writer = None
current_log_hour = None

def get_dummy_sensor_data():
    return {
        "lat": 35.681236,
        "lon": 139.767125,
        "hdop": 0.7,
        "vdop": 1.0,
        "heading": 60,
        "imu_x": 0.02,
        "imu_y": 0.01,
        "imu_z": 0.98
    }

def get_real_sensor_data():
    return get_dummy_sensor_data()  # 実機実装時に変更

def get_sensor_data():
    data = get_dummy_sensor_data() if DUMMY_MODE else get_real_sensor_data()
    utm_coords = utm.from_latlon(data["lat"], data["lon"])
    data["utm_easting"] = utm_coords[0]
    data["utm_northing"] = utm_coords[1]
    data["utm_zone"] = utm_coords[2]
    data["utm_letter"] = utm_coords[3]
    return data

def open_log_file(dt):
    filename = dt.strftime("%Y%m%d_%H") + ".csv"
    path = os.path.join(LOG_DIR, filename)
    need_header = not os.path.exists(path)
    f = open(path, "a", encoding="utf-8", newline="")
    writer = csv.writer(f)
    if need_header:
        writer.writerow(["time", "lat", "lon", "hdop", "vdop", "heading", "imu_x", "imu_y", "imu_z"])
    return f, writer

def write_log(data):
    global current_log_file, current_log_writer, current_log_hour
    now = datetime.datetime.utcnow()
    with log_lock:
        if current_log_file is None or current_log_hour != now.hour:
            if current_log_file:
                current_log_file.close()
            current_log_file, current_log_writer = open_log_file(now)
            current_log_hour = now.hour
        try:
            data["time"] = datetime.datetime.fromisoformat(data["time"].replace("Z", "+00:00")).isoformat()
        except (KeyError, ValueError):
            data["time"] = now.isoformat()
        current_log_writer.writerow([
            data["time"], data["lat"], data["lon"], data["hdop"],
            data["vdop"], data["heading"], data["imu_x"], data["imu_y"], data["imu_z"]
        ])
        current_log_file.flush()

def cleanup():
    global current_log_file
    with log_lock:
        if current_log_file:
            current_log_file.close()

atexit.register(cleanup)

@app.route("/")
def index():
    return render_template("index.html", dummy_mode=DUMMY_MODE)

@app.route("/get_data")
def get_data():
    return jsonify(get_sensor_data())

@app.route("/log", methods=["POST"])
def log():
    if not request.is_json:
        return jsonify({"error": "ログデータの送信に失敗しました。JSON形式のデータが必要です。"}), 400
    data = request.get_json()
    required_keys = ["time", "lat", "lon", "hdop", "vdop", "heading", "imu_x", "imu_y", "imu_z"]
    if not all(key in data for key in required_keys):
        return jsonify({"error": "ログデータに必要なフィールドが不足しています。必要なフィールド: " + ", ".join(required_keys)}), 400
    try:
        for key in ["lat", "lon", "hdop", "vdop", "heading", "imu_x", "imu_y", "imu_z"]:
            if not isinstance(data[key], (int, float)):
                return jsonify({"error": f"フィールド '{key}' のデータ型が不正です。数値を指定してください。"}), 400
        write_log(data)
        return jsonify({"message": "ログを正常に記録しました。"})
    except Exception as e:
        return jsonify({"error": f"ログの記録中にエラーが発生しました: {str(e)}"}), 500

if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "False").lower() == "true"
    app.run(debug=debug, threaded=True)

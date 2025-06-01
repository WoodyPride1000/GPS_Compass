from flask import Flask, jsonify, render_template
import serial
import pynmea2
import math
import threading
import time
import random  # 実デバイスがない場合のダミー
try:
    from mpu6050 import mpu6050
    IMU_AVAILABLE = True
except ImportError:
    IMU_AVAILABLE = False

app = Flask(__name__)

# --- 設定 ---
GPS_BASE_PORT = '/dev/ttyUSB0'
GPS_ROVER_PORT = '/dev/ttyUSB1'
BAUDRATE = 4800

base_data = {'lat': 0.0, 'lon': 0.0, 'hdop': 99.9}
rover_data = {'lat': 0.0, 'lon': 0.0, 'hdop': 99.9}
heading = 0.0
error = 0.0
imu_used = False

imu_angle = 0.0

# --- IMU 初期化 ---
if IMU_AVAILABLE:
    imu = mpu6050(0x68)

def read_imu():
    global imu_angle, imu_used
    while True:
        try:
            accel = imu.get_accel_data()
            gyro = imu.get_gyro_data()
            imu_angle = gyro['z']  # 仮に z軸の角速度から推定（適当）
            imu_used = True
        except:
            imu_used = False
        time.sleep(0.5)

# --- GPS読み取り ---
def read_gps(port, target):
    try:
        ser = serial.Serial(port, BAUDRATE, timeout=1)
    except:
        print(f"GPSポート {port} が開けません")
        return

    while True:
        try:
            line = ser.readline().decode('ascii', errors='ignore')
            if line.startswith('$GPGGA'):
                msg = pynmea2.parse(line)
                target['lat'] = msg.latitude
                target['lon'] = msg.longitude
                target['hdop'] = float(msg.horizontal_dil)
        except:
            continue

# --- ヘディングと誤差の計算 ---
def calculate_heading_and_error():
    global heading, error
    while True:
        lat1, lon1 = base_data['lat'], base_data['lon']
        lat2, lon2 = rover_data['lat'], rover_data['lon']

        dLat = math.radians(lat2 - lat1)
        dLon = math.radians(lon2 - lon1)
        y = math.sin(dLon) * math.cos(math.radians(lat2))
        x = math.cos(math.radians(lat1)) * math.sin(math.radians(lat2)) - \
            math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(dLon)
        heading = (math.degrees(math.atan2(y, x)) + 360) % 360

        # 誤差（Haversine距離）
        R = 6371000
        a = math.sin(dLat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dLon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        error = R * c

        time.sleep(1)

# --- スレッド起動 ---
threading.Thread(target=read_gps, args=(GPS_BASE_PORT, base_data), daemon=True).start()
threading.Thread(target=read_gps, args=(GPS_ROVER_PORT, rover_data), daemon=True).start()
threading.Thread(target=calculate_heading_and_error, daemon=True).start()
if IMU_AVAILABLE:
    threading.Thread(target=read_imu, daemon=True).start()

# --- APIエンドポイント ---
@app.route("/api/position")
def api_position():
    angle = heading
    if imu_used:
        angle = (heading + imu_angle) % 360  # IMU補間（仮）
    return jsonify({
        'lat': base_data['lat'],
        'lon': base_data['lon'],
        'heading': angle,
        'error': error,
        'imu': imu_used,
        'hdop_base': base_data['hdop'],
        'hdop_rover': rover_data['hdop']
    })

# --- index.htmlを返す ---
@app.route("/")
def index():
    return render_template("index.html")

# --- アプリ起動 ---
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")

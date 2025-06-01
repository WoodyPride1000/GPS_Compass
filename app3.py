from flask import Flask, jsonify, render_template
import serial
import pynmea2
import math
import threading
import time
import random
import os # シリアルポートの存在確認用

# --- 設定 ---
# ダミーモードのフラグ
# True にすると実デバイスの代わりにダミーデータを生成します。
# 開発・デバッグ時は True に設定することを推奨します。
DUMMY_MODE = False # 実機運用時は False に設定してください

# IMUライブラリのインポート（利用可能であれば）
IMU_AVAILABLE = False # デフォルトでFalseに初期化
try:
    from mpu6050 import mpu6050
    IMU_AVAILABLE = True
except ImportError:
    print("警告: mpu6050ライブラリが見つかりませんでした。IMUは無効になります。")

app = Flask(__name__)

GPS_BASE_PORT = '/dev/ttyUSB0'
GPS_ROVER_PORT = '/dev/ttyUSB1'
BAUDRATE = 9600 # このコードでは9600に変わっているので注意

# データを保持するクラス
class SensorData:
    def __init__(self):
        self.base_data = {'lat': 0.0, 'lon': 0.0, 'hdop': 99.9}
        self.rover_data = {'lat': 0.0, 'lon': 0.0, 'hdop': 99.9}
        self.heading_gps = 0.0
        self.error = 0.0
        self.imu_status = False # IMUが利用可能かどうか
        self.imu_raw_gyro_z = 0.0 # IMUの生のZ軸ジャイロデータ（角速度）
        self.lock = threading.Lock()

sensor_data = SensorData()

# --- IMU 初期化と読み取りスレッド ---
# IMU_AVAILABLE と DUMMY_MODE がここで定義済みであることを確認
if IMU_AVAILABLE and not DUMMY_MODE:
    try:
        imu_device = mpu6050(0x68) # IMUデバイスをグローバルに持たせる
        with sensor_data.lock:
            sensor_data.imu_status = True
        print("IMUが正常に初期化されました。")
    except Exception as e:
        print(f"IMU初期化エラー: {e}。IMUは無効になります。")
        IMU_AVAILABLE = False # 初期化失敗時はIMUを無効化

def read_imu_thread():
    # このスレッド内でのみ imu_device にアクセス
    while True:
        if DUMMY_MODE:
            # ダミーのIMUデータ生成
            with sensor_data.lock:
                sensor_data.imu_raw_gyro_z = random.uniform(-5.0, 5.0)
                sensor_data.imu_status = True
            time.sleep(0.1)
        else:
            if not IMU_AVAILABLE: # 初期化に失敗した場合はスキップ
                time.sleep(1)
                continue
            try:
                # accel = imu_device.get_accel_data()
                gyro = imu_device.get_gyro_data()
                with sensor_data.lock:
                    sensor_data.imu_raw_gyro_z = gyro['z']
                    sensor_data.imu_status = True
            except Exception as e:
                with sensor_data.lock:
                    sensor_data.imu_status = False
                print(f"IMU読み取りエラー: {e}")
            time.sleep(0.05)

# --- GPS読み取りスレッド ---
def read_gps_thread(port, target_key):
    if DUMMY_MODE:
        while True:
            # ダミーのGPSデータ生成
            with sensor_data.lock:
                if target_key == 'base':
                    sensor_data.base_data['lat'] = random.uniform(35.680, 35.682)
                    sensor_data.base_data['lon'] = random.uniform(139.765, 139.768)
                    sensor_data.base_data['hdop'] = random.uniform(0.8, 1.5)
                else:
                    # ローバーはベースから少しずれた位置をシミュレート
                    sensor_data.rover_data['lat'] = sensor_data.base_data['lat'] + random.uniform(-0.0001, 0.0001)
                    sensor_data.rover_data['lon'] = sensor_data.base_data['lon'] + random.uniform(-0.0001, 0.0001)
                    sensor_data.rover_data['hdop'] = random.uniform(0.8, 1.5)
            time.sleep(random.uniform(0.5, 1.5))
    else:
        # シリアルポートの存在を確認
        if not os.path.exists(port):
            print(f"エラー: GPSポート {port} が見つかりません。")
            return

        try:
            ser = serial.Serial(port, BAUDRATE, timeout=1)
            print(f"GPSポート {port} が正常に開かれました。")
        except serial.SerialException as e:
            print(f"エラー: GPSポート {port} を開けません - {e}")
            return

        while True:
            try:
                line = ser.readline().decode('ascii', errors='ignore').strip()
                if line.startswith("$GPGGA"):
                    msg = pynmea2.parse(line)
                    with sensor_data.lock:
                        if target_key == 'base':
                            sensor_data.base_data['lat'] = msg.latitude
                            sensor_data.base_data['lon'] = msg.longitude
                            sensor_data.base_data['hdop'] = float(msg.horizontal_dil)
                        else:
                            sensor_data.rover_data['lat'] = msg.latitude
                            sensor_data.rover_data['lon'] = msg.longitude
                            sensor_data.rover_data['hdop'] = float(msg.horizontal_dil)
            except pynmea2.ParseError as e:
                continue
            except UnicodeDecodeError:
                continue
            except serial.SerialException as e:
                print(f"GPSポート {port} でシリアル通信エラー: {e}")
                break
            except Exception as e:
                print(f"GPSポート {port} で予期せぬエラー: {e}")
                time.sleep(1)

# --- ヘディングと誤差の計算スレッド ---
def calculate_heading_and_error_thread():
    while True:
        with sensor_data.lock:
            lat1, lon1 = sensor_data.base_data['lat'], sensor_data.base_data['lon']
            lat2, lon2 = sensor_data.rover_data['lat'], sensor_data.rover_data['lon']

        if lat1 == 0.0 or lon1 == 0.0 or lat2 == 0.0 or lon2 == 0.0:
            time.sleep(1)
            continue

        # 正確な測地系計算 (Haversine for distance, bearing for heading)
        R = 6371000 # 地球の平均半径 (メートル)
        phi1 = math.radians(lat1)
        lambda1 = math.radians(lon1)
        phi2 = math.radians(lat2)
        lambda2 = math.radians(lon2)

        d_phi = phi2 - phi1
        d_lambda = lambda2 - lambda1

        # Distance (Haversine formula)
        a = math.sin(d_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        calculated_distance = R * c

        # Heading (bearing)
        y = math.sin(d_lambda) * math.cos(phi2)
        x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(d_lambda)
        calculated_heading = (math.degrees(math.atan2(y, x)) + 360) % 360

        # error: 基線長に対する誤差（具体的な定義に応じて調整）
        # 例: 既知の基線長が 0.7m であれば
        calculated_error = abs(calculated_distance - 0.7) # 仮の定義

        with sensor_data.lock:
            sensor_data.heading_gps = calculated_heading
            sensor_data.error = calculated_error

        time.sleep(0.5)

# --- スレッド起動 ---
# 各スレッドは自身のシリアルポートを管理し、共有データはロックで保護
threading.Thread(target=read_gps_thread, args=(GPS_BASE_PORT, 'base'), daemon=True).start()
threading.Thread(target=read_gps_thread, args=(GPS_ROVER_PORT, 'rover'), daemon=True).start()
threading.Thread(target=calculate_heading_and_error_thread, daemon=True).start()
if IMU_AVAILABLE: # IMUが利用可能かつ初期化に成功した場合のみスレッドを起動
    threading.Thread(target=read_imu_thread, daemon=True).start()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/position")
def api_position():
    with sensor_data.lock: # データを読み取る際にもロックをかける
        lat = sensor_data.base_data['lat']
        lon = sensor_data.base_data['lon']
        heading_gps = sensor_data.heading_gps
        imu_status = sensor_data.imu_status
        imu_raw_gyro_z = sensor_data.imu_raw_gyro_z # IMUの生データ
        error_val = sensor_data.error
        hdop_base_val = sensor_data.base_data['hdop']
        hdop_rover_val = sensor_data.rover_data['hdop']
        distance_val = sensor_data.error # 仮にerrorに距離も入っていると想定。別途distance変数を用意しても良い

        # ここでIMUとGPSのヘディングを融合するロジックを実装
        # index.html は 'heading' を期待
        # 現状、imu_raw_gyro_zは角速度なので、単純に融合することはできません。
        # 実際のプロジェクトでは、IMUから安定したヨー角（MadgwickFilterなど）を取得し、
        # それとGPSヘディングを何らかのフィルタ（例：カルマンフィルター）で融合します。
        # ここでは暫定的にGPSヘディングを使用します。
        fused_heading = heading_gps 
        
    return jsonify({
        "lat": lat,
        "lon": lon,
        "heading": fused_heading % 360, # index.htmlが期待するフィールド名
        "distance": distance_val, # 新しくdistanceを返す
        "error": error_val,
        "imu": imu_status, # index.html は 'imu' を期待
        "imu_raw_gyro_z": imu_raw_gyro_z, # デバッグ用にIMU生データも返す
        "hdop_base": hdop_base_val,
        "hdop_rover": hdop_rover_val
    })

if __name__ == "__main__":
    # シリアルポートの競合を避けるため、デバッグモードでの自動リロードを無効にすることを推奨
    app.run(debug=True, use_reloader=False, host="0.0.0.0")

from flask import Flask, jsonify, render_template
import serial
import pynmea2
import math
import threading
import time
import random
import os # シリアルポートの存在確認用

# IMUライブラリのインポート（利用可能であれば）
IMU_AVAILABLE = False
try:
    from mpu6050 import mpu6050
    IMU_AVAILABLE = True
except ImportError:
    print("警告: mpu6050ライブラリが見つかりませんでした。IMUは無効になります。")

app = Flask(__name__)

# --- 設定 ---
# ダミーモードのフラグ
# True にすると実デバイスの代わりにダミーデータを生成します。
# 開発・デバッグ時は True に設定することを推奨します。
DUMMY_MODE = True

GPS_BASE_PORT = '/dev/ttyUSB0'
GPS_ROVER_PORT = '/dev/ttyUSB1'
BAUDRATE = 4800

# データを保持するクラス
class SensorData:
    def __init__(self):
        self.base_data = {'lat': 0.0, 'lon': 0.0, 'hdop': 99.9}
        self.rover_data = {'lat': 0.0, 'lon': 0.0, 'hdop': 99.9}
        self.heading_gps = 0.0 # GPSのみから計算されたヘディング
        self.error = 0.0
        self.imu_status = False # IMUが利用可能かどうか
        self.imu_raw_gyro_z = 0.0 # IMUの生のZ軸ジャイロデータ（角速度）
        self.lock = threading.Lock() # スレッドセーフティのためのロック

sensor_data = SensorData() # データのシングルトンインスタンス

# --- IMU 初期化と読み取り ---
if IMU_AVAILABLE and not DUMMY_MODE:
    try:
        imu = mpu6050(0x68)
        # IMUが初期化できたことを確認
        with sensor_data.lock:
            sensor_data.imu_status = True
        print("IMUが正常に初期化されました。")
    except Exception as e:
        print(f"IMU初期化エラー: {e}。IMUは無効になります。")
        IMU_AVAILABLE = False # 初期化失敗時はIMUを無効化

def read_imu():
    while True:
        if DUMMY_MODE:
            # ダミーのIMUデータ生成
            with sensor_data.lock:
                # 実際のIMUデータ（例：ヨー角の安定した推定値）を模倣
                # 現実にはフィルタリングされた姿勢データが必要
                sensor_data.imu_raw_gyro_z = random.uniform(-5.0, 5.0) # ダミーのZ軸角速度
                sensor_data.imu_status = True
            time.sleep(0.1) # IMUはより高速に更新されることが多い
        else:
            if not IMU_AVAILABLE: # 初期化に失敗した場合はスキップ
                time.sleep(1)
                continue
            try:
                # accel = imu.get_accel_data() # 加速度データも取得できる
                gyro = imu.get_gyro_data()
                with sensor_data.lock:
                    sensor_data.imu_raw_gyro_z = gyro['z']
                    sensor_data.imu_status = True
            except Exception as e:
                with sensor_data.lock:
                    sensor_data.imu_status = False
                print(f"IMU読み取りエラー: {e}")
            time.sleep(0.05) # 20Hz更新を想定

# --- GPS読み取り ---
def read_gps(port, target_key): # 'base'または'rover'を文字列で受け取る
    if DUMMY_MODE:
        while True:
            # ダミーのGPSデータ生成
            with sensor_data.lock:
                if target_key == 'base':
                    sensor_data.base_data['lat'] = random.uniform(35.680, 35.682)
                    sensor_data.base_data['lon'] = random.uniform(139.765, 139.768)
                    sensor_data.base_data['hdop'] = random.uniform(0.8, 1.5)
                else: # rover
                    # ローバーはベースから少しずれた位置をシミュレート
                    sensor_data.rover_data['lat'] = sensor_data.base_data['lat'] + random.uniform(-0.0001, 0.0001)
                    sensor_data.rover_data['lon'] = sensor_data.base_data['lon'] + random.uniform(-0.0001, 0.0001)
                    sensor_data.rover_data['hdop'] = random.uniform(0.8, 1.5)
            time.sleep(random.uniform(0.5, 1.5)) # GPSは1Hz更新を想定
    else:
        # シリアルポートの存在を確認
        if not os.path.exists(port):
            print(f"エラー: GPSポート {port} が見つかりません。")
            return # スレッドを終了させる

        try:
            ser = serial.Serial(port, BAUDRATE, timeout=1)
            print(f"GPSポート {port} が正常に開かれました。")
        except serial.SerialException as e:
            print(f"エラー: GPSポート {port} を開けません - {e}")
            return # スレッドを終了させる

        while True:
            try:
                line = ser.readline().decode('ascii', errors='ignore').strip()
                if line.startswith('$GPGGA'):
                    msg = pynmea2.parse(line)
                    with sensor_data.lock:
                        if target_key == 'base':
                            sensor_data.base_data['lat'] = msg.latitude
                            sensor_data.base_data['lon'] = msg.longitude
                            sensor_data.base_data['hdop'] = float(msg.horizontal_dil)
                        else: # rover
                            sensor_data.rover_data['lat'] = msg.latitude
                            sensor_data.rover_data['lon'] = msg.longitude
                            sensor_data.rover_data['hdop'] = float(msg.horizontal_dil)
            except pynmea2.ParseError as e:
                # print(f"警告: NMEA解析エラー ({port}): {e} - '{line}'")
                continue # 解析できない行はスキップ
            except UnicodeDecodeError:
                # print(f"警告: 無効な文字エンコーディング ({port})")
                continue
            except serial.SerialException as e:
                print(f"GPSポート {port} でシリアル通信エラー: {e}")
                break # エラーが発生したらスレッドを終了させる（再起動が必要になる可能性）
            except Exception as e:
                print(f"GPSポート {port} で予期せぬエラー: {e}")
                time.sleep(1)

# --- ヘディングと誤差の計算 ---
def calculate_heading_and_error():
    while True:
        with sensor_data.lock:
            lat1, lon1 = sensor_data.base_data['lat'], sensor_data.base_data['lon']
            lat2, lon2 = sensor_data.rover_data['lat'], sensor_data.rover_data['lon']

        # 緯度・経度が初期値（0.0）の場合は計算をスキップ
        if lat1 == 0.0 or lon1 == 0.0 or lat2 == 0.0 or lon2 == 0.0:
            time.sleep(1)
            continue

        dLat = math.radians(lat2 - lat1)
        dLon = math.radians(lon2 - lon1)

        y = math.sin(dLon) * math.cos(math.radians(lat2))
        x = math.cos(math.radians(lat1)) * math.sin(math.radians(lat2)) - \
            math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(dLon)
        
        # ヘディングはベースからローバーへの方向
        calculated_heading = (math.degrees(math.atan2(y, x)) + 360) % 360

        # 誤差（Haversine距離）
        R = 6371000 # 地球の平均半径 (メートル)
        a = math.sin(dLat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dLon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        calculated_error = R * c

        with sensor_data.lock:
            sensor_data.heading_gps = calculated_heading
            sensor_data.error = calculated_error

        time.sleep(0.5) # GPSデータ更新に合わせて計算頻度を調整

# --- スレッド起動 ---
threading.Thread(target=read_gps, args=(GPS_BASE_PORT, 'base'), daemon=True).start()
threading.Thread(target=read_gps, args=(GPS_ROVER_PORT, 'rover'), daemon=True).start()
threading.Thread(target=calculate_heading_and_error, daemon=True).start()
if IMU_AVAILABLE: # IMUが利用可能かつ初期化に成功した場合のみスレッドを起動
    threading.Thread(target=read_imu, daemon=True).start()

# --- APIエンドポイント ---
@app.route("/api/position")
def api_position():
    with sensor_data.lock: # データを読み取る際にもロックをかける
        lat = sensor_data.base_data['lat']
        lon = sensor_data.base_data['lon']
        heading_gps = sensor_data.heading_gps
        imu_status = sensor_data.imu_status
        imu_raw_gyro_z = sensor_data.imu_raw_gyro_z
        error_val = sensor_data.error
        hdop_base_val = sensor_data.base_data['hdop']
        hdop_rover_val = sensor_data.rover_data['hdop']

        # ヘディングの融合ロジック（例: GPSヘディングを優先し、IMUは補足情報として含める）
        # 注意: imu_raw_gyro_z は角速度であり、直接ヘディングに足すのは不適切です。
        #       実際のアプリケーションでは、IMUからの安定した姿勢（ヨー角）や
        #       GPSとIMUを組み合わせたセンサーフュージョンアルゴリズムが必要です。
        #       ここでは例としてGPSヘディングをそのまま返し、IMU情報は別途提供します。
        combined_heading = heading_gps 
        
        # もしIMUから安定した絶対ヨー角が得られる場合、例えば以下のように使用
        # if imu_status and imu_stable_yaw_available: # IMUが安定したヨー角を提供できる場合
        #     combined_heading = imu_stable_yaw_angle 
        # else:
        #     combined_heading = heading_gps

    return jsonify({
        'lat': lat,
        'lon': lon,
        'heading': combined_heading, # index.htmlが期待する 'heading' フィールド
        'error': error_val,
        'imu_status': imu_status,
        'imu_raw_gyro_z': imu_raw_gyro_z, # IMUの生データも返す
        'hdop_base': hdop_base_val,
        'hdop_rover': hdop_rover_val
    })

# --- index.htmlを返す ---
@app.route("/")
def index():
    return render_template("index.html")

# --- アプリ起動 ---
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")

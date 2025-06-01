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

# --- 定数設定 ---
GPS_BASE_PORT = '/dev/ttyUSB0'
GPS_ROVER_PORT = '/dev/ttyUSB1'
BAUDRATE = 4800
BASELINE_LENGTH_METER = 0.7 # 基線長 (メートル)

# データを保持するクラス
class SensorData:
    def __init__(self):
        self.base_data = {'lat': 0.0, 'lon': 0.0, 'hdop': 99.9}
        self.rover_data = {'lat': 0.0, 'lon': 0.0, 'hdop': 99.9}
        self.heading_gps = 0.0
        self.error = 0.0 # 基線誤差 (メートル)
        self.distance = 0.0 # ベースとローバー間の距離 (メートル)
        self.imu_status = False # IMUが利用可能かどうか
        self.imu_raw_gyro_z = 0.0 # IMUの生のZ軸ジャイロデータ（角速度）
        self.lock = threading.Lock() # スレッドセーフのためのロック

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
    """
    IMUセンサーからデータを読み取り、共有データに格納するスレッド関数。
    DUMMY_MODEがTrueの場合はダミーデータを生成。
    """
    # このスレッド内でのみ imu_device にアクセス
    while True:
        if DUMMY_MODE:
            # ダミーのIMUデータ生成
            with sensor_data.lock:
                # 実際のIMUデータ（角速度deg/s）の範囲を考慮してダミー値を設定
                sensor_data.imu_raw_gyro_z = random.uniform(-10.0, 10.0)
                sensor_data.imu_status = True # ダミーモードではIMUは常に利用可能
            time.sleep(0.05) # IMUは高速
        else:
            if not IMU_AVAILABLE: # 初期化に失敗した場合はスキップ
                time.sleep(1) # 再試行間隔を短くすることも検討
                continue
            try:
                # accel = imu_device.get_accel_data() # 必要に応じて加速度データも取得
                gyro = imu_device.get_gyro_data()
                with sensor_data.lock:
                    sensor_data.imu_raw_gyro_z = gyro['z']
                    sensor_data.imu_status = True
            except Exception as e:
                with sensor_data.lock:
                    sensor_data.imu_status = False # エラー時はIMUを無効とマーク
                print(f"IMU読み取りエラー: {e}")
                time.sleep(1) # エラー時は少し待機して再試行
            time.sleep(0.05)

# --- GPS読み取りスレッド ---
def read_gps_thread(port: str, target_key: str):
    """
    指定されたシリアルポートからGPSデータを読み取り、共有データに格納するスレッド関数。
    :param port: シリアルポートのパス (例: '/dev/ttyUSB0')
    :param target_key: 'base' または 'rover'
    """
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
        while True: # シリアルポートの再接続ロジックを導入
            if not os.path.exists(port):
                print(f"エラー: GPSポート {port} が見つかりません。5秒後に再試行します。")
                time.sleep(5)
                continue

            try:
                ser = serial.Serial(port, BAUDRATE, timeout=1)
                print(f"GPSポート {port} が正常に開かれました。")
            except serial.SerialException as e:
                print(f"エラー: GPSポート {port} を開けません - {e}。5秒後に再試行します。")
                time.sleep(5)
                continue

            try:
                while True:
                    line = ser.readline().decode('ascii', errors='ignore').strip()
                    if line.startswith("$GPGGA"):
                        try:
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
                            # print(f"GPSポート {port} でNMEA解析エラー: {e}") # デバッグ時のみ有効化
                            continue # 不正なNMEAメッセージはスキップ
                    time.sleep(0.01) # 短いスリープでCPU負荷を軽減
            except UnicodeDecodeError:
                # print(f"GPSポート {port} でUnicodeDecodeError") # デバッグ時のみ有効化
                continue
            except serial.SerialException as e:
                print(f"GPSポート {port} でシリアル通信エラー: {e}。再接続を試みます。")
                ser.close() # 既存のシリアルポートを閉じる
                time.sleep(2) # 再接続前に少し待機
                # ループの先頭に戻り、再接続を試みる
            except Exception as e:
                print(f"GPSポート {port} で予期せぬエラー: {e}。再接続を試みます。")
                if 'ser' in locals() and ser.is_open:
                    ser.close()
                time.sleep(2)

# --- ヘディングと誤差の計算スレッド ---
def calculate_heading_and_error_thread():
    """
    ベースとローバーのGPSデータから、ヘディング（方位角）と基線長誤差を計算するスレッド関数。
    """
    while True:
        with sensor_data.lock:
            lat1, lon1 = sensor_data.base_data['lat'], sensor_data.base_data['lon']
            lat2, lon2 = sensor_data.rover_data['lat'], sensor_data.rover_data['lon']

        # GPSデータが有効でない場合は計算をスキップ
        # ある程度誤差が少ない場合のみ計算
        if lat1 == 0.0 or lon1 == 0.0 or lat2 == 0.0 or lon2 == 0.0: # or sensor_data.base_data['hdop'] > 5.0 or sensor_data.rover_data['hdop'] > 5.0:
            time.sleep(1) # データが来るまで待機
            continue

        # 正確な測地系計算 (Haversine for distance, bearing for heading)
        R_earth = 6371000 # 地球の平均半径 (メートル)
        
        phi1 = math.radians(lat1)
        lambda1 = math.radians(lon1)
        phi2 = math.radians(lat2)
        lambda2 = math.radians(lon2)

        d_phi = phi2 - phi1
        d_lambda = lambda2 - lambda1

        # Distance (Haversine formula)
        a = math.sin(d_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        calculated_distance = R_earth * c

        # Heading (bearing)
        y = math.sin(d_lambda) * math.cos(phi2)
        x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(d_lambda)
        calculated_heading = (math.degrees(math.atan2(y, x)) + 360) % 360

        # error: 基線長に対する誤差（既知の基線長との差）
        calculated_error = abs(calculated_distance - BASELINE_LENGTH_METER)

        with sensor_data.lock:
            sensor_data.heading_gps = calculated_heading
            sensor_data.error = calculated_error
            sensor_data.distance = calculated_distance # 計算した距離を保存

        time.sleep(0.5)

# --- スレッド起動 ---
# 各スレッドは自身のシリアルポートを管理し、共有データはロックで保護
threading.Thread(target=read_gps_thread, args=(GPS_BASE_PORT, 'base'), daemon=True).start()
threading.Thread(target=read_gps_thread, args=(GPS_ROVER_PORT, 'rover'), daemon=True).start()
threading.Thread(target=calculate_heading_and_error_thread, daemon=True).start()
if IMU_AVAILABLE: # IMUが利用可能かつ初期化に成功した場合のみスレッドを起動
    threading.Thread(target=read_imu_thread, daemon=True).start()

# --- Flask Webアプリケーション ---
@app.route("/")
def index():
    """
    メインページを表示するルート。
    """
    return render_template("index.html")

@app.route("/api/position")
def api_position():
    """
    センサーデータをJSON形式で返すAPIエンドポイント。
    """
    with sensor_data.lock: # データを読み取る際にもロックをかける
        lat = sensor_data.base_data['lat']
        lon = sensor_data.base_data['lon']
        heading_gps = sensor_data.heading_gps
        imu_status = sensor_data.imu_status
        imu_raw_gyro_z = sensor_data.imu_gyro_z # IMUの生データ
        error_val = sensor_data.error
        distance_val = sensor_data.distance # 新しくdistanceを返す
        hdop_base_val = sensor_data.base_data['hdop']
        hdop_rover_val = sensor_data.rover_data['hdop']

        # Python側での融合ロジックの例（ここでは単純にGPSヘディングを返す）
        # より複雑な融合はJavaScript側で行う、またはここに実装し、結果を返す
        fused_heading = heading_gps # 融合ロジックをここに記述

    return jsonify({
        "lat": lat,
        "lon": lon,
        "heading": fused_heading % 360, # 0-360度の範囲に正規化
        "distance": distance_val,
        "error": error_val,
        "imu": imu_status,
        "imu_raw_gyro_z": imu_raw_gyro_z, # デバッグ用にIMU生データも返す
        "hdop_base": hdop_base_val,
        "hdop_rover": hdop_rover_val
    })

if __name__ == "__main__":
    # シリアルポートの競合を避けるため、デバッグモードでの自動リロードを無効にすることを推奨
    app.run(debug=True, use_reloader=False, host="0.0.0.0")

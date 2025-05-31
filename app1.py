from flask import Flask, render_template, jsonify
import threading
import math
import serial
import pynmea2
import time

app = Flask(__name__)

latest_base = (35.681236, 139.767125)  # 初期値
latest_rover = (35.681800, 139.768000)

def get_gps_position(device):
    try:
        with serial.Serial(device, baudrate=9600, timeout=1) as ser:
            for _ in range(10):  # 最大10行まで読み取りを試みる
                line = ser.readline().decode('ascii', errors='ignore').strip()
                if line.startswith('$GPGGA') or line.startswith('$GPRMC'):
                    try:
                        msg = pynmea2.parse(line)
                        if hasattr(msg, 'latitude') and hasattr(msg, 'longitude'):
                            return (msg.latitude, msg.longitude)
                    except pynmea2.ParseError:
                        continue
    except serial.SerialException:
        pass
    return None

def gps_reader():
    global latest_base, latest_rover
    while True:
        b = get_gps_position('/dev/ttyUSB0')
        r = get_gps_position('/dev/ttyUSB1')
        if b:
            latest_base = b
        if r:
            latest_rover = r
        time.sleep(0.5)

def calculate_heading_and_error(base, rover):
    lat1, lon1 = base
    lat2, lon2 = rover
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    heading = math.degrees(math.atan2(dlon, dlat)) % 360
    distance = math.sqrt(dlat**2 + dlon**2) * 111000  # meters
    error = abs(distance - 0.7)
    return heading, distance, error

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/position")
def api_position():
    heading, dist, error = calculate_heading_and_error(latest_base, latest_rover)
    return jsonify({
        "base": {"lat": latest_base[0], "lon": latest_base[1]},
        "rover": {"lat": latest_rover[0], "lon": latest_rover[1]},
        "heading": heading,
        "distance": dist,
        "error": error
    })




if __name__ == "__main__":
    threading.Thread(target=gps_reader, daemon=True).start()
    app.run(debug=True, host="0.0.0.0", threaded=True)

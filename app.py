from flask import Flask, render_template, jsonify
import math

app = Flask(__name__)

def get_gps_position(device):
    # 仮の値（実装では /dev/ttyUSBx を読む）
    if device == "/dev/ttyUSB0":
        return (35.681236, 139.767125)
    elif device == "/dev/ttyUSB1":
        return (35.681800, 139.768000)
    return None

def calculate_heading_and_error(base, rover):
    lat1, lon1 = base
    lat2, lon2 = rover
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    heading = math.degrees(math.atan2(dlon, dlat)) % 360
    distance = math.sqrt(dlat**2 + dlon**2) * 111000  # meters
    error = abs(distance - 0.7)  # 70cmが理想
    return heading, distance, error

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/position")
def api_position():
    base = get_gps_position("/dev/ttyUSB0")
    rover = get_gps_position("/dev/ttyUSB1")
    if base is None or rover is None:
        base = (35.681236, 139.767125)
        rover = (35.681800, 139.768000)

    heading, dist, error = calculate_heading_and_error(base, rover)
    return jsonify({
        "lat": base[0],
        "lon": base[1],
        "heading": heading,
        "distance": dist,
        "error": error
    })

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")

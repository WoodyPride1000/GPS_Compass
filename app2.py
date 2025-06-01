from flask import Flask, render_template, jsonify
import math
import serial
import pynmea2
import mgrs
import utm

app = Flask(__name__)
m = mgrs.MGRS()

def get_gps_position_with_hdop(device):
    try:
        with serial.Serial(device, baudrate=9600, timeout=1) as ser:
            for _ in range(30):
                line = ser.readline().decode("ascii", errors="ignore").strip()
                if line.startswith("$GPGGA"):
                    try:
                        msg = pynmea2.parse(line)
                        if msg.latitude and msg.longitude:
                            hdop = float(msg.horizontal_dil)
                            return msg.latitude, msg.longitude, hdop
                    except:
                        continue
    except:
        pass
    return 35.681236, 139.767125, 0.9  # fallback

def calculate_heading_and_error(base, rover):
    lat1, lon1 = base
    lat2, lon2 = rover
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    heading = math.degrees(math.atan2(dlon, dlat)) % 360
    distance = math.sqrt(dlat**2 + dlon**2) * 111000
    error = abs(distance - 0.7)
    return heading, distance, error

imu_available = False
imu_heading = 0.0

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/position")
def api_position():
    base_lat, base_lon, base_hdop = get_gps_position_with_hdop("/dev/ttyUSB0")
    rover_lat, rover_lon, rover_hdop = get_gps_position_with_hdop("/dev/ttyUSB1")

    gps_heading, dist, error = calculate_heading_and_error((base_lat, base_lon), (rover_lat, rover_lon))

    if imu_available:
        alpha = 0.8
        fused_heading = alpha * gps_heading + (1 - alpha) * imu_heading
    else:
        fused_heading = gps_heading

    mgrs_str = m.toMGRS(base_lat, base_lon)
    utm_e, utm_n, utm_zone, utm_letter = utm.from_latlon(base_lat, base_lon)
    utm_str = f"{utm_zone}{utm_letter} {utm_e:.2f}E {utm_n:.2f}N"

    return jsonify({
        "lat": base_lat,
        "lon": base_lon,
        "mgrs": mgrs_str,
        "utm": utm_str,
        "heading": fused_heading % 360,
        "distance": dist,
        "error": error,
        "imu": imu_available,
        "hdop_base": base_hdop,
        "hdop_rover": rover_hdop
    })

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")

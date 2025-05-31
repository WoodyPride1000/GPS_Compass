from flask import Flask, render_template_string
from gps_reader import get_gps_position
from heading_calc import calculate_heading_and_error, latlon_to_utm
import folium

app = Flask(__name__)

@app.route('/')
@app.route('/')
def index():
    base = get_gps_position('/dev/ttyUSB0')
    rover = get_gps_position('/dev/ttyUSB1')

    if base is None:
        print("Base GPS not available. Using fallback coordinates.")
        base = (35.681236, 139.767125)
    if rover is None:
        print("Rover GPS not available. Using fallback coordinates.")
        rover = (35.681800, 139.768000)

    heading, measured_distance, error = calculate_heading_and_error(base, rover)
    lat, lon = base
    utm_x, utm_y = latlon_to_utm(lat, lon)

    # 方位角に従って短い矢印線を描画（地球座標上で小さなオフセットを与える）
    import math
    arrow_length = 0.0003  # 緯度・経度で約30m（見た目10%ほど）
    heading_rad = math.radians(heading)
    lat2 = lat + arrow_length * math.cos(heading_rad)
    lon2 = lon + arrow_length * math.sin(heading_rad)

    fmap = folium.Map(location=[lat, lon], zoom_start=18)
    
    # 自己位置マーカー
    folium.Marker(
        [lat, lon],
        tooltip="Base Station",
        popup=f"""
        <b>Lat/Lon:</b> {lat:.6f}, {lon:.6f}<br>
        <b>UTM:</b> {utm_x}, {utm_y}<br>
        <b>Heading:</b> {heading:.2f}°<br>
        <b>Error:</b> {error:.2f} m
        """
    ).add_to(fmap)

    # 方位角矢印（固定長）
    folium.PolyLine(
        locations=[(lat, lon), (lat2, lon2)],
        color='red',
        weight=5,
        tooltip=f'Heading: {heading:.2f}°'
    ).add_to(fmap)

    # 画面上に数値表示
    info_html = f"""
    <div style="position:absolute; top:10px; left:10px; background:white; padding:10px; z-index:999;">
        <b>Lat:</b> {lat:.6f}<br>
        <b>Lon:</b> {lon:.6f}<br>
        <b>UTM:</b> {utm_x:.2f}, {utm_y:.2f}<br>
        <b>Heading:</b> {heading:.2f}°<br>
        <b>Error:</b> {error:.2f} m
    </div>
    """

    map_html = fmap._repr_html_()
    return render_template_string(f"""
    <html><head><meta charset="utf-8"><title>GPS Compass</title></head>
    <body>
        {info_html}
        {map_html}
    </body></html>
    """)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

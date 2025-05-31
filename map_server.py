from flask import Flask, render_template_string
import folium
from gps_reader import get_gps_position
from heading_calc import calculate_heading_and_error, latlon_to_utm, latlon_to_mgrs

app = Flask(__name__)

@app.route('/')
def index():
    base = get_gps_position('/dev/ttyUSB0')
    rover = get_gps_position('/dev/ttyUSB1')

    heading, measured_distance, error = calculate_heading_and_error(base, rover)
    lat, lon = base
    utm_x, utm_y = latlon_to_utm(lat, lon)
    mgrs_code = latlon_to_mgrs(lat, lon)

    fmap = folium.Map(location=[lat, lon], zoom_start=18)
    folium.Marker(
        [lat, lon],
        tooltip="Base Station",
        popup=f"""
        <b>Lat/Lon:</b> {lat:.6f}, {lon:.6f}<br>
        <b>UTM:</b> {utm_x}, {utm_y}<br>
        <b>MGRS:</b> {mgrs_code}<br>
        <b>Heading:</b> {heading:.2f}°<br>
        <b>Error:</b> {error:.2f} m
        """
    ).add_to(fmap)

    folium.PolyLine(
        locations=[base, rover],
        color='blue',
        weight=3,
        tooltip=f'Heading: {heading:.2f}°, Distance: {measured_distance:.2f}m'
    ).add_to(fmap)

    html = fmap._repr_html_()
    return render_template_string("""
    <html><head><meta charset="utf-8"><title>GPS Compass</title></head>
    <body>{{{{ map_html|safe }}}}</body></html>
    """, map_html=html)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
from pyproj import Geod, Transformer
import mgrs
import math

WGS84 = Geod(ellps="WGS84")
transformer = Transformer.from_crs("EPSG:4326", "EPSG:32654", always_xy=True)
m = mgrs.MGRS()

def calculate_heading_and_error(base, rover, baseline_length=0.70):
    lon1, lat1 = base[1], base[0]
    lon2, lat2 = rover[1], rover[0]

    azimuth12, _, distance = WGS84.inv(lon1, lat1, lon2, lat2)
    error = abs(distance - baseline_length)
    return azimuth12 % 360, distance, error

def latlon_to_utm(lat, lon):
    x, y = transformer.transform(lon, lat)
    return round(x, 2), round(y, 2)

def latlon_to_mgrs(lat, lon):
    return m.toMGRS(lat, lon)
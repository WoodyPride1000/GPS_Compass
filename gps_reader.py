import serial
import pynmea2

def get_gps_position(port='/dev/ttyUSB0', baudrate=9600):
    ser = serial.Serial(port, baudrate, timeout=1)
    while True:
        try:
            line = ser.readline().decode('ascii', errors='replace')
            if line.startswith('$GPGGA') or line.startswith('$GNGGA'):
                msg = pynmea2.parse(line)
                if msg.latitude != 0.0 and msg.longitude != 0.0:
                    return float(msg.latitude), float(msg.longitude)
        except Exception:
            continue
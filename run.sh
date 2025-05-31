#!/bin/bash
echo "Starting GPS Compass Web Server..."
export FLASK_APP=map_server.py
flask run --host=0.0.0.0 --port=5000

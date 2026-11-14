#pragma once

// Replace these values before flashing. The computer running backend_server.py
// must have a stable LAN IPv4 address reachable from the ESP32-CAM.
#define WIFI_SSID "CHANGE_WIFI_NAME"
#define WIFI_PASSWORD "CHANGE_WIFI_PASSWORD"
#define BACKEND_RESULT_URL "http://192.168.1.10:5000/api/result"

// AI-Thinker ESP32-CAM infrared sensor input. Sensor output is active LOW.
#define IR_SENSOR_GPIO 2

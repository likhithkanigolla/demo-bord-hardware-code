import json
import socket
import subprocess
import time
from datetime import datetime

import requests
import board
import busio
import RPi.GPIO as GPIO

import adafruit_veml7700
import adafruit_si7021
import adafruit_sgp30


# ================= CONFIG =================
API_BASE = "https://smartcitylivinglab.iiit.ac.in/smartcitydigitaltwin-api/demo-board"
NODE_ID = 1

ESP_IP = "10.2.135.210"
ESP_PORT = 8100
ESP_URL = f"http://{ESP_IP}:{ESP_PORT}/data"

SENSOR_INTERVAL_SECONDS = 45
HEARTBEAT_INTERVAL_SECONDS = 15
COMMAND_POLL_SECONDS = 5

ESP_SEND_INTERVAL = 5  # 🔥 send every 4 sec


# ================= GPIO =================
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

PIR_PIN = 4

buttons = {
    12: "Time",
    16: "Sensors",
    20: "Wi-Fi",
    21: "Power",
    6: "Lux",
    13: "Temp",
    19: "CO2"
}

GPIO.setup(PIR_PIN, GPIO.IN)

for pin in buttons:
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

last_state = {pin: 1 for pin in buttons}
last_pressed_time = {pin: 0 for pin in buttons}
DEBOUNCE_TIME = 0.2

sensor_enabled = {
    "Lux": True,
    "Temp": True,
    "CO2": True
}


# ================= I2C =================
i2c = busio.I2C(board.SCL, board.SDA)

veml = adafruit_veml7700.VEML7700(i2c)
si7021 = adafruit_si7021.SI7021(i2c)

sgp30 = adafruit_sgp30.Adafruit_SGP30(i2c)
sgp30.iaq_init()

print("Waiting for SGP30 stabilization...")
time.sleep(2)

eco2_raw, tvoc_raw = 0, 0


# ================= PIR WINDOW =================
pir_history = []
PIR_WINDOW = 30


def get_pir_majority():
    global pir_history

    now = time.time()
    val = 1 if GPIO.input(PIR_PIN) else 0

    pir_history.append((now, val))
    pir_history = [(t, v) for (t, v) in pir_history if now - t <= PIR_WINDOW]

    ones = sum(v for (_, v) in pir_history)
    zeros = len(pir_history) - ones

    return 1 if ones > zeros else 0


# ================= HELPERS =================
def get_local_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except:
        return "0.0.0.0"


def fmt(val):
    return "NaN" if val is None else round(val, 2)


# ================= ESP =================
esp_queue = []
last_esp_send = 0


def send_esp_command(cmd):
    try:
        payload = {"cmd": cmd}
        r = requests.post(ESP_URL, json=payload, timeout=2)
        print("ESP:", cmd, "|", r.status_code)
    except Exception as e:
        print("ESP Error:", e)


# ================= SENSOR =================
def read_sensors():
    global eco2_raw, tvoc_raw

    try:
        eco2_raw, tvoc_raw = sgp30.iaq_measure()
    except:
        pass

    lux = veml.light if sensor_enabled["Lux"] else None
    temp = si7021.temperature if sensor_enabled["Temp"] else None

    gas = eco2_raw if sensor_enabled["CO2"] else None
    pir = get_pir_majority()

    return {
        "temperature": temp,
        "lux": lux,
        "gas": gas,
        "pir": pir
    }


# ================= BUTTON =================
def handle_buttons():
    now = time.time()

    for pin, name in buttons.items():
        state = GPIO.input(pin)

        if last_state[pin] == 1 and state == 0:
            if now - last_pressed_time[pin] > DEBOUNCE_TIME:

                if name in sensor_enabled:
                    sensor_enabled[name] = not sensor_enabled[name]
                    print(f"{name} {'ENABLED' if sensor_enabled[name] else 'DISABLED'}")

                last_pressed_time[pin] = now

        last_state[pin] = state


# ================= API =================
def post_sensor_data():
    global esp_queue

    readings = read_sensors()

    print("\n===== SENSOR DATA =====")
    for k, v in readings.items():
        print(f"{k}: {fmt(v)}")
    print("=======================\n")

    payload = {
        "node_id": NODE_ID,
        "sensor_type": "environmental",
        "readings": readings,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "metadata": {"source": "raspberry_pi_agent"}
    }

    try:
        r = requests.post(f"{API_BASE}/receive-sensor-data", json=payload, timeout=5)
        print("POST:", r.status_code)
    except Exception as e:
        print("POST Error:", e)

    # -------- ADD TO ESP QUEUE --------
    esp_queue.append([1 if readings["gas"] else 0, 0, 0, 0, 0, 0, [0,0,0], 0])
    esp_queue.append([0, 1 if readings["temperature"] else 0, 0, 0, 0, 0, [0,0,0], 0])
    esp_queue.append([0, 0, 1 if readings["lux"] else 0, 0, 0, 0, [0,0,0], 0])
    esp_queue.append([0, 0, 0, readings["pir"], 0, 0, [0,0,0], 0])


def post_heartbeat():
    payload = {
        "node_id": NODE_ID,
        "ip_address": get_local_ip(),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    try:
        r = requests.post(f"{API_BASE}/node-heartbeat", json=payload, timeout=5)
        print("Heartbeat:", r.status_code)
    except:
        pass


def poll_commands():
    try:
        r = requests.get(f"{API_BASE}/commands/{NODE_ID}?status=pending", timeout=5)
        data = r.json()

        for cmd in data.get("commands", []):
            requests.post(
                f"{API_BASE}/commands/{cmd['id']}/ack",
                json={"status": "executed", "response_message": "OK"},
                timeout=5
            )
            print("ACK:", cmd["id"])
    except:
        pass


# ================= MAIN =================
def main():
    global last_esp_send

    print("Agent started")

    next_sensor = 0
    next_hb = 0
    next_cmd = 0

    while True:
        now = time.time()

        try:
            handle_buttons()

            # SENSOR (30 sec)
            if now >= next_sensor:
                post_sensor_data()
                next_sensor = now + SENSOR_INTERVAL_SECONDS

            # HEARTBEAT
            if now >= next_hb:
                post_heartbeat()
                next_hb = now + HEARTBEAT_INTERVAL_SECONDS

            # COMMAND POLL
            if now >= next_cmd:
                poll_commands()
                next_cmd = now + COMMAND_POLL_SECONDS

            # 🔥 ESP SEND EVERY 2 SEC
            if now - last_esp_send >= ESP_SEND_INTERVAL:
                if len(esp_queue) > 0:
                    cmd = esp_queue.pop(0)
                    send_esp_command(cmd)
                    last_esp_send = now

        except Exception as e:
            print("Error:", e)

        time.sleep(0.1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        GPIO.cleanup()
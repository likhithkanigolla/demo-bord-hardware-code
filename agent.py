import json
import socket
import subprocess
import time
from datetime import datetime
import os
from pathlib import Path
import logging

import requests
from dotenv import load_dotenv
import board
import busio
import RPi.GPIO as GPIO

import adafruit_veml7700
import adafruit_si7021
import adafruit_sgp30


# ================= LOGGING =================
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='[%(asctime)s] [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('/tmp/pi_agent.log'),  # Log to file
        logging.StreamHandler()  # Also print to console
    ]
)
logger = logging.getLogger(__name__)
logger.info(f"Pi Agent started with LOG_LEVEL={log_level}")


# ================= CONFIG =================
CONFIG_FILE = Path(__file__).parent / "config" / "config.env"
if CONFIG_FILE.exists():
    load_dotenv(CONFIG_FILE)

BACKEND_HOST = os.getenv("BACKEND_HOST", "https://smartcitylivinglab.iiit.ac.in/smartcitydigitaltwin-api").rstrip("/")
API_BASE = f"{BACKEND_HOST}/demo-board"
NODE_ID = int(os.getenv("NODE_ID", "1"))

ESP_URL = os.getenv("ESP_URL")
if not ESP_URL:
    ESP_IP = os.getenv("ESP_IP", "10.2.135.210")
    ESP_PORT = int(os.getenv("ESP_PORT", "8100"))
    ESP_URL = f"http://{ESP_IP}:{ESP_PORT}/data"

SENSOR_INTERVAL_SECONDS = 45
HEARTBEAT_INTERVAL_SECONDS = 15
COMMAND_POLL_SECONDS = 5

# Configurable sensor interval (can be updated via API)
SENSOR_INTERVAL_CONFIG = float(os.getenv("SENSOR_INTERVAL_SECONDS", "45"))
last_sensor_config_fetch = 0
CONFIG_FETCH_INTERVAL = 300  # Refresh config every 5 minutes

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

logger.info("Waiting for SGP30 stabilization...")
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


def _normalize_esp_url(target_url):
    if not target_url:
        return ESP_URL
    if target_url.startswith("http://") or target_url.startswith("https://"):
        return target_url
    return f"http://{target_url}"


def send_esp_command(cmd, target_url=None):
    try:
        url = _normalize_esp_url(target_url)
        payload = {"cmd": cmd}
        r = requests.post(url, json=payload, timeout=2)
        logger.debug(f"ESP command {cmd}: {r.status_code}")
        return r.ok, f"HTTP {r.status_code}: {r.text[:200]}"
    except Exception as e:
        logger.error(f"ESP Error: {e}")
        return False, str(e)


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
                    logger.info(f"{name} {'ENABLED' if sensor_enabled[name] else 'DISABLED'}")

                last_pressed_time[pin] = now

        last_state[pin] = state


# ================= API =================
def post_sensor_data():
    global esp_queue

    readings = read_sensors()

    logger.info("\n===== SENSOR DATA =====")
    for k, v in readings.items():
        logger.info(f"{k}: {fmt(v)}")
    logger.info("======================\n")

    payload = {
        "node_id": NODE_ID,
        "sensor_type": "environmental",
        "readings": readings,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "metadata": {"source": "raspberry_pi_agent"}
    }

    try:
        r = requests.post(f"{API_BASE}/receive-sensor-data", json=payload, timeout=5)
        if r.status_code == 200:
            logger.info(f"✓ Sensor data posted successfully: T={fmt(readings['temperature'])}°C, "
                       f"Lux={fmt(readings['lux'])}, Gas={fmt(readings['gas'])}")
        else:
            logger.warning(f"✗ POST failed with status {r.status_code}")
    except Exception as e:
        logger.error(f"✗ POST error: {e}")

    # -------- ADD TO ESP QUEUE --------
    esp_queue.append([1 if readings["gas"] else 0, 0, 0, 0, 0, 0, [0,0,0], 0])
    esp_queue.append([0, 1 if readings["temperature"] else 0, 0, 0, 0, 0, [0,0,0], 0])
    esp_queue.append([0, 0, 1 if readings["lux"] else 0, 0, 0, 0, [0,0,0], 0])
    esp_queue.append([0, 0, 0, readings["pir"], 0, 0, [0,0,0], 0])


def fetch_sensor_config():
    """Fetch configurable sensor interval from backend"""
    global SENSOR_INTERVAL_CONFIG, last_sensor_config_fetch
    
    try:
        r = requests.get(
            f"{API_BASE}/sensor-config/{NODE_ID}",
            timeout=3
        )
        if r.status_code == 200:
            config = r.json()
            new_interval = config.get("sampling_interval_seconds", SENSOR_INTERVAL_CONFIG)
            if new_interval != SENSOR_INTERVAL_CONFIG:
                logger.info(f"✓ Sensor interval updated: {SENSOR_INTERVAL_CONFIG}s → {new_interval}s")
                SENSOR_INTERVAL_CONFIG = new_interval
            last_sensor_config_fetch = time.time()
            return True
    except Exception as e:
        logger.debug(f"Config fetch warning (non-critical): {e}")
    
    return False


def post_heartbeat():
    payload = {
        "node_id": NODE_ID,
        "ip_address": get_local_ip(),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    try:
        r = requests.post(f"{API_BASE}/node-heartbeat", json=payload, timeout=5)
        logger.debug(f"Heartbeat sent: {r.status_code}")
    except Exception as e:
        logger.debug(f"Heartbeat failed (non-critical): {e}")
        pass


def poll_commands():
    try:
        r = requests.get(f"{API_BASE}/commands/{NODE_ID}?status=pending", timeout=5)
        data = r.json()

        for cmd in data.get("commands", []):
            cmd_type = cmd.get("command_type")
            payload = cmd.get("command_payload") or {}
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except Exception:
                    payload = {}

            try:
                payload_preview = json.dumps(payload)[:300]
            except Exception:
                payload_preview = str(payload)[:300]

            logger.info(f"CMD RECEIVED: id={cmd.get('id')} type={cmd_type} payload={payload_preview}")

            status = "executed"
            message = "OK"

            if cmd_type == "ESP_COMMAND":
                cmd_list = payload.get("cmd")
                target_url = payload.get("target_url")
                if not cmd_list:
                    status = "failed"
                    message = "Missing cmd payload"
                else:
                    ok, resp_msg = send_esp_command(cmd_list, target_url)
                    status = "executed" if ok else "failed"
                    message = resp_msg
            else:
                message = f"Skipped unsupported command: {cmd_type}"

            requests.post(
                f"{API_BASE}/commands/{cmd['id']}/ack",
                json={"status": status, "response_message": message},
                timeout=5
            )
            logger.debug(f"ACK: {cmd['id']} {status}")
    except Exception as exc:
        logger.error(f"Command poll error: {exc}")


# ================= MAIN =================
def main():
    global last_esp_send, SENSOR_INTERVAL_CONFIG, last_sensor_config_fetch

    logger.info("Agent started")

    next_sensor = 0
    next_hb = 0
    next_cmd = 0
    next_config_fetch = 0

    while True:
        now = time.time()

        try:
            handle_buttons()

            # FETCH SENSOR CONFIG FROM BACKEND (every 5 min)
            if now >= next_config_fetch:
                fetch_sensor_config()
                next_config_fetch = now + CONFIG_FETCH_INTERVAL

            # SENSOR - Use configurable interval
            if now >= next_sensor:
                post_sensor_data()
                next_sensor = now + SENSOR_INTERVAL_CONFIG

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
            logger.error(f"Error: {e}")

        time.sleep(0.1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        GPIO.cleanup()
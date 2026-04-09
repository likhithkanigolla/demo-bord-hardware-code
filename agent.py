import json
import socket
import subprocess
import sys
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

# Create logs directory if it doesn't exist
logs_dir = Path(__file__).parent / "logs"
logs_dir.mkdir(exist_ok=True)
log_file = logs_dir / "pi_agent.log"

logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='[%(asctime)s] [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(log_file),  # Log to file
        logging.StreamHandler()  # Also print to console
    ]
)
logger = logging.getLogger(__name__)
logger.info(f"Pi Agent started with LOG_LEVEL={log_level}")
logger.info("="*80)
logger.info("STARTUP: Initializing Pi Agent...")
logger.info("="*80)

# ================= CONFIG =================
CONFIG_FILE = Path(__file__).parent / "config" / "config.env"
if CONFIG_FILE.exists():
    load_dotenv(CONFIG_FILE)

BACKEND_HOST = os.getenv("BACKEND_HOST", "https://smartcitylivinglab.iiit.ac.in/smartcitydigitaltwin-api").rstrip("/")
API_BASE = f"{BACKEND_HOST}/demo-board"
NODE_ID = int(os.getenv("NODE_ID", "1"))

logger.info(f"CONFIG: BACKEND_HOST = {BACKEND_HOST}")
logger.info(f"CONFIG: API_BASE = {API_BASE}")
logger.info(f"CONFIG: NODE_ID = {NODE_ID}")

ESP_URL = os.getenv("ESP_URL")
if not ESP_URL:
    ESP_IP = os.getenv("ESP_IP", "10.2.135.210")
    ESP_PORT = int(os.getenv("ESP_PORT", "8100"))
    ESP_URL = f"http://{ESP_IP}:{ESP_PORT}/data"

logger.info(f"CONFIG: ESP_URL = {ESP_URL}")

SENSOR_INTERVAL_SECONDS = 10
HEARTBEAT_INTERVAL_SECONDS = 15
COMMAND_POLL_SECONDS = 5
MIN_SENSOR_INTERVAL_SECONDS = 3.0
MAX_SENSOR_INTERVAL_SECONDS = 120.0


def _safe_interval_seconds(value, default):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        logger.warning(f"[CONFIG] Invalid sensor interval '{value}', using default {default}s")
        return float(default)

    clamped = max(MIN_SENSOR_INTERVAL_SECONDS, min(MAX_SENSOR_INTERVAL_SECONDS, parsed))
    if clamped != parsed:
        logger.warning(
            f"[CONFIG] Sensor interval {parsed}s out of range; clamped to {clamped}s "
            f"(allowed {MIN_SENSOR_INTERVAL_SECONDS}-{MAX_SENSOR_INTERVAL_SECONDS}s)"
        )
    return clamped

# Configurable sensor interval (can be updated via API)
interval_from_env = os.getenv(
    "SENSOR_INTERVAL_SECONDS",
    os.getenv("SENSOR_POLL_INTERVAL", str(SENSOR_INTERVAL_SECONDS)),
)
SENSOR_INTERVAL_CONFIG = _safe_interval_seconds(interval_from_env, SENSOR_INTERVAL_SECONDS)
SENSOR_COLLECTION_ENABLED = os.getenv("SENSOR_COLLECTION_ENABLED", "1") == "1"
last_sensor_config_fetch = 0
CONFIG_FETCH_INTERVAL = max(3.0, float(os.getenv("SENSOR_CONFIG_FETCH_INTERVAL_SECONDS", "15")))

ESP_SEND_INTERVAL = 5  # 🔥 send every 4 sec
LOCAL_ESP_QUEUE_ENABLED = os.getenv("LOCAL_ESP_QUEUE_ENABLED", "0") == "1"

logger.info(f"CONFIG: SENSOR_INTERVAL = {SENSOR_INTERVAL_CONFIG}s")
logger.info(f"CONFIG: SENSOR_COLLECTION_ENABLED = {SENSOR_COLLECTION_ENABLED}")
logger.info(f"CONFIG: HEARTBEAT_INTERVAL = {HEARTBEAT_INTERVAL_SECONDS}s")
logger.info(f"CONFIG: COMMAND_POLL_INTERVAL = {COMMAND_POLL_SECONDS}s")
logger.info(f"CONFIG: CONFIG_FETCH_INTERVAL = {CONFIG_FETCH_INTERVAL}s")
logger.info(f"CONFIG: LOCAL_ESP_QUEUE_ENABLED = {LOCAL_ESP_QUEUE_ENABLED}")


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

logger.info("INIT: Waiting for SGP30 stabilization...")
time.sleep(2)
logger.info("INIT: I2C sensors initialized (VEML7700, SI7021, SGP30)")
logger.info("="*80)

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
        
        # Log the command being sent
        logger.info(f"[ESP COMMAND] Sending to {url}")
        logger.info(f"[ESP COMMAND] Payload: {json.dumps(payload)}")
        logger.info(f"[ESP COMMAND] Command array breakdown:")
        if isinstance(cmd, list) and len(cmd) >= 8:
            logger.info(f"  - Random prefix: {cmd[0:4]}")
            logger.info(f"  - Buzzer mode: {cmd[4]}")
            logger.info(f"  - Tube state: {cmd[5]} (0=OFF, 1=ON)")
            logger.info(f"  - Tube RGB color: {cmd[6]} [R, G, B]")
            logger.info(f"  - Fan speed: {cmd[7]} (0-255)")
        else:
            logger.info(f"  - Command format unexpected: {cmd}")
        
        r = requests.post(url, json=payload, timeout=2)
        
        if r.ok:
            logger.info(f"✓ ESP command sent successfully: HTTP {r.status_code}")
        else:
            logger.warning(f"✗ ESP command failed: HTTP {r.status_code}: {r.text[:200]}")
        
        return r.ok, f"HTTP {r.status_code}: {r.text[:200]}"
    except Exception as e:
        logger.error(f"❌ ESP Error: {e}")
        return False, str(e)


# ================= SENSOR =================
def read_sensors():
    global eco2_raw, tvoc_raw

    logger.debug(f"[SENSOR] Reading sensors at {datetime.utcnow().isoformat()}Z")
    
    try:
        eco2_raw, tvoc_raw = sgp30.iaq_measure()
        logger.debug(f"[SENSOR] SGP30 read: CO2={eco2_raw}ppm, TVOC={tvoc_raw}")
    except Exception as e:
        logger.error(f"[SENSOR] SGP30 read failed: {e}")
        pass

    try:
        lux = veml.light if sensor_enabled["Lux"] else None
        if lux is not None:
            logger.debug(f"[SENSOR] VEML7700 read: Lux={lux}")
    except Exception as e:
        logger.error(f"[SENSOR] VEML7700 read failed: {e}")
        lux = None

    try:
        temp = si7021.temperature if sensor_enabled["Temp"] else None
        if temp is not None:
            logger.debug(f"[SENSOR] SI7021 read: Temp={temp}°C")
    except Exception as e:
        logger.error(f"[SENSOR] SI7021 read failed: {e}")
        temp = None

    gas = eco2_raw if sensor_enabled["CO2"] else None
    pir = get_pir_majority()
    logger.debug(f"[SENSOR] PIR read: motion={pir}")

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

    timestamp = datetime.utcnow().isoformat() + "Z"
    logger.info(f"\n[API CALL] {timestamp} - Posting sensor data...")
    
    readings = read_sensors()

    logger.info(f"[SENSOR DATA] Collected:")
    logger.info(f"    Temperature: {fmt(readings['temperature'])}°C")
    logger.info(f"    Lux: {fmt(readings['lux'])}")
    logger.info(f"    Gas: {fmt(readings['gas'])}ppm")
    logger.info(f"    PIR: {readings['pir']}")

    payload = {
        "node_id": NODE_ID,
        "sensor_type": "environmental",
        "readings": readings,
        "timestamp": timestamp,
        "metadata": {"source": "raspberry_pi_agent"}
    }

    api_url = f"{API_BASE}/receive-sensor-data"
    logger.info(f"[API] POST to: {api_url}")
    logger.debug(f"[PAYLOAD] {json.dumps(payload, indent=2)}")
    
    try:
        logger.info(f"[API] Sending request (timeout=5s)...")
        r = requests.post(api_url, json=payload, timeout=5)
        logger.info(f"[API] Response: HTTP {r.status_code}")
        
        if r.status_code == 200:
            logger.info(f"[SUCCESS] ✓ Sensor data posted successfully")
            logger.info(f"    T={fmt(readings['temperature'])}°C, Lux={fmt(readings['lux'])}, Gas={fmt(readings['gas'])}ppm")

            try:
                response_payload = r.json()
            except Exception:
                response_payload = {}

            adaptation_commands = response_payload.get("adaptation_commands", []) if isinstance(response_payload, dict) else []
            if adaptation_commands:
                logger.info(f"[ADAPTATION] Backend queued {len(adaptation_commands)} command(s)")
                for cmd in adaptation_commands[:3]:
                    logger.info(
                        f"    -> id={cmd.get('id')} type={cmd.get('command')} inserted={cmd.get('inserted')} "
                        f"dupe_skips={cmd.get('duplicate_skip_count', 0)}"
                    )
            else:
                logger.info("[ADAPTATION] No adaptation command returned for this sensor payload")
        else:
            logger.warning(f"[FAILURE] ✗ POST returned HTTP {r.status_code}")
            logger.warning(f"[RESPONSE] {r.text[:200]}")
    except requests.exceptions.Timeout:
        logger.error(f"[ERROR] ✗ POST timeout (5s exceeded)")
    except requests.exceptions.ConnectionError as e:
        logger.error(f"[ERROR] ✗ Connection failed: {e}")
    except Exception as e:
        logger.error(f"[ERROR] ✗ POST exception: {type(e).__name__}: {e}")
    
    logger.info("")

    # Autonomous local ESP queue is disabled by default.
    # Backend -> Pi polled commands remain the primary execution path.
    if LOCAL_ESP_QUEUE_ENABLED:
        esp_queue.append([1 if readings["gas"] else 0, 0, 0, 0, 0, 0, [0,0,0], 0])
        esp_queue.append([0, 1 if readings["temperature"] else 0, 0, 0, 0, 0, [0,0,0], 0])
        esp_queue.append([0, 0, 1 if readings["lux"] else 0, 0, 0, 0, [0,0,0], 0])
        esp_queue.append([0, 0, 0, readings["pir"], 0, 0, [0,0,0], 0])


def fetch_sensor_config():
    """Fetch configurable sensor interval from backend"""
    global SENSOR_INTERVAL_CONFIG, SENSOR_COLLECTION_ENABLED, last_sensor_config_fetch
    
    api_url = f"{API_BASE}/sensor-config/{NODE_ID}"
    logger.debug(f"[CONFIG FETCH] GET {api_url}")
    
    try:
        logger.debug(f"[API] Sending request (timeout=3s)...")
        r = requests.get(api_url, timeout=3)
        logger.debug(f"[API] Response: HTTP {r.status_code}")
        
        if r.status_code == 200:
            config = r.json()
            logger.debug(f"[CONFIG] Received: {config}")
            new_interval_raw = config.get("sampling_interval_seconds", SENSOR_INTERVAL_CONFIG)
            new_interval = _safe_interval_seconds(new_interval_raw, SENSOR_INTERVAL_CONFIG)
            new_enabled = bool(config.get("enabled", SENSOR_COLLECTION_ENABLED))
            if abs(new_interval - SENSOR_INTERVAL_CONFIG) > 1e-6:
                logger.info(f"[CONFIG UPDATE] ✓ Sensor interval updated: {SENSOR_INTERVAL_CONFIG}s → {new_interval}s")
                SENSOR_INTERVAL_CONFIG = new_interval
            else:
                logger.debug(f"[CONFIG] No change needed. Current: {SENSOR_INTERVAL_CONFIG}s")

            if new_enabled != SENSOR_COLLECTION_ENABLED:
                logger.info(f"[CONFIG UPDATE] ✓ Sensor collection enabled: {SENSOR_COLLECTION_ENABLED} → {new_enabled}")
                SENSOR_COLLECTION_ENABLED = new_enabled
            else:
                logger.debug(f"[CONFIG] Sensor collection unchanged: {SENSOR_COLLECTION_ENABLED}")

            last_sensor_config_fetch = time.time()
            return True
        else:
            logger.debug(f"[CONFIG] Unexpected status code: {r.status_code}")
            return False
    except requests.exceptions.Timeout:
        logger.debug(f"[CONFIG] Fetch timeout (non-critical)")
    except requests.exceptions.ConnectionError as e:
        logger.debug(f"[CONFIG] Connection failed (non-critical): {e}")
    except Exception as e:
        logger.debug(f"[CONFIG] Fetch failed (non-critical): {type(e).__name__}: {e}")
    
    return False


def post_heartbeat():
    timestamp = datetime.utcnow().isoformat() + "Z"
    ip = get_local_ip()
    
    payload = {
        "node_id": NODE_ID,
        "ip_address": ip,
        "timestamp": timestamp,
    }
    
    api_url = f"{API_BASE}/node-heartbeat"
    logger.debug(f"[HEARTBEAT] POST {api_url}")

    try:
        logger.debug(f"[API] Sending heartbeat (node_id={NODE_ID}, ip={ip})")
        r = requests.post(api_url, json=payload, timeout=5)
        logger.debug(f"[API] Response: HTTP {r.status_code}")
        
        if r.status_code == 200:
            logger.debug(f"[HEARTBEAT] ✓ Heartbeat sent successfully")
        else:
            logger.debug(f"[HEARTBEAT] ⚠ Heartbeat failed: HTTP {r.status_code}")
    except Exception as e:
        logger.debug(f"[HEARTBEAT] ⚠ Heartbeat failed (non-critical): {type(e).__name__}: {e}")


def poll_commands():
    api_url = f"{API_BASE}/commands/{NODE_ID}?status=pending"
    logger.debug(f"[POLL COMMANDS] GET {api_url}")
    
    try:
        logger.debug(f"[API] Polling for commands (timeout=5s)...")
        r = requests.get(api_url, timeout=5)
        logger.debug(f"[API] Response: HTTP {r.status_code}")
        
        data = r.json()
        cmd_count = len(data.get("commands", []))
        
        if cmd_count > 0:
            logger.info(f"[COMMANDS] Found {cmd_count} pending command(s)")
        else:
            logger.debug(f"[COMMANDS] No pending commands")

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

            logger.info(f"[COMMAND] RECEIVED: id={cmd.get('id')} type={cmd_type}")
            logger.debug(f"[COMMAND] Payload: {payload_preview}")

            status = "executed"
            message = "OK"

            if cmd_type == "ESP_COMMAND":
                cmd_list = payload.get("cmd")
                target_url = payload.get("target_url")
                
                logger.info(f"[ESP_COMMAND RECEIVED]")
                logger.info(f"  - Command ID: {cmd.get('id')}")
                logger.info(f"  - Payload: {json.dumps(payload)}")
                
                if not cmd_list:
                    status = "failed"
                    message = "Missing cmd payload"
                    logger.error(f"[ESP_COMMAND] ❌ FAILED: Missing cmd in payload")
                else:
                    logger.info(f"[ESP_COMMAND] Found command array: {cmd_list}")
                    ok, resp_msg = send_esp_command(cmd_list, target_url)
                    status = "executed" if ok else "failed"
                    message = resp_msg
                    logger.info(f"[ESP_COMMAND] Result: {status} - {message}")
            else:
                message = f"Skipped unsupported command: {cmd_type}"

            ack_url = f"{API_BASE}/commands/{cmd['id']}/ack"
            logger.debug(f"[ACK] Sending ACK to {ack_url}")
            
            try:
                ack_r = requests.post(
                    ack_url,
                    json={"status": status, "response_message": message},
                    timeout=5
                )
                logger.info(f"[COMMAND] ACK sent: id={cmd['id']} status={status} (HTTP {ack_r.status_code})")
            except Exception as ack_e:
                logger.error(f"[COMMAND] ACK failed: id={cmd['id']} error={ack_e}")
    except requests.exceptions.Timeout:
        logger.debug(f"[POLL] Timeout (non-critical)")
    except requests.exceptions.ConnectionError as e:
        logger.debug(f"[POLL] Connection failed (non-critical): {e}")
    except Exception as exc:
        logger.error(f"[POLL] Command poll error: {type(exc).__name__}: {exc}")


# ================= MAIN =================
def main():
    global last_esp_send, SENSOR_INTERVAL_CONFIG, SENSOR_COLLECTION_ENABLED, last_sensor_config_fetch

    logger.info("="*80)
    logger.info("[MAIN] Agent started - entering main loop")
    logger.info("="*80)
    
    # Check root privileges - required for GPIO access
    logger.info("[STARTUP] Checking root privileges...")
    if os.geteuid() != 0:
        logger.error("[STARTUP] ✗ ERROR: This script must be run as root (required for GPIO access)")
        logger.error("[STARTUP] Try: sudo python pi_experiment_service.py")
        sys.exit(1)
    logger.info("[STARTUP] ✓ Running as root")
    
    # Test initial connection to backend root API
    logger.info("[STARTUP] Testing backend root API connectivity...")
    try:
        root_url = BACKEND_HOST
        logger.info(f"[STARTUP] GET {root_url} (root API test)")
        r = requests.get(root_url, timeout=3)
        logger.info(f"[STARTUP] Root API response: HTTP {r.status_code} ✓")
    except Exception as e:
        logger.warning(f"[STARTUP] ⚠ Could not reach root API immediately: {e}")
        logger.warning(f"[STARTUP] Will retry on normal schedule...")
    
    # Test initial connection to demo-board API
    logger.info("[STARTUP] Testing demo-board API connectivity...")
    try:
        test_url = API_BASE
        logger.info(f"[STARTUP] GET {test_url} (demo-board API test)")
        r = requests.get(test_url, timeout=3)
        logger.info(f"[STARTUP] Demo-board API response: HTTP {r.status_code} ✓")
    except Exception as e:
        logger.warning(f"[STARTUP] ⚠ Could not reach demo-board API immediately: {e}")
        logger.warning(f"[STARTUP] Will retry on normal schedule...")
    
    logger.info("[MAIN] Starting sensor loop...\n")

    next_sensor = 0
    next_hb = 0
    next_cmd = 0
    next_config_fetch = 0
    loop_count = 0

    while True:
        now = time.time()
        loop_count += 1

        try:
            handle_buttons()

            # FETCH SENSOR CONFIG FROM BACKEND (every 5 min)
            if now >= next_config_fetch:
                logger.info(f"[TIMER] Config fetch interval reached")
                fetch_sensor_config()
                next_config_fetch = now + CONFIG_FETCH_INTERVAL

            # SENSOR - Use configurable interval
            if now >= next_sensor:
                logger.info(f"[TIMER] Sensor interval reached ({SENSOR_INTERVAL_CONFIG}s)")
                if SENSOR_COLLECTION_ENABLED:
                    post_sensor_data()
                else:
                    logger.info("[SENSOR] Collection disabled by backend config; skipping sensor POST")
                next_sensor = now + SENSOR_INTERVAL_CONFIG

            # HEARTBEAT
            if now >= next_hb:
                logger.debug(f"[TIMER] Heartbeat interval reached ({HEARTBEAT_INTERVAL_SECONDS}s)")
                post_heartbeat()
                next_hb = now + HEARTBEAT_INTERVAL_SECONDS

            # COMMAND POLL
            if now >= next_cmd:
                logger.debug(f"[TIMER] Command poll interval reached ({COMMAND_POLL_SECONDS}s)")
                poll_commands()
                next_cmd = now + COMMAND_POLL_SECONDS

            # Optional local autonomous ESP send path (disabled by default).
            if LOCAL_ESP_QUEUE_ENABLED and now - last_esp_send >= ESP_SEND_INTERVAL:
                if len(esp_queue) > 0:
                    cmd = esp_queue.pop(0)
                    logger.debug(f"[ESP] Sending queued command")
                    send_esp_command(cmd)
                    last_esp_send = now

        except Exception as e:
            logger.error(f"[MAIN LOOP] Exception: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"[TRACEBACK] {traceback.format_exc()}")

        time.sleep(0.1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        GPIO.cleanup()
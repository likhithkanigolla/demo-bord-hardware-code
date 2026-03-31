import time
import math
import board
import busio
import RPi.GPIO as GPIO

import adafruit_veml7700
import adafruit_si7021
import adafruit_sgp30

# ---------- GPIO ----------
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

# ---------- BUTTON STATE TRACKING ----------
last_state = {pin: 1 for pin in buttons}
last_pressed_time = {pin: 0 for pin in buttons}

DEBOUNCE_TIME = 0.2  # seconds

# ---------- SENSOR ENABLE/DISABLE (TOGGLE) ----------
sensor_enabled = {
    "Lux": True,
    "Temp": True,
    "CO2": True
}

# ---------- I2C ----------
i2c = busio.I2C(board.SCL, board.SDA)

veml = adafruit_veml7700.VEML7700(i2c)
si7021 = adafruit_si7021.SI7021(i2c)

sgp30 = adafruit_sgp30.Adafruit_SGP30(i2c)
sgp30.iaq_init()

print("Waiting for SGP30 stabilization...")
time.sleep(2)

print("System ready")

last_print_time = 0

# ---------- HELPER ----------
def fmt(val, unit):
    return f"{val:.2f} {unit}" if not math.isnan(val) else "NaN"

# ---------- MAIN LOOP ----------
try:
    while True:

        current_time = time.time()

        # -------- PIR --------
        if GPIO.input(PIR_PIN):
            print("Motion detected (PIR)")

        # -------- BUTTONS (EDGE DETECTION + TOGGLE) --------
        for pin, name in buttons.items():
            state = GPIO.input(pin)

            if last_state[pin] == 1 and state == 0:
                if current_time - last_pressed_time[pin] > DEBOUNCE_TIME:

                    # Toggle only for sensor buttons
                    if name in sensor_enabled:
                        sensor_enabled[name] = not sensor_enabled[name]
                        status = "ENABLED" if sensor_enabled[name] else "DISABLED"
                        print(f"{name} sensor {status}")
                    else:
                        print(f"{name} button pressed")

                    last_pressed_time[pin] = current_time

            last_state[pin] = state

        # -------- SGP30 (EVERY SECOND REQUIRED) --------
        try:
            eco2_raw, tvoc_raw = sgp30.iaq_measure()
        except:
            eco2_raw, tvoc_raw = 0, 0
            print("SGP30 read error")

        # -------- PRINT EVERY 10s --------
        if current_time - last_print_time > 10:
            last_print_time = current_time

            # Apply toggle logic
            lux = veml.light if sensor_enabled["Lux"] else float('nan')

            temp = si7021.temperature if sensor_enabled["Temp"] else float('nan')
            humidity = si7021.relative_humidity if sensor_enabled["Temp"] else float('nan')

            eco2 = eco2_raw if sensor_enabled["CO2"] else float('nan')
            tvoc = tvoc_raw if sensor_enabled["CO2"] else float('nan')

            print("\n------ Sensor Data ------")
            print(f"Lux: {fmt(lux, 'lx')}")
            print(f"Temperature: {fmt(temp, '°C')}")
            print(f"Humidity: {fmt(humidity, '%')}")
            print(f"eCO2: {fmt(eco2, 'ppm')}")
            print(f"TVOC: {fmt(tvoc, 'ppb')}")
            print("-------------------------\n")

        # Fast loop (non-blocking)
        time.sleep(0.01)

except KeyboardInterrupt:
    print("Program stopped")

finally:
    GPIO.cleanup()
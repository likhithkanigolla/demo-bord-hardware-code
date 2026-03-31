import requests
import time
import random

ESP_IP = "10.2.135.210"
PORT = 8100

url = f"http://{ESP_IP}:{PORT}/data"

while True:
    try:
        # Strip triggers (0/1)
        strips = [random.randint(0,1) for _ in range(4)]

        # Buzzer
        buzzer = random.randint(0,1)

        # Tube
        tube = random.randint(0,1)

        # RGB
        rgb = [
            random.randint(0,255),
            random.randint(0,255),
            random.randint(0,255)
        ]

        # Fan
        fan = random.randint(0,255)

        command = strips + [buzzer, tube, rgb, fan]

        payload = {
            "cmd": command
        }

        r = requests.post(url, json=payload, timeout=5)

        print("Sent:", command)
        print("Response:", r.text)
        print("-"*50)

    except Exception as e:
        print("Error:", e)
import os
import json
import re
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import paho.mqtt.client as mqtt


WATERPLANT_URL = os.environ.get("WATERPLANT_URL", "https://mitdrikkevand.dk/waterplants/49809")
MQTT_HOST = os.environ["MQTT_HOST"]
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_TOPIC = os.environ.get("MQTT_TOPIC", "waterquality/frederiksberg_soroe/state")
MQTT_USERNAME = os.environ.get("MQTT_USERNAME")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD")

MQTT_TLS = os.environ.get("MQTT_TLS", "false").lower() in ("1", "true", "yes")
MQTT_RETAIN = os.environ.get("MQTT_RETAIN", "true").lower() in ("1", "true", "yes")
MQTT_QOS = int(os.environ.get("MQTT_QOS", "1"))

# Parametre vi forsøger at hente (du kan udvide listen)
TARGETS = [
    "Nitrat (NO3)",
    "Ammonium (NH4)",
    "Nitrit (NO2)",
]

def normalized_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    # Flad tekst gør det nemt at regex'e stabilt (så længe ordene eksisterer)
    return " ".join(soup.get_text(" ", strip=True).split())

def extract_param(text: str, name: str):
    """
    Matcher typiske linjer i MitDrikkevand-tabellen, fx:
      "Nitrat (NO3) 1,30 <= 50,0 mg/l 07/10 2025 ..."
      "Ammonium (NH4) < 0,005 <= 0,050 mg/l 07/10 2025 ..."
    """
    pattern = rf"{re.escape(name)}\s+([<>]?\s*\d+(?:[.,]\d+)?)\s+.*?\s([a-zA-Z/µ]+)\s+(\d{{2}}/\d{{2}}\s+\d{{4}})"
    m = re.search(pattern, text)
    if not m:
        return None
    value = re.sub(r"\s+", " ", m.group(1).strip())
    unit = m.group(2).strip()
    date = m.group(3).strip()
    return {"value": value, "unit": unit, "date": date}

def publish(payload: dict):
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD or "")

    if MQTT_TLS:
        client.tls_set()  # bruger system CA bundle (ok til public CA / korrekt CA i image)

    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.loop_start()
    msg = json.dumps(payload, ensure_ascii=False)
    info = client.publish(MQTT_TOPIC, msg, qos=MQTT_QOS, retain=MQTT_RETAIN)
    info.wait_for_publish()
    client.loop_stop()
    client.disconnect()

def main():
    r = requests.get(WATERPLANT_URL, timeout=30)
    r.raise_for_status()

    text = normalized_text(r.text)

    values = {}
    for name in TARGETS:
        d = extract_param(text, name)
        if d:
            values[name] = d

    payload = {
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": WATERPLANT_URL,
        "values": values,
    }

    # Log til pod logs
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    publish(payload)

if __name__ == "__main__":
    main()
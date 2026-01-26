import paho.mqtt.client as mqtt
import json
import time
import numpy as np

MQTT_BROKER = "broker.emqx.io"
MQTT_PORT = 8084
SESSION_ID = "1"
PLAYER_ID = 3
PLAYER_NAME = "test3"
RATE = 8000

def on_connect(client, userdata, flags, rc):
    print(f"[DEBUG] Test Client RC {rc}")

def run_test_client():
    client = mqtt.Client(transport="websockets")
    client.on_connect = on_connect
    client.tls_set()
    client.connect(MQTT_BROKER, MQTT_PORT)
    client.loop_start()

    player_data = {
        "id": PLAYER_ID, "name": PLAYER_NAME,
        "x": 0, "y": 0, "z": 0,
        "dead": 0, "session": SESSION_ID, "global": 0, "show_map": 0, "echo": 0
    }

    data_topic = f"tdvc/{SESSION_ID}/data/{PLAYER_ID}"
    audio_topic = f"tdvc/{SESSION_ID}/audio/{PLAYER_ID}"

    try:
        while True:
            client.publish(data_topic, json.dumps(player_data), qos=0, retain=True)
            
            noise = np.random.randint(-1500, 1500, RATE, dtype=np.int16)
            client.publish(audio_topic, noise.tobytes(), qos=0)
            
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        client.publish(data_topic, payload=None, retain=True)
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    run_test_client()

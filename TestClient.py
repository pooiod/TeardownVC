import paho.mqtt.client as mqtt
import json
import time
import numpy as np
import os

MQTT_BROKER = "broker.emqx.io"
MQTT_PORT = 8084
SESSION_ID = 6432
PLAYER_ID = 3794
PLAYER_NAME = "HoldMusic"
RATE = 8000
SECONDS_PER_SEND = 1
CHUNK = int(RATE * SECONDS_PER_SEND)
DATA_PUBLISH_INTERVAL = 1

AUDIO_MODE = 'mp3' # options: 'mp3' or 'static'
MP3_PATH = 'test.mp3'

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

    def load_mp3_frames(path):
        if not os.path.exists(path):
            return None
        try:
            from pydub import AudioSegment
        except Exception:
            return None

        try:
            audio = AudioSegment.from_file(path)
            audio = audio.set_frame_rate(RATE).set_channels(1).set_sample_width(2)
            samples = np.array(audio.get_array_of_samples(), dtype=np.int16)
            return samples
        except Exception:
            return None

    try:
        client.publish(data_topic, json.dumps(player_data), qos=0, retain=True)

        last_data = time.time()
        mp3_frames = None
        mp3_idx = 0
        if AUDIO_MODE == 'mp3':
            mp3_frames = load_mp3_frames(MP3_PATH)
            if mp3_frames is None:
                print(f"[WARN] Unable to load MP3 '{MP3_PATH}', falling back to static noise")
                mp3_frames = None
        while True:
            if AUDIO_MODE == 'mp3' and mp3_frames is not None:
                end = mp3_idx + CHUNK
                if end <= len(mp3_frames):
                    chunk = mp3_frames[mp3_idx:end]
                    mp3_idx = end
                else:
                    part1 = mp3_frames[mp3_idx:]
                    part2 = mp3_frames[: max(0, CHUNK - len(part1))]
                    if len(part1) + len(part2) < CHUNK:
                        pad = np.zeros(CHUNK - (len(part1) + len(part2)), dtype=np.int16)
                        chunk = np.concatenate((part1, part2, pad))
                    else:
                        chunk = np.concatenate((part1, part2))
                    mp3_idx = len(part2)
                client.publish(audio_topic, chunk.tobytes(), qos=0)
            else:
                noise = np.random.randint(-1500, 1500, CHUNK, dtype=np.int16)
                client.publish(audio_topic, noise.tobytes(), qos=0)

            if time.time() - last_data >= DATA_PUBLISH_INTERVAL:
                client.publish(data_topic, json.dumps(player_data), qos=0, retain=True)
                last_data = time.time()

            time.sleep(CHUNK / RATE)
    except KeyboardInterrupt:
        pass
    finally:
        client.publish(data_topic, payload=None, retain=True)
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    run_test_client()

import os
import re
import json
import time
import threading
import subprocess
import webbrowser
import math
import sys
import wave
import numpy as np
import sounddevice as sd
import paho.mqtt.client as mqtt
import webview

try:
    import psutil
except ImportError:
    psutil = None

TEST_MODE = False
TEST_MP3_PATH = "test.mp3"
TEST_DATA = {
    "session": 6432,
    "userid": 1234,
    "name": "Tester",
    "pos_x": 0.0,
    "pos_y": 0.0,
    "pos_z": 0.0,
    "isdead": 0,
    "global": 0,
    "showmap": 0, # debug, do not use
    "echo": 0
}

SAVE_TAG = "steam-3653434619"
CLIENT_VERSION = 2
SAVE_PATH = os.path.expandvars(r'%LOCALAPPDATA%\Teardown\savegame.xml')
MQTT_BROKER = "broker.emqx.io"
MQTT_PORT = 8084
RATE = 8000
AUDIO_SNIP_SECONDS = 1
MAX_QUEUE_SECONDS = 4
STALE_TIMEOUT = 10
FADE_SAMPLES = int(RATE * 0.75)
RESET_SESSION_ON_START = False

HTML = """
<!DOCTYPE html>
<html>
<head>
    <style>
        body { --sb-track-color: #000000; --sb-thumb-color: #ffffff; --sb-size: 14px; } body::-webkit-scrollbar { width: var(--sb-size) } body::-webkit-scrollbar-track { background: var(--sb-track-color); } body::-webkit-scrollbar-thumb { background: var(--sb-thumb-color); border-radius: 10px; border: 4px solid #000000; } @supports not selector(::-webkit-scrollbar) { body { scrollbar-color: var(--sb-thumb-color) var(--sb-track-color); } }
        body { background: #111; color: #eee; font-family: sans-serif; padding: 15px; user-select: none; }
        .card { background: #1f1f1f; border-radius: 8px; padding: 15px; margin-bottom: 15px; border: 1px solid #333; }
        h3 { margin: 0 0 10px 0; color: #00ffaa; font-size: 14px; text-transform: uppercase; }
        select { background: #333; color: white; border: 1px solid #444; padding: 8px; width: 100%; margin-bottom: 8px; border-radius: 4px; }
        .p-row { display: flex; align-items: center; background: #252525; margin: 5px 0; padding: 8px; border-radius: 4px; }
        .p-info { flex: 1; font-size: 13px; } .p-name { font-weight: bold; } .p-sub { font-size: 11px; color: #888; }
        .meter { width: 80px; height: 8px; background: #000; border-radius: 4px; overflow: hidden; }
        .fill { height: 100%; background: #00ffaa; width: 0%; transition: width 0.1s; }
        .setting-row { display: flex; align-items: center; justify-content: space-between; margin: 10px 0; font-size: 13px; }
        input[type="range"] { flex-grow: 1; margin: 0 10px; } input[type="checkbox"] { margin-right: 10px; }
        #minimap { display: none; background: #000; border-radius: 8px; width: 100%; aspect-ratio: 1; }
        .loader { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); display: flex; justify-content: center; align-items: center; z-index: 100; flex-direction: column; text-align: center; }
        .spinner { border: 4px solid rgba(255,255,255,0.3); border-top: 4px solid #00ffaa; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin-bottom: 20px; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        .header-info { display: flex; justify-content: space-between; align-items: center; }
        #launch-btn { position: fixed; top: 12px; right: 12px; background: #00ffaa; color: #111; border: none; padding: 8px 12px; border-radius: 6px; cursor: pointer; z-index: 200; display: none; font-weight: bold; }
        #launch-btn.disabled { opacity: 0.5; pointer-events: none; }
    </style>
</head>
<body>
    <button id="launch-btn" onclick="launchTeardown()">Launch Teardown</button>
    <div id="loader" class="loader">
        <div class="spinner"></div>
        <h3 id="loader-text">Loading...</h3>
    </div>
    <div class="card">
        <h3>Settings</h3>
        <div class="setting-row"> <label>Hear Self</label> <input type="checkbox" id="hearSelf" onchange="updateSettings()"> </div>
        <div class="setting-row"> <label>Mic Gain</label> <input type="range" id="micGain" min="0" max="200" value="100" oninput="updateSettings()"> <span id="micGainLabel">100%</span> </div>
        <div class="setting-row"> <label>VC Volume</label> <input type="range" id="masterVol" min="0" max="150" value="100" oninput="updateSettings()"> <span id="masterVolLabel">100%</span> </div>
    </div>
    <div class="card">
        <h3>Audio Devices</h3>
        <select id="mic" onchange="setIO()"></select> <select id="spk" onchange="setIO()"></select>
    </div>
    <div class="card">
        <div class="header-info" id="playerlist">
            <h3>Players</h3>
            <span style="font-size: 12px; color: #888;">Room ID: <b id="session-id">0</b></span>
        </div>
        <div id="list"></div>
    </div>
    <div class="card" id="map-container" style="display:none;">
        <h3>Minimap</h3> <canvas id="minimap"></canvas>
    </div>
    <script>
        function setIO() { pywebview.api.set_io(parseInt(document.getElementById('mic').value), parseInt(document.getElementById('spk').value)); }
        function updateSettings() {
            const settings = {
                hear_self: document.getElementById('hearSelf').checked,
                mic_gain: document.getElementById('micGain').value / 100,
                master_vol: document.getElementById('masterVol').value / 100
            };
            document.getElementById('micGainLabel').innerText = `${Math.round(settings.mic_gain * 100)}%`;
            document.getElementById('masterVolLabel').innerText = `${Math.round(settings.master_vol * 100)}%`;
            pywebview.api.update_settings(settings);
        }
        function render(jsonStr) {
            const data = JSON.parse(jsonStr);
            const loader = document.getElementById('loader');
            const loaderText = document.getElementById('loader-text');
            if (data.session === 0) {
                loader.style.display = 'flex';
                loaderText.innerText = "Waiting for Teardown Session...";
            } else {
                loader.style.display = 'none';
            }
            document.getElementById('session-id').innerText = data.session;
            document.getElementById('list').innerHTML = '';
            data.players.forEach(p => {
                const row = document.createElement('div');
                row.className = 'p-row';
                row.style.color = (p.status == 'DEAD'? 'red' : 'white');
                row.innerHTML = `<div class="p-info"><div class="p-name">${p.name} ${p.local ? '(You)' : ''}</div><div class="p-sub">Player ${p.id}, Echo: ${p.echo}ms</div></div><div class="meter"><div class="fill" style="width: ${p.vol}%"></div></div>`;
                document.getElementById('list').appendChild(row);
            });
            if (data.players.length > 1) document.getElementById('playerlist').style.display = "";
            else document.getElementById('playerlist').style.display = "none";
            drawMap(data.players, data.show_map);
        }
        function drawMap(players, show) {
            const container = document.getElementById('map-container');
            if (!show || players.length === 0) { container.style.display = 'none'; return; }
            container.style.display = 'block';
            const canvas = document.getElementById('minimap');
            const ctx = canvas.getContext('2d');
            canvas.width = canvas.offsetWidth; canvas.height = canvas.offsetHeight;
            let minX = players[0].x, maxX = players[0].x, minY = players[0].y, maxY = players[0].y, minZ = players[0].z, maxZ = players[0].z;
            players.forEach(p => {
                if (p.x < minX) minX = p.x; if (p.x > maxX) maxX = p.x;
                if (p.y < minY) minY = p.y; if (p.y > maxY) maxY = p.y;
                if (p.z < minZ) minZ = p.z; if (p.z > maxZ) maxZ = p.z;
            });
            const worldSize = Math.max(20, maxX - minX, maxZ - minZ, maxY - minY) * 1.2;
            const zoom = canvas.width / worldSize;
            const centerX = (minX + maxX) / 2;
            const centerZ = (minZ + maxZ) / 2;
            const minYval = minY, maxYval = maxY;
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            players.forEach(p => {
                const cx = (p.x - centerX) * zoom + canvas.width / 2;
                const cz = (p.z - centerZ) * zoom + canvas.height / 2;
                let heightFactor = 0;
                if (maxYval > minYval) heightFactor = (p.y - minYval) / (maxYval - minYval);
                const radius = 4 + Math.round(heightFactor * 6);
                ctx.beginPath(); ctx.arc(cx, cz, radius, 0, 2 * Math.PI);
                ctx.fillStyle = p.local ? '#00ffaa' : '#ffaa00'; ctx.fill();
            });
        }
        function launchTeardown(){
            const btn = document.getElementById('launch-btn');
            btn.classList.add('disabled');
            btn.innerText = 'Launching...';
            pywebview.api.launch_teardown().then(res => {
                if(res && res.error){ btn.innerText = 'Launch Failed'; setTimeout(()=>btn.classList.remove('disabled'),1000); }
                else { btn.style.display = 'none'; }
            });
        }
        function updateLaunchButton(){
            pywebview.api.is_teardown_running().then(res => {
                const btn = document.getElementById('launch-btn');
                if(res && res.running){ btn.style.display = 'none'; }
                else{ btn.style.display = 'block'; btn.innerText = 'Launch Teardown'; btn.classList.remove('disabled'); }
            });
        }
        window.addEventListener('pywebviewready', () => {
            const loaderText = document.getElementById('loader-text');
            loaderText.innerText = "Loading Audio Devices...";
            pywebview.api.init_devices().then(res => {
                if(res.error) { loaderText.innerText = res.error; return; }
                const m = document.getElementById('mic');
                const s = document.getElementById('spk');
                res.mics.forEach(d => { const opt = new Option(d.name, d.id); if(d.id === res.def_mic) opt.selected = true; m.add(opt); });
                res.spks.forEach(d => { const opt = new Option(d.name, d.id); if(d.id === res.def_spk) opt.selected = true; s.add(opt); });
                updateSettings();
                updateLaunchButton();
                setInterval(updateLaunchButton, 2000);
            });
        });
    </script>
</body>
</html>
"""

def get_steam_username():
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
        steam_path = winreg.QueryValueEx(key, "SteamPath")[0]
        login_vdf = os.path.join(steam_path, "config", "loginusers.vdf")
        with open(login_vdf, 'r', encoding='utf-8') as f:
            content = f.read()
        users = re.findall(r'"PersonaName"\s+"([^"]+)"', content)
        if users:
            return users[-1]
    except Exception:
        pass
    try:
        return os.getlogin()
    except Exception:
        return "Player"

def force_reset_session():
    if not os.path.exists(SAVE_PATH):
        return True
    try:
        with open(SAVE_PATH, 'r+', encoding='utf-8') as f:
            content = f.read()
            m = re.search(fr'(<{SAVE_TAG}>(.*?)</{SAVE_TAG}>)', content, re.S)
            if m:
                full_tag, inner = m.group(1), m.group(2)
                new_inner = re.sub(r'<session\s+value="[^"]*"', '<session value="0"', inner)
                if RESET_SESSION_ON_START:
                    f.seek(0)
                    f.write(content.replace(full_tag, f'<{SAVE_TAG}>{new_inner}</{SAVE_TAG}>', 1))
                    f.truncate()
            else:
                return True
    except Exception:
        pass
    return True

def resample_audio(samples, from_rate, to_rate):
    if from_rate == to_rate or len(samples) == 0:
        return samples
    num_output = int(round(len(samples) * float(to_rate) / float(from_rate)))
    if num_output == 0:
        return np.zeros(0, dtype=samples.dtype)
    x_old = np.linspace(0, 1, len(samples), endpoint=False)
    x_new = np.linspace(0, 1, num_output, endpoint=False)
    return np.interp(x_new, x_old, samples).astype(samples.dtype)

def soft_clip(samples, gain=1.0):
    samples_f = samples.astype(np.float32) * (gain / 32768.0)
    return (np.tanh(samples_f) * 32767.0).astype(np.int16)

def load_audio_file(file_path, target_rate):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(script_dir, file_path),
        os.path.join(script_dir, "test.wav"),
        os.path.abspath(file_path),
        os.path.abspath("test.wav")
    ]
    resolved_path = None
    for p in candidates:
        if os.path.isfile(p):
            resolved_path = p
            break
    if not resolved_path:
        t = np.linspace(0, 1, target_rate, False)
        return (np.sin(2 * np.pi * 440 * t) * 10000).astype(np.int16)

    ext = os.path.splitext(resolved_path)[1].lower()
    if ext == ".wav":
        try:
            with wave.open(resolved_path, 'rb') as wf:
                sr = wf.getframerate()
                n_ch = wf.getnchannels()
                sw = wf.getsampwidth()
                frames = wf.readframes(wf.getnframes())
                if sw == 2:
                    raw = np.frombuffer(frames, dtype=np.int16)
                elif sw == 1:
                    raw = ((np.frombuffer(frames, dtype=np.uint8).astype(np.int32) - 128) * 256).astype(np.int16)
                else:
                    raw = np.frombuffer(frames, dtype=np.int32) >> 16
                if n_ch > 1:
                    raw = raw.reshape(-1, n_ch).mean(axis=1).astype(np.int16)
                return resample_audio(raw, sr, target_rate)
        except Exception:
            pass

    try:
        import soundfile as sf
        data, sr = sf.read(resolved_path, dtype='float32')
        if data.ndim > 1:
            data = data.mean(axis=1)
        data = resample_audio(data, sr, target_rate)
        return (data * 32767.0).clip(-32768, 32767).astype(np.int16)
    except Exception:
        pass

    try:
        import miniaudio
        decoded = miniaudio.decode_file(resolved_path, output_format=miniaudio.SampleFormat.SIGNED16, nchannels=1, sample_rate=target_rate)
        return np.frombuffer(decoded.samples, dtype=np.int16)
    except Exception:
        pass

    try:
        import imageio_ffmpeg
        ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [ffmpeg_bin, '-i', resolved_path, '-f', 's16le', '-acodec', 'pcm_s16le', '-ar', str(target_rate), '-ac', '1', '-']
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True)
        return np.frombuffer(proc.stdout, dtype=np.int16)
    except Exception:
        pass

    try:
        cmd = ['ffmpeg', '-i', resolved_path, '-f', 's16le', '-acodec', 'pcm_s16le', '-ar', str(target_rate), '-ac', '1', '-']
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True)
        return np.frombuffer(proc.stdout, dtype=np.int16)
    except Exception:
        pass

    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_file(resolved_path)
        audio = audio.set_frame_rate(target_rate).set_channels(1).set_sample_width(2)
        return np.array(audio.get_array_of_samples(), dtype=np.int16)
    except Exception:
        pass

    t = np.linspace(0, 1, target_rate, False)
    return (np.sin(2 * np.pi * 440 * t) * 10000).astype(np.int16)

class VoiceChat:
    def __init__(self):
        self.audio_lock = threading.Lock()
        try:
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, transport="websockets")
        except (AttributeError, TypeError):
            self.client = mqtt.Client(transport="websockets")

        self.client.on_connect = self.on_mqtt_connect
        self.client.on_message = self.on_mqtt_message
        self.client.on_subscribe = self.on_mqtt_subscribe
        self.client.tls_set()

        try:
            default_dev = sd.default.device
            self.mic_id = default_dev[0] if default_dev[0] is not None and default_dev[0] >= 0 else None
            self.spk_id = default_dev[1] if default_dev[1] is not None and default_dev[1] >= 0 else None
        except Exception:
            self.mic_id = None
            self.spk_id = None

        self.running = True
        
        initial_name = TEST_DATA.get("name", "Tester") if TEST_MODE else get_steam_username()
        initial_id = int(TEST_DATA.get("userid", 0)) if TEST_MODE else 0
        initial_session = int(TEST_DATA.get("session", 0)) if TEST_MODE else 0
        
        self.local = {
            "id": initial_id,
            "name": initial_name,
            "x": 0.0, "y": 0.0, "z": 0.0,
            "dead": 0 if TEST_MODE else 1,
            "session": initial_session,
            "show_map": 0, "echo": 0, "global": 0,
            "rate": RATE
        }
        self.peers = {}
        self.levels = {}
        self.audio_queues = {}
        self.last_seen = {}
        self.last_pcm = {}
        self.fade_pos = {}
        self.last_audio_time = {}
        self.settings = {'hear_self': False, 'mic_gain': 1.0, 'master_vol': 1.0}
        
        self.echo_buffer = np.zeros(RATE * 4, dtype=np.float32)
        self.echo_pos = 0
        self.self_hear_buf = bytearray()
        self.send_acc = bytearray()

        self.in_stream = None
        self.out_stream = None
        self.mic_rate = 48000
        self.spk_rate = 48000
        self.test_audio_samples = np.zeros(0, dtype=np.int16)
        self.test_audio_idx = 0

        self.start_audio_streams()

        self.client.connect(MQTT_BROKER, MQTT_PORT)
        self.client.loop_start()

    def start_audio_streams(self):
        self.stop_audio_streams()
        try:
            devices = sd.query_devices()
            if self.mic_id is not None and self.mic_id < len(devices):
                self.mic_rate = int(devices[self.mic_id].get('default_samplerate', 48000))
            else:
                self.mic_rate = 48000

            if self.spk_id is not None and self.spk_id < len(devices):
                self.spk_rate = int(devices[self.spk_id].get('default_samplerate', 48000))
            else:
                self.spk_rate = 48000
        except Exception:
            self.mic_rate = 48000
            self.spk_rate = 48000

        if TEST_MODE:
            self.test_audio_samples = load_audio_file(TEST_MP3_PATH, self.mic_rate)
            self.test_audio_idx = 0

        try:
            self.in_stream = sd.InputStream(
                device=self.mic_id,
                channels=1,
                samplerate=self.mic_rate,
                dtype='int16',
                blocksize=512,
                callback=self.mic_callback
            )
            self.in_stream.start()
        except Exception as e:
            print(f"[AUDIO] Mic Stream Error: {e}")

        try:
            self.out_stream = sd.OutputStream(
                device=self.spk_id,
                channels=2,
                samplerate=self.spk_rate,
                dtype='int16',
                blocksize=512,
                callback=self.spk_callback
            )
            self.out_stream.start()
        except Exception as e:
            print(f"[AUDIO] Spk Stream Error: {e}")

    def stop_audio_streams(self):
        if self.in_stream is not None:
            try:
                self.in_stream.stop()
                self.in_stream.close()
            except Exception:
                pass
            self.in_stream = None

        if self.out_stream is not None:
            try:
                self.out_stream.stop()
                self.out_stream.close()
            except Exception:
                pass
            self.out_stream = None

    def set_io(self, mic_id, spk_id):
        self.mic_id = mic_id
        self.spk_id = spk_id
        self.start_audio_streams()

    def mic_callback(self, indata, frames, time_info, status):
        try:
            if TEST_MODE and len(self.test_audio_samples) > 0:
                end = self.test_audio_idx + frames
                if end <= len(self.test_audio_samples):
                    raw_hw = self.test_audio_samples[self.test_audio_idx:end]
                    self.test_audio_idx = end
                else:
                    part1 = self.test_audio_samples[self.test_audio_idx:]
                    part2 = self.test_audio_samples[: max(0, frames - len(part1))]
                    if len(part1) + len(part2) < frames:
                        pad = np.zeros(frames - (len(part1) + len(part2)), dtype=np.int16)
                        raw_hw = np.concatenate((part1, part2, pad))
                    else:
                        raw_hw = np.concatenate((part1, part2))
                    self.test_audio_idx = len(part2)
            else:
                raw_hw = indata[:, 0]

            raw_8k = resample_audio(raw_hw, self.mic_rate, RATE)
            gain = self.settings.get('mic_gain', 1.0)
            in_proc = raw_8k.astype(np.float32) * gain

            cur_echo = max(0, int(self.local.get("echo", 0)))
            if cur_echo > 0:
                delay_samples = max(1, int(RATE * (cur_echo / 1000.0)))
                n_samples = len(in_proc)
                read_idx = (self.echo_pos - delay_samples + np.arange(n_samples)) % len(self.echo_buffer)
                delayed = self.echo_buffer[read_idx]
                snd_f = in_proc + (delayed * 0.48)
                write_idx = (self.echo_pos + np.arange(n_samples)) % len(self.echo_buffer)
                self.echo_buffer[write_idx] = snd_f
                self.echo_pos = (self.echo_pos + n_samples) % len(self.echo_buffer)
            else:
                snd_f = in_proc
                self.echo_buffer.fill(0)

            snd_8k = soft_clip(snd_f, 1.0)

            level = float(np.abs(snd_8k).mean()) if len(snd_8k) > 0 else 0.0
            self.levels[str(self.local["id"])] = level

            if self.settings.get('hear_self', False) and not self.local["dead"]:
                with self.audio_lock:
                    self.self_hear_buf.extend(snd_8k.tobytes())
                    if len(self.self_hear_buf) > RATE * 2:
                        self.self_hear_buf = self.self_hear_buf[-(RATE * 2):]

            if not self.local["dead"] and self.local["session"] > 0 and self.local["id"] != 0:
                with self.audio_lock:
                    self.send_acc.extend(snd_8k.tobytes())
                    snip_bytes = RATE * 2 * AUDIO_SNIP_SECONDS
                    if len(self.send_acc) >= snip_bytes:
                        payload = bytes(self.send_acc[:snip_bytes])
                        del self.send_acc[:snip_bytes]
                        self.client.publish(f"tdvc/{self.local['session']}/audio/{self.local['id']}", payload, qos=0)
        except Exception:
            pass

    def spk_callback(self, outdata, frames, time_info, status):
        try:
            needed_8k = int(math.ceil(frames * RATE / self.spk_rate))
            mix_l_8k = np.zeros(needed_8k, dtype=np.float32)
            mix_r_8k = np.zeros(needed_8k, dtype=np.float32)
            byte_size = needed_8k * 2

            with self.audio_lock:
                for uid, q in list(self.audio_queues.items()):
                    if str(uid) == str(self.local["id"]):
                        continue
                    try:
                        p_meta = self.peers.get(uid, {})
                        vl, vr = (1.0, 1.0) if p_meta.get("global") else self.spatial_calc(p_meta)

                        if len(q) >= byte_size:
                            chunk_bytes = bytes(q[:byte_size])
                            del q[:byte_size]
                            pcm = np.frombuffer(chunk_bytes, dtype=np.int16).astype(np.float32)
                            self.last_pcm[uid] = pcm.copy()
                            self.fade_pos[uid] = 0
                            self.levels[uid] = float(np.abs(pcm).mean() * ((vl + vr) / 2.0))
                            mix_l_8k += pcm * vl
                            mix_r_8k += pcm * vr
                        elif len(q) > 0:
                            avail = len(q) // 2
                            chunk_bytes = bytes(q[:avail * 2])
                            del q[:avail * 2]
                            pcm_part = np.frombuffer(chunk_bytes, dtype=np.int16).astype(np.float32)
                            padded = np.zeros(needed_8k, dtype=np.float32)
                            padded[:avail] = pcm_part
                            if uid in self.last_pcm and len(self.last_pcm[uid]) > 0:
                                last = self.last_pcm[uid]
                                rem = needed_8k - avail
                                rep_idx = np.arange(rem) % len(last)
                                decay = np.linspace(1.0, 0.7, rem, endpoint=False)
                                padded[avail:] = last[rep_idx] * decay
                            self.last_pcm[uid] = padded.copy()
                            self.fade_pos[uid] = 0
                            self.levels[uid] = float(np.abs(padded).mean() * ((vl + vr) / 2.0))
                            mix_l_8k += padded * vl
                            mix_r_8k += padded * vr
                        else:
                            fade_p = self.fade_pos.get(uid, 0)
                            if uid in self.last_pcm and fade_p < FADE_SAMPLES:
                                last = self.last_pcm[uid]
                                rep_idx = np.arange(needed_8k) % len(last)
                                progress = (fade_p + np.arange(needed_8k)) / float(FADE_SAMPLES)
                                env = np.clip(1.0 - progress, 0.0, 1.0).astype(np.float32)
                                pcm_decay = last[rep_idx] * env
                                self.fade_pos[uid] = fade_p + needed_8k
                                self.levels[uid] = float(np.abs(pcm_decay).mean() * ((vl + vr) / 2.0))
                                mix_l_8k += pcm_decay * vl
                                mix_r_8k += pcm_decay * vr
                            else:
                                self.levels[uid] = 0.0
                                self.last_pcm.pop(uid, None)
                    except Exception:
                        continue

                if self.settings.get('hear_self', False) and not self.local["dead"]:
                    if len(self.self_hear_buf) >= byte_size:
                        chunk = bytes(self.self_hear_buf[:byte_size])
                        del self.self_hear_buf[:byte_size]
                        pcm = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
                        mix_l_8k += pcm
                        mix_r_8k += pcm

            mix_l_hw = resample_audio(mix_l_8k, RATE, self.spk_rate)
            mix_r_hw = resample_audio(mix_r_8k, RATE, self.spk_rate)

            if len(mix_l_hw) < frames:
                mix_l_hw = np.pad(mix_l_hw, (0, frames - len(mix_l_hw)))
                mix_r_hw = np.pad(mix_r_hw, (0, frames - len(mix_r_hw)))
            else:
                mix_l_hw = mix_l_hw[:frames]
                mix_r_hw = mix_r_hw[:frames]

            master_vol = self.settings.get('master_vol', 1.0)
            out_l = soft_clip(mix_l_hw, master_vol)
            out_r = soft_clip(mix_r_hw, master_vol)

            outdata[:, 0] = out_l
            outdata[:, 1] = out_r
        except Exception:
            outdata.fill(0)

    def on_mqtt_connect(self, client, userdata, flags, rc, *args):
        code = getattr(rc, "value", rc)
        print(f"[MQTT] Connected with code {code}")
        if self.local["session"] > 0:
            client.subscribe(f"tdvc/{self.local['session']}/#")
            if self.local["id"] != 0:
                client.publish(f"tdvc/{self.local['session']}/data/{self.local['id']}", json.dumps(self.local), qos=0, retain=True)

    def on_mqtt_subscribe(self, client, userdata, mid, *args):
        print(f"[MQTT] Subscribed to session room")

    def on_mqtt_message(self, c, u, m):
        try:
            topic_parts = m.topic.split("/")
            if "audio" in topic_parts:
                uid = str(topic_parts[-1])
                if str(self.local["id"]) != "0" and uid == str(self.local["id"]):
                    return

                raw_samples = np.frombuffer(m.payload, dtype=np.int16)
                if len(raw_samples) == 0:
                    return

                p_meta = self.peers.get(uid, {})
                peer_rate = int(p_meta.get("rate", p_meta.get("samplerate", 0)))
                now = time.time()
                last_t = self.last_audio_time.get(uid, 0)
                dt = now - last_t if last_t > 0 else 1.0
                self.last_audio_time[uid] = now

                if peer_rate <= 0:
                    standard_rates = [8000, 11025, 12000, 16000, 22050, 24000, 32000, 44100, 48000, 96000]
                    if 0.4 <= dt <= 2.5:
                        est_rate = int(round(len(raw_samples) / dt))
                        peer_rate = min(standard_rates, key=lambda r: abs(r - est_rate))
                    elif len(raw_samples) in standard_rates:
                        peer_rate = len(raw_samples)
                    else:
                        peer_rate = min(standard_rates, key=lambda r: abs(r - len(raw_samples)))

                if peer_rate != RATE and peer_rate > 0:
                    norm_samples = resample_audio(raw_samples, peer_rate, RATE)
                else:
                    norm_samples = raw_samples

                with self.audio_lock:
                    if uid not in self.audio_queues:
                        self.audio_queues[uid] = bytearray()
                    self.audio_queues[uid].extend(norm_samples.tobytes())
                    self.last_seen[uid] = now
                    if len(self.audio_queues[uid]) > (RATE * 2 * MAX_QUEUE_SECONDS):
                        self.audio_queues[uid] = self.audio_queues[uid][-(RATE * 2 * MAX_QUEUE_SECONDS):]
            elif "data" in topic_parts:
                uid = str(topic_parts[-1])
                if not m.payload or len(m.payload) == 0:
                    with self.audio_lock:
                        self.peers.pop(uid, None)
                        self.audio_queues.pop(uid, None)
                        self.levels.pop(uid, None)
                        self.last_seen.pop(uid, None)
                        self.last_pcm.pop(uid, None)
                        self.fade_pos.pop(uid, None)
                        self.last_audio_time.pop(uid, None)
                    return
                try:
                    p = json.loads(m.payload.decode('utf-8'))
                except Exception:
                    return
                p_id = str(p.get("id", uid))
                if str(self.local["id"]) != "0" and (p_id == str(self.local["id"]) or uid == str(self.local["id"])):
                    return
                with self.audio_lock:
                    self.peers[p_id] = p
                    self.last_seen[p_id] = time.time()
        except Exception as e:
            print(f"[MQTT ERR] {e}")

    def spatial_calc(self, p):
        if not p:
            return 0.5, 0.5
        dx = float(p.get("x", 0)) - self.local["x"]
        dy = float(p.get("y", 0)) - self.local["y"]
        dz = float(p.get("z", 0)) - self.local["z"]
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        vol = max(0.0, 1.0 - (dist / 45.0))
        pan = np.clip(dx / -15.0, -0.8, 0.8)
        return vol * (1.0 - pan), vol * (1.0 + pan)

    def teardown_monitor(self):
        ls = -1
        last_pub_time = 0

        while self.running:
            if TEST_MODE:
                cs = int(TEST_DATA.get("session", 0))
                current_userid = int(TEST_DATA.get("userid", 0))
                current_name = str(TEST_DATA.get("name", "Tester"))
                
                if cs != ls:
                    if ls > 0 and self.local["id"] != 0:
                        self.client.publish(f"tdvc/{ls}/data/{self.local['id']}", payload=b"", retain=True)
                        self.client.unsubscribe(f"tdvc/{ls}/#")
                    if cs > 0:
                        print(f"[MONITOR] Subscribing to Test Session {cs}")
                        self.client.subscribe(f"tdvc/{cs}/#")
                        with self.audio_lock:
                            self.peers.clear()
                            self.audio_queues.clear()
                            self.levels.clear()
                            self.last_pcm.clear()
                            self.fade_pos.clear()
                            self.last_audio_time.clear()
                    ls = cs

                self.local.update({
                    "id": current_userid,
                    "name": current_name,
                    "x": float(TEST_DATA.get("pos_x", 0.0)),
                    "y": float(TEST_DATA.get("pos_y", 0.0)),
                    "z": float(TEST_DATA.get("pos_z", 0.0)),
                    "dead": int(TEST_DATA.get("isdead", 0)),
                    "session": cs,
                    "global": int(TEST_DATA.get("global", 0)),
                    "show_map": int(TEST_DATA.get("showmap", 0)),
                    "echo": int(TEST_DATA.get("echo", 0)),
                    "rate": RATE
                })

                with self.audio_lock:
                    self.peers.pop(str(current_userid), None)

                now = time.time()
                if cs > 0 and self.local["id"] != 0 and (now - last_pub_time >= 0.5):
                    self.client.publish(f"tdvc/{cs}/data/{self.local['id']}", json.dumps(self.local), qos=0, retain=True)
                    last_pub_time = now
            elif os.path.exists(SAVE_PATH):
                try:
                    with open(SAVE_PATH, 'r', encoding='utf-8', errors='ignore') as f:
                        xml = f.read()
                    m = re.search(fr'<{SAVE_TAG}>(.*?)</{SAVE_TAG}>', xml, re.S)
                    if m:
                        inner = m.group(1)

                        def g(k, default=0):
                            mm = re.search(rf'<{k}\s+value="([^"]*)"', inner)
                            if not mm:
                                return default
                            val_str = mm.group(1).strip()
                            try:
                                return float(val_str) if '.' in val_str else int(val_str)
                            except (ValueError, TypeError):
                                return default

                        cs = int(g("session", 0))
                        current_userid = int(g("userid", 0))

                        if cs != ls:
                            if ls > 0 and self.local["id"] != 0:
                                self.client.publish(f"tdvc/{ls}/data/{self.local['id']}", payload=b"", retain=True)
                                self.client.unsubscribe(f"tdvc/{ls}/#")
                            
                            if cs > 0:
                                print(f"[MONITOR] Subscribing to Session {cs}")
                                self.client.subscribe(f"tdvc/{cs}/#")
                                with self.audio_lock:
                                    self.peers.clear()
                                    self.audio_queues.clear()
                                    self.levels.clear()
                                    self.last_pcm.clear()
                                    self.fade_pos.clear()
                                    self.last_audio_time.clear()
                            
                            ls = cs

                        self.local.update({
                            "id": current_userid, 
                            "x": float(g("pos_x", 0)) / 100.0, 
                            "y": float(g("pos_y", 0)) / 100.0, 
                            "z": float(g("pos_z", 0)) / 100.0, 
                            "dead": int(g("isdead", 1)), 
                            "session": cs, 
                            "global": int(g("global", 0)), 
                            "show_map": int(g("showmap", 0)), 
                            "echo": int(g("echo", 0)),
                            "rate": RATE
                        })

                        with self.audio_lock:
                            self.peers.pop(str(current_userid), None)

                        now = time.time()
                        if cs > 0 and self.local["id"] != 0 and (now - last_pub_time >= 0.5):
                            self.client.publish(f"tdvc/{cs}/data/{self.local['id']}", json.dumps(self.local), qos=0, retain=True)
                            last_pub_time = now

                except Exception as e:
                    print(f"[MONITOR ERR] {e}")

            now = time.time()
            with self.audio_lock:
                stale = [uid for uid, ts in list(self.last_seen.items()) if now - ts > STALE_TIMEOUT]
                for uid in stale:
                    self.peers.pop(uid, None)
                    self.audio_queues.pop(uid, None)
                    self.levels.pop(uid, None)
                    self.last_seen.pop(uid, None)
                    self.last_pcm.pop(uid, None)
                    self.fade_pos.pop(uid, None)
                    self.last_audio_time.pop(uid, None)

            time.sleep(0.3)

    def is_teardown_running(self):
        t = {"teardown.exe", "Teardown.exe"}
        if psutil:
            for p in psutil.process_iter(['name']):
                try:
                    if p.info['name'] in t:
                        return True
                except Exception:
                    pass
            return False
        try:
            o = subprocess.check_output(['tasklist'], shell=True).decode(errors='ignore')
            return any(x.lower() in o.lower() for x in t)
        except Exception:
            return False

    def launch_teardown(self):
        try:
            webbrowser.open("steam://rungameid/1167630")
            return {'ok': True}
        except Exception as e:
            return {'error': str(e)}

class Bridge:
    def __init__(self, vc): 
        self.vc = vc

    def init_devices(self):
        mics, spks = [], []
        try:
            devices = sd.query_devices()
            for idx, d in enumerate(devices):
                if d['max_input_channels'] > 0:
                    mics.append({'id': idx, 'name': d['name']})
                if d['max_output_channels'] > 0:
                    spks.append({'id': idx, 'name': d['name']})

            def_in, def_out = sd.default.device
            if def_in is None or def_in < 0:
                def_in = mics[0]['id'] if mics else 0
            if def_out is None or def_out < 0:
                def_out = spks[0]['id'] if spks else 0
        except Exception as e:
            print(f"[DEVICE ERR] {e}")
            def_in, def_out = 0, 0

        return {'mics': mics, 'spks': spks, 'def_mic': def_in, 'def_spk': def_out}

    def set_io(self, mic, spk): 
        self.vc.set_io(mic, spk)

    def update_settings(self, s): 
        self.vc.settings = s

    def is_teardown_running(self): 
        return {'running': self.vc.is_teardown_running()}

    def launch_teardown(self): 
        return self.vc.launch_teardown()

def gui_updater(vc, win):
    while vc.running:
        try:
            plist = []
            plist.append({
                "id": vc.local["id"],
                "name": vc.local["name"],
                "vol": min(100, int(vc.levels.get(str(vc.local["id"]), 0) / 10)),
                "status": "DEAD" if vc.local["dead"] else "LIVE",
                "local": True,
                "x": vc.local["x"],
                "y": vc.local["y"],
                "z": vc.local["z"],
                "echo": vc.local["echo"]
            })
            with vc.audio_lock:
                peer_items = list(vc.peers.items())
            for uid, p in peer_items:
                if str(uid) == str(vc.local["id"]):
                    continue
                plist.append({
                    "id": uid,
                    "name": p.get("name", f"Player {uid}"),
                    "vol": min(100, int(vc.levels.get(uid, 0) / 10)),
                    "status": "DEAD" if p.get("dead") else "LIVE",
                    "local": False,
                    "x": p.get("x", 0),
                    "y": p.get("y", 0),
                    "z": p.get("z", 0),
                    "echo": p.get("echo", 0)
                })
            win.evaluate_js(f"render('{json.dumps({'session': vc.local['session'], 'players': plist, 'show_map': vc.local['show_map']})}')")
        except Exception:
            pass
        time.sleep(0.1)

if __name__ == "__main__":
    if force_reset_session():
        v = VoiceChat()
        threading.Thread(target=v.teardown_monitor, daemon=True).start()
        w = webview.create_window('TeardownVC', html=HTML, js_api=Bridge(v), width=400, height=600)
        threading.Thread(target=gui_updater, args=(v, w), daemon=True).start()
        webview.start()
        
        v.running = False
        v.stop_audio_streams()
        if v.local["session"] > 0 and v.local["id"] != 0:
            v.client.publish(f"tdvc/{v.local['session']}/data/{v.local['id']}", payload=b"", retain=True)
        v.client.loop_stop()
        v.client.disconnect()

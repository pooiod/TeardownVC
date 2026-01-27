import os
import re
import json
import time
import threading
import subprocess
import webbrowser
import numpy as np
import pyaudio
import paho.mqtt.client as mqtt
import webview
import math
import sys

try:
    import psutil
except:
    psutil = None

SAVE_TAG = "steam-3653434619"
CLIENT_VERSION = 2
SAVE_PATH = os.path.expandvars(r'%LOCALAPPDATA%\Teardown\savegame.xml')
MQTT_BROKER = "broker.emqx.io"
MQTT_PORT = 8084
CHUNK = 512
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 8000
AUDIO_SNIP_SECONDS = 1
MAX_QUEUE_SECONDS = 4
STALE_TIMEOUT = 10
FADE_SECONDS = 1
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
        with open(login_vdf, 'r', encoding='utf-8') as f: content = f.read()
        users = re.findall(r'"PersonaName"\s+"([^"]+)"', content)
        if users: return users[-1]
    except: pass
    try: return os.getlogin()
    except: return "Player"

def force_reset_session():
    if not os.path.exists(SAVE_PATH): return False
    try:
        with open(SAVE_PATH, 'r+', encoding='utf-8') as f:
            content = f.read()
            m = re.search(fr'(<{SAVE_TAG}>(.*?)</{SAVE_TAG}>)', content, re.S)
            if m:
                full_tag, inner = m.group(1), m.group(2)
                new_inner = re.sub(r'<session\s+value="[^"]*"', '<session value="0"', inner)
                if RESET_SESSION_ON_START:
                    f.seek(0); f.write(content.replace(full_tag, f'<{SAVE_TAG}>{new_inner}</{SAVE_TAG}>', 1)); f.truncate()
            else: return True
    except: pass
    return True

class VoiceChat:
    def __init__(self):
        self.pa = pyaudio.PyAudio()
        self.client = mqtt.Client(transport="websockets")
        self.client.on_connect = self.on_mqtt_connect
        self.client.on_message = self.on_mqtt_message
        self.client.on_subscribe = self.on_mqtt_subscribe
        self.client.tls_set()
        try: self.mic_id = self.pa.get_default_input_device_info()['index']
        except: self.mic_id = 0
        try: self.spk_id = self.pa.get_default_output_device_info()['index']
        except: self.spk_id = 0
        self.restart_trigger = False
        self.running = True
        self.local = {"id": 0, "name": get_steam_username(), "x": 0, "y": 0, "z": 0, "dead": 1, "session": 0, "show_map": 0, "echo": 0, "global": 0}
        self.peers = {}
        self.levels = {}
        self.audio_queues = {}
        self.last_seen = {}
        self.play_started = {}
        self.settings = {'hear_self': False, 'mic_gain': 1, 'master_vol': 1}
        self.client.connect(MQTT_BROKER, MQTT_PORT)
        self.client.loop_start()
        self.last_pcm = {}
        self.fade_remaining = {}
        self.fade_total_samples = int(RATE * FADE_SECONDS)
        self.faded_out = {}

    def on_mqtt_connect(self, client, userdata, flags, rc):
        print(f"[MQTT] Connected with code {rc}")

    def on_mqtt_subscribe(self, client, userdata, mid, granted_qos):
        print(f"[MQTT] Subscribed to session room")

    def on_mqtt_message(self, c, u, m):
        try:
            topic_parts = m.topic.split("/")
            if "audio" in topic_parts:
                uid = str(topic_parts[-1])
                if uid == str(self.local["id"]): return
                if uid not in self.audio_queues:
                    self.audio_queues[uid] = bytearray()
                    self.play_started[uid] = False
                self.audio_queues[uid].extend(m.payload)
                try:
                    self.last_seen[uid] = time.time()
                except: pass
                try:
                    self.fade_remaining[uid] = 0
                    self.last_pcm.pop(uid, None)
                    self.faded_out[uid] = False
                except: pass
                if len(self.audio_queues[uid]) > (RATE * 2 * MAX_QUEUE_SECONDS):
                    self.audio_queues[uid] = self.audio_queues[uid][-(RATE * 2 * MAX_QUEUE_SECONDS):]
            elif "data" in topic_parts:
                if not m.payload:
                    uid = str(topic_parts[-1])
                    if uid in self.peers: del self.peers[uid]
                    try: del self.audio_queues[uid]
                    except: pass
                    try: del self.play_started[uid]
                    except: pass
                    try: del self.levels[uid]
                    except: pass
                    try: del self.last_seen[uid]
                    except: pass
                    return
                p = json.loads(m.payload)
                uid = str(p["id"])
                if uid == str(self.local["id"]): return
                self.peers[uid] = p
                try: self.last_seen[uid] = time.time()
                except: pass
        except Exception as e: print(f"[MQTT ERR] {e}")

    def audio_thread(self):
        while self.running:
            if self.local["session"] == 0:
                time.sleep(1); continue
            sin, sout = None, None
            try:
                print(f"[AUDIO] Reloading Hardware for Session {self.local['session']}")
                sin = self.pa.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, input_device_index=self.mic_id, frames_per_buffer=CHUNK)
                sout = self.pa.open(format=FORMAT, channels=2, rate=RATE, output=True, output_device_index=self.spk_id)
                self.restart_trigger = False
                last_echo, echo_buf = -1, np.zeros(1, dtype=np.int16)
                send_acc = bytearray()

                while self.running and not self.restart_trigger:
                    cur_echo = self.local.get("echo", 0)
                    if cur_echo != last_echo:
                        last_echo = cur_echo
                        echo_buf = np.zeros(int(RATE * (max(0, cur_echo)/1000)), dtype=np.int16)

                    in_np = np.zeros(CHUNK, dtype=np.int16)
                    try:
                        raw = sin.read(CHUNK, exception_on_overflow=False)
                        in_np = np.frombuffer(raw, dtype=np.int16)
                        if self.settings['mic_gain'] != 1:
                            in_np = (in_np.astype(np.float32) * self.settings['mic_gain']).clip(-32768, 32767).astype(np.int16)

                        self.levels[str(self.local["id"])] = np.abs(in_np).mean()
                    except Exception as e:
                        in_np = np.zeros(CHUNK, dtype=np.int16)
                        self.levels[str(self.local["id"])] = 0

                    ec = (echo_buf[:CHUNK] * 0.4).astype(np.int16) if len(echo_buf) >= CHUNK else 0
                    snd = np.add(in_np, ec, casting="unsafe")

                    if len(echo_buf) >= CHUNK:
                        echo_buf = np.roll(echo_buf, -CHUNK); echo_buf[-CHUNK:] = snd

                    if not self.local["dead"]:
                        send_acc.extend(snd.tobytes())
                        if len(send_acc) >= (RATE * 2 * AUDIO_SNIP_SECONDS):
                            self.client.publish(f"tdvc/{self.local['session']}/audio/{self.local['id']}", bytes(send_acc), qos=0)
                            send_acc = bytearray()
                    
                    mix = np.zeros(CHUNK * 2, dtype=np.float32)
                    byte_size = CHUNK * 2
                    
                    for uid, q in list(self.audio_queues.items()):
                        try:
                            p_meta = self.peers.get(uid, {})
                            vl, vr = (1, 1) if p_meta.get("global") else self.spatial_calc(p_meta)

                            one_sec_bytes = RATE * 2

                            if self.faded_out.get(uid, False) and len(q) == 0:
                                self.levels[uid] = 0
                                try: self.play_started[uid] = False
                                except: pass
                                continue

                            if not self.play_started.get(uid, False):
                                if len(q) >= one_sec_bytes:
                                    self.play_started[uid] = True
                                else:
                                    self.levels[uid] = 0
                                    continue

                            if len(q) >= byte_size:
                                chunk_bytes = q[:byte_size]
                                del q[:byte_size]
                                pcm = np.frombuffer(chunk_bytes, dtype=np.int16).astype(np.float32)
                                self.last_pcm[uid] = pcm.copy()
                                self.fade_remaining[uid] = 0
                                self.faded_out[uid] = False
                                self.levels[uid] = np.abs(pcm).mean() * ((vl + vr) / 2)
                                mix[0::2] += pcm * vl; mix[1::2] += pcm * vr
                                continue

                            available_bytes = len(q)
                            pcm_out = np.zeros(CHUNK, dtype=np.float32)
                            part_len = 0
                            if available_bytes > 0:
                                chunk_bytes = q[:available_bytes]
                                del q[:available_bytes]
                                part = np.frombuffer(chunk_bytes, dtype=np.int16).astype(np.float32)
                                part_len = len(part)
                                pcm_out[:part_len] = part

                            if self.fade_remaining.get(uid, 0) <= 0:
                                if uid in self.last_pcm:
                                    self.fade_remaining[uid] = self.fade_total_samples
                                else:
                                    self.levels[uid] = 0
                                    continue

                            rem = self.fade_remaining.get(uid, 0)
                            if rem <= 0:
                                self.levels[uid] = 0
                                continue

                            fade_needed = CHUNK - part_len
                            fade_samples = min(rem, fade_needed)
                            if fade_samples > 0 and uid in self.last_pcm:
                                last = self.last_pcm[uid]
                                lt = len(last)
                                idxs = np.arange(fade_samples)
                                multipliers = ((rem - idxs) / float(self.fade_total_samples)).astype(np.float32)
                                if fade_samples <= lt:
                                    source = last[-fade_samples:]
                                else:
                                    pad_len = fade_samples - lt
                                    source = np.concatenate((last, np.full(pad_len, last[-1], dtype=last.dtype)))
                                pcm_out[part_len:part_len+fade_samples] = source[:fade_samples] * multipliers

                                new_rem = rem - fade_samples
                                self.fade_remaining[uid] = new_rem
                                if new_rem <= 0:
                                    self.faded_out[uid] = True
                                    try: del self.last_pcm[uid]
                                    except: pass

                            self.levels[uid] = np.abs(pcm_out).mean() * ((vl + vr) / 2)
                            mix[0::2] += pcm_out * vl; mix[1::2] += pcm_out * vr
                        except: continue
                    
                    if self.settings['hear_self'] and not self.local["dead"]:
                        mix[0::2] += snd.astype(np.float32); mix[1::2] += snd.astype(np.float32)
                    
                    out_pcm = (mix * self.settings['master_vol']).clip(-32768, 32767).astype(np.int16)
                    try:
                        sout.write(out_pcm.tobytes())
                    except: pass

            except Exception as e:
                print(f"[AUDIO ERR] {e}")
                time.sleep(1)
            finally:
                if sin: 
                    try: sin.stop_stream(); sin.close()
                    except: pass
                if sout:
                    try: sout.stop_stream(); sout.close()
                    except: pass

    def spatial_calc(self, p):
        if not p: return 0.5, 0.5
        dx = p.get("x", 0) - self.local["x"]
        dy = p.get("y", 0) - self.local["y"]
        dz = p.get("z", 0) - self.local["z"]
        dist = math.sqrt(dx*dx + dy*dy + dz*dz)
        vol = max(0, 1 - (dist / 45))
        pan = np.clip(dx / -15, -0.8, 0.8)
        return vol * (1 - pan), vol * (1 + pan)

    def teardown_monitor(self):
        ls = -1
        while self.running:
            if os.path.exists(SAVE_PATH):
                try:
                    with open(SAVE_PATH, 'r', encoding='utf-8') as f: xml = f.read()
                    m = re.search(fr'<{SAVE_TAG}>(.*?)</{SAVE_TAG}>', xml, re.S)
                    inner = m.group(1) if m else ""
                    def g(k, default=0):
                        mm = re.search(rf'<{k}\s+value="([^"]*)"', inner)
                        return int(mm.group(1)) if mm else default
                    cs = g("session", 0)

                    if cs != ls:
                        if ls > 0:
                            self.client.publish(f"tdvc/{ls}/data/{self.local['id']}", payload=None, retain=True)
                            self.client.unsubscribe(f"tdvc/{ls}/#")
                        
                        if cs > 0:
                            print(f"[MONITOR] Joining Session {cs}")
                            self.client.subscribe(f"tdvc/{cs}/#")
                            self.peers.clear()
                            self.audio_queues.clear()
                            self.play_started.clear()
                        
                        ls = cs
                        self.restart_trigger = True

                    self.local.update({
                        "id": g("userid", 0), 
                        "x": g("pos_x", 0)/100, 
                        "y": g("pos_y", 0)/100, 
                        "z": g("pos_z", 0)/100, 
                        "dead": g("isdead", 1), 
                        "session": cs, 
                        "global": g("global", 0), 
                        "show_map": g("showmap", 0), 
                        "echo": g("echo", 0)
                    })

                    if cs > 0 and self.local["id"] != 0:
                         self.client.publish(f"tdvc/{cs}/data/{self.local['id']}", json.dumps(self.local), qos=0, retain=True)
                    try:
                        now = time.time()
                        stale = [uid for uid, ts in self.last_seen.items() if now - ts > STALE_TIMEOUT]
                        for uid in stale:
                            try: del self.peers[uid]
                            except: pass
                            try: del self.audio_queues[uid]
                            except: pass
                            try: del self.play_started[uid]
                            except: pass
                            try: del self.levels[uid]
                            except: pass
                            try: del self.last_seen[uid]
                            except: pass
                    except: pass
                except Exception as e:
                     print(f"[MONITOR ERR] {e}")
            time.sleep(0.3)

    def is_teardown_running(self):
        t = {"teardown.exe", "Teardown.exe"}
        if psutil:
            for p in psutil.process_iter(['name']):
                try:
                    if p.info['name'] in t: return True
                except: pass
            return False
        try:
            o = subprocess.check_output(['tasklist'], shell=True).decode(errors='ignore')
            return any(x.lower() in o.lower() for x in t)
        except: return False

    def launch_teardown(self):
        try:
            webbrowser.open("steam://rungameid/1167630"); return {'ok': True}
        except Exception as e: return {'error': str(e)}

class Bridge:
    def __init__(self, vc): self.vc = vc
    def init_devices(self):
        mics, spks = [], []
        for i in range(self.vc.pa.get_device_count()):
            try:
                d = self.vc.pa.get_device_info_by_index(i)
                if d['maxInputChannels'] > 0: mics.append({'id': i, 'name': d['name']})
                if d['maxOutputChannels'] > 0: spks.append({'id': i, 'name': d['name']})
            except: pass
        dm, ds = 0, 0
        try: dm = self.vc.pa.get_default_input_device_info()['index']
        except: pass
        try: ds = self.vc.pa.get_default_output_device_info()['index']
        except: pass
        return {'mics': mics, 'spks': spks, 'def_mic': dm, 'def_spk': ds}
    def set_io(self, mic, spk): self.vc.mic_id, self.vc.spk_id = mic, spk; self.vc.restart_trigger = True
    def update_settings(self, s): self.vc.settings = s
    def is_teardown_running(self): return {'running': self.vc.is_teardown_running()}
    def launch_teardown(self): return self.vc.launch_teardown()

def gui_updater(vc, win):
    while vc.running:
        try:
            plist = []
            plist.append({"id": vc.local["id"], "name": vc.local["name"], "vol": min(100, int(vc.levels.get(str(vc.local["id"]), 0)/10)), "status": "DEAD" if vc.local["dead"] else "LIVE", "local": True, "x": vc.local["x"], "y": vc.local["y"], "z": vc.local["z"], "echo": vc.local["echo"]})
            for uid, p in vc.peers.items():
                plist.append({"id": uid, "name": p.get("name", "Player"), "vol": min(100, int(vc.levels.get(uid, 0)/10)), "status": "DEAD" if p.get("dead") else "LIVE", "local": False, "x": p.get("x", 0), "y": p.get("y", 0), "z": p.get("z", 0), "echo": p.get("echo", 0)})
            win.evaluate_js(f"render('{json.dumps({'session': vc.local['session'], 'players': plist, 'show_map': vc.local['show_map']})}')")
        except: pass
        time.sleep(0.1)

if __name__ == "__main__":
    if force_reset_session():
        v = VoiceChat()
        threading.Thread(target=v.teardown_monitor, daemon=True).start()
        threading.Thread(target=v.audio_thread, daemon=True).start()
        w = webview.create_window('TeardownVC', html=HTML, js_api=Bridge(v), width=400, height=600)
        threading.Thread(target=gui_updater, args=(v, w), daemon=True).start()
        webview.start()
        if v.local["session"] > 0: v.client.publish(f"tdvc/{v.local['session']}/data/{v.local['id']}", payload=None, retain=True)
        v.running = False

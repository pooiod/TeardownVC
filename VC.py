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

SAVE_TAG = "steam-3653434619" # "local-teardownvc"
CLIENT_VERSION = 1
SAVE_PATH = os.path.expandvars(r'%LOCALAPPDATA%\Teardown\savegame.xml')
MQTT_BROKER = "broker.emqx.io"
MQTT_PORT = 8084
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1

HTML = """
<!DOCTYPE html>
<html>
<head>
    <style>
        body { background: #111; color: #eee; font-family: sans-serif; padding: 15px; user-select: none; overflow: hidden; }
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
        <div class="header-info">
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
            drawMap(data.players, data.show_map);
        }
        function drawMap(players, show) {
            const container = document.getElementById('map-container');
            if (!show || players.length === 0) { container.style.display = 'none'; return; }
            container.style.display = 'block';
            const canvas = document.getElementById('minimap');
            const ctx = canvas.getContext('2d');
            canvas.width = canvas.offsetWidth; canvas.height = canvas.offsetHeight;
            
            let minX = players[0].x, maxX = players[0].x, minZ = players[0].z, maxZ = players[0].z;
            players.forEach(p => {
                if (p.x < minX) minX = p.x; if (p.x > maxX) maxX = p.x;
                if (p.z < minZ) minZ = p.z; if (p.z > maxZ) maxZ = p.z;
            });

            const worldSize = Math.max(20, maxX - minX, maxZ - minZ) * 1.2;
            const zoom = canvas.width / worldSize;
            const centerX = (minX + maxX) / 2;
            const centerZ = (minZ + maxZ) / 2;

            ctx.clearRect(0, 0, canvas.width, canvas.height);
            players.forEach(p => {
                const cx = (p.x - centerX) * zoom + canvas.width / 2;
                const cz = (p.z - centerZ) * zoom + canvas.height / 2;
                ctx.beginPath(); ctx.arc(cx, cz, 5, 0, 2 * Math.PI);
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
    if not os.path.exists(SAVE_PATH):
        return False
    try:
        with open(SAVE_PATH, 'r+', encoding='utf-8') as f:
            content = f.read()
            m = re.search(fr'(<{SAVE_TAG}>(.*?)</{SAVE_TAG}>)', content, re.S)
            if m:
                full_tag = m.group(1)
                inner = m.group(2)
                vm = re.search(r'<version\s+value="([^"]*)"', inner)
                if vm:
                    try:
                        sv = int(vm.group(1))
                    except:
                        sv = 0
                    if sv > CLIENT_VERSION:
                        html = f"<body style='background:black;'><h2 style='color:#fff;background:#111;padding:12px'>Client out of date</h2><p style='color:#ddd'>Your TDVC client is out of date. Please update to version {sv}. <a style='color:lightblue;' href='https://github.com/pooiod/TeardownVC/releases' target='_blank'>github.com/pooiod/TeardownVC/releases</a></p>"
                        webview.create_window('Out of Date', html=html, width=520, height=200)
                        webview.start()
                        sys.exit(0)
                if re.search(r'<session\s+value="[^"]*"', inner):
                    new_inner = re.sub(r'<session\s+value="[^"]*"', '<session value="0"', inner, count=1)
                else:
                    new_inner = inner + '\n\t\t\t<session value="0"/>'
                new_full_tag = f'<{SAVE_TAG}>{new_inner}</{SAVE_TAG}>'
                new_content = content.replace(full_tag, new_full_tag, 1)
                f.seek(0); f.write(new_content); f.truncate()
            else:
                if re.search(r'session value="\d+"', content):
                    new_content = re.sub(r'session value="\d+"', 'session value="0"', content, 1)
                    f.seek(0); f.write(new_content); f.truncate()
                else:
                    return True
    except Exception as e:
        print(f"[WARN] Failed to reset session file: {e}")
    return True

class VoiceChat:
    def __init__(self):
        self.pa = pyaudio.PyAudio()
        self.client = mqtt.Client(transport="websockets"); self.client.tls_set()
        try: self.mic_id = self.pa.get_default_input_device_info()['index']
        except: self.mic_id = 0
        try: self.spk_id = self.pa.get_default_output_device_info()['index']
        except: self.spk_id = 0
        self.restart_trigger = False; self.running = True
        self.local = {"id": 0, "name": get_steam_username(), "x": 0, "y": 0, "z": 0, "dead": 1, "session": 0, "show_map": 0, "echo": 0}
        self.peers, self.levels = {}, {}
        self.settings = {'hear_self': False, 'mic_gain': 1.0, 'master_vol': 1.0}
        self.client.on_message = self.on_mqtt; self.client.connect(MQTT_BROKER, MQTT_PORT); self.client.loop_start()

    def on_mqtt(self, c, u, m):
        try:
            p = json.loads(m.payload)
            if p["id"] == self.local["id"]: return
            if p["id"] not in self.peers: self.peers[p["id"]] = {"buf": [], "name": p.get("name", "Unknown")}
            self.peers[p["id"]]["buf"].append(p); self.peers[p["id"]]["meta"] = p
            if len(self.peers[p["id"]]["buf"]) > 8: self.peers[p["id"]]["buf"].pop(0)
        except: pass

    def is_teardown_running(self):
        target_names = {"teardown.exe", "Teardown.exe"}
        if psutil:
            for p in psutil.process_iter(['name']):
                try:
                    if p.info['name'] in target_names: return True
                except: pass
            return False
        else:
            try:
                out = subprocess.check_output(['tasklist'], shell=True).decode(errors='ignore')
                for line in out.splitlines():
                    for tn in target_names:
                        if tn.lower() in line.lower(): return True
            except: pass
            return False

    def launch_teardown(self):
        if self.is_teardown_running(): return {'ok': True}
        try:
            steam_path = None
            try:
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
                steam_path = winreg.QueryValueEx(key, "SteamPath")[0]
            except: steam_path = None
            if steam_path:
                exe_path = os.path.join(steam_path, "steamapps", "common", "Teardown", "Teardown.exe")
                if os.path.exists(exe_path):
                    subprocess.Popen([exe_path], shell=False)
                    return {'ok': True}
            try:
                steam_uri = "steam://rungameid/1167630"
                if sys.platform.startswith("win"):
                    os.startfile(steam_uri)
                else:
                    webbrowser.open(steam_uri)
                return {'ok': True}
            except Exception as e:
                return {'error': str(e)}
        except Exception as e:
            return {'error': str(e)}

    def audio_thread(self):
        while self.running:
            if self.local["session"] == 0: time.sleep(1); continue
            stream_in, stream_out = None, None
            try:
                rate = int(self.pa.get_device_info_by_index(self.mic_id)['defaultSampleRate'])
                last_echo_ms = -1; echo_buf = np.zeros(1, dtype=np.int16)
                stream_in = self.pa.open(format=FORMAT, channels=CHANNELS, rate=rate, input=True, input_device_index=self.mic_id, frames_per_buffer=CHUNK)
                stream_out = self.pa.open(format=FORMAT, channels=2, rate=rate, output=True, output_device_index=self.spk_id)
                self.restart_trigger = False
                while self.running and not self.restart_trigger:
                    current_echo = self.local.get("echo", 0)
                    if current_echo < 30: current_echo = 0
                    if current_echo != last_echo_ms:
                        last_echo_ms = current_echo
                        echo_delay_s = max(0, last_echo_ms / 1000.0)
                        echo_buf = np.zeros(int(rate * echo_delay_s), dtype=np.int16)
                    raw = stream_in.read(CHUNK, exception_on_overflow=False)
                    in_np = (np.frombuffer(raw, dtype=np.int16) * self.settings['mic_gain']).astype(np.int16)
                    self.levels[self.local["id"]] = np.abs(in_np).mean()
                    ec = (echo_buf[:CHUNK] * 0.3).astype(np.int16) if len(echo_buf) > 0 else 0
                    send_audio = np.add(in_np, ec, casting="unsafe")
                    if len(echo_buf) > 0:
                        echo_buf = np.roll(echo_buf, -CHUNK)
                        echo_buf[-CHUNK:] = send_audio
                    if not self.local["dead"]:
                        pl = {**self.local, "audio": send_audio.tobytes().hex()}
                        self.client.publish(f"p7vc/{self.local['session']}", json.dumps(pl))
                    mix = np.zeros(CHUNK * 2, dtype=np.int16)
                    for uid, p_data in list(self.peers.items()):
                        if not p_data["buf"]: self.levels[uid] = 0; continue
                        pkt = p_data["buf"].pop(0)
                        if pkt.get("dead"): continue
                        pcm = np.frombuffer(bytes.fromhex(pkt["audio"]), dtype=np.int16)
                        vl, vr = (1.0, 1.0) if pkt.get("global") else self.spatial_calc(pkt)
                        self.levels[uid] = np.abs(pcm).mean() * ((vl + vr) / 2)
                        stereo = np.empty((CHUNK * 2,), dtype=np.int16)
                        stereo[0::2], stereo[1::2] = (pcm * vl).astype(np.int16), (pcm * vr).astype(np.int16)
                        mix = np.add(mix, stereo, casting="unsafe")
                    if self.settings['hear_self'] and not self.local["dead"]:
                        stereo_self = np.empty((CHUNK * 2,), dtype=np.int16)
                        stereo_self[0::2], stereo_self[1::2] = send_audio, send_audio
                        mix = np.add(mix, stereo_self, casting="unsafe")
                    final_mix = (mix * self.settings['master_vol']).astype(np.int16)
                    stream_out.write(final_mix.tobytes())
            except Exception as e:
                print(f"[ERROR] Audio Engine: {e}")
                time.sleep(2)
            finally:
                if stream_in:
                    try: stream_in.close()
                    except: pass
                if stream_out:
                    try: stream_out.close()
                    except: pass

    def spatial_calc(self, pkt):
        dx, dz = pkt["x"] - self.local["x"], pkt["z"] - self.local["z"]
        dist = math.sqrt(dx*dx + dz*dz); vol = max(0, 1.0 - (dist / 45.0)); pan = np.clip(dx / 15.0, -1.0, 1.0)
        return vol * (1.0 - pan) * 0.5, vol * (1.0 + pan) * 0.5

    def teardown_monitor(self):
        last_s = -1
        while self.running:
            if os.path.exists(SAVE_PATH):
                try:
                    with open(SAVE_PATH, 'r', encoding='utf-8') as f:
                        xml = f.read()
                    m = re.search(fr'<{SAVE_TAG}>(.*?)</{SAVE_TAG}>', xml, re.S)
                    inner = m.group(1) if m else ""
                    vm = re.search(r'<version\s+value="([^"]*)"', inner)
                    if vm:
                        try:
                            sv = int(vm.group(1))
                        except:
                            sv = 0
                        if sv > CLIENT_VERSION:
                            html = f"<h2 style='color:#fff;background:#111;padding:12px'>Client out of date</h2><p style='color:#ddd'>Your game save requires a newer client (save version {sv}). Please update the client: <a href='https://github.com/pooiod/TeardownVC/releases' target='_blank'>Releases</a></p>"
                            webview.create_window('Out of Date', html=html, width=520, height=140)
                            webview.start()
                            self.running = False
                            break
                    def g(k, default=0):
                        try:
                            if inner:
                                mm = re.search(rf'<{k}\s+value="([^"]*)"', inner)
                                if mm:
                                    try:
                                        return int(mm.group(1))
                                    except:
                                        return default
                        except:
                            pass
                        return default
                    current_s = g("session", 0)
                    if current_s != last_s:
                        if last_s != 0: self.client.unsubscribe(f"p7vc/{last_s}")
                        if current_s != 0: self.client.subscribe(f"p7vc/{current_s}")
                        self.peers.clear(); self.levels.clear(); last_s = current_s; self.restart_trigger = True
                    echo_val = g("echo", 0)
                    if echo_val < 30: echo_val = 0
                    self.local.update({"id": g("userid", 0), "x": g("pos_x", 0)/100, "y": g("pos_y", 0)/100, "z": g("pos_z", 0)/100, "dead": g("isdead", 1), "session": current_s, "global": g("global", 0), "show_map": g("showmap", 0), "echo": echo_val})
                except: pass
            time.sleep(0.5)

class Bridge:
    def __init__(self, vc): self.vc = vc
    def init_devices(self):
        mics, spks, def_mic, def_spk = [], [], None, None
        try: def_mic = self.vc.pa.get_default_input_device_info()['index']
        except: pass
        try: def_spk = self.vc.pa.get_default_output_device_info()['index']
        except: pass
        for i in range(self.vc.pa.get_device_count()):
            try:
                d = self.vc.pa.get_device_info_by_index(i)
                if d['maxInputChannels'] > 0:
                    try:
                        self.vc.pa.open(format=FORMAT, channels=1, rate=int(d['defaultSampleRate']), input=True, input_device_index=i, frames_per_buffer=1024).close()
                        mics.append({'id': i, 'name': d['name']})
                    except: continue
                if d['maxOutputChannels'] > 0: spks.append({'id': i, 'name': d['name']})
            except: pass
        return {'mics': mics, 'spks': spks, 'def_mic': def_mic, 'def_spk': def_spk}
    def set_io(self, mic, spk): self.vc.mic_id, self.vc.spk_id = mic, spk; self.vc.restart_trigger = True
    def update_settings(self, s): self.vc.settings = s
    def is_teardown_running(self): return {'running': self.vc.is_teardown_running()}
    def launch_teardown(self): return self.vc.launch_teardown()

def gui_updater(vc, win):
    def snap_echo(e):
        try:
            if e < 30: return 0
        except: pass
        return e
    while vc.running:
        try:
            player_list = []
            player_list.append({"id": vc.local["id"], "name": vc.local["name"], "vol": min(100, int(vc.levels.get(vc.local["id"], 0) / 10)), "status": "DEAD" if vc.local["dead"] else "LIVE", "local": True, "x": vc.local["x"], "z": vc.local["z"], "echo": snap_echo(vc.local.get("echo", 0))})
            for uid, d in vc.peers.items():
                meta = d.get("meta", {})
                echo_val = snap_echo(meta.get("echo", 0))
                player_list.append({"id": uid, "name": d["name"], "vol": min(100, int(vc.levels.get(uid, 0) / 10)), "status": "DEAD" if meta.get("dead") else "LIVE", "local": False, "x": meta.get("x",0), "z": meta.get("z",0), "echo": echo_val})
            payload = {"session": vc.local["session"], "players": player_list, "show_map": vc.local["show_map"]}
            win.evaluate_js(f"render('{json.dumps(payload)}')")
        except: pass
        time.sleep(0.1)

if __name__ == "__main__":
    if not force_reset_session():
        webview.create_window('Error', html="<h1>Teardown save file not found. Please install and run Teardown first.</h1>", width=400, height=100)
        webview.start()
    else:
        v = VoiceChat()
        threading.Thread(target=v.teardown_monitor, daemon=True).start()
        threading.Thread(target=v.audio_thread, daemon=True).start()
        w = webview.create_window('TeardownVC', html=HTML, js_api=Bridge(v), width=400, height=600, resizable=True, on_top=True)
        try:
            w.set_always_on_top(True)
        except: pass
        threading.Thread(target=gui_updater, args=(v, w), daemon=True).start()
        webview.start()
        v.running = False

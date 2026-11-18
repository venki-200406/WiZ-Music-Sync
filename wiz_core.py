r"""
WiZ Music Sync: engine (no UI).

  apps -> VB-Cable ("CABLE Input") -> this engine -> beat detection -> UDP -> WiZ bulb
                                                 \-> delay line ----------> headphones / speakers

The bulb reacts late (Wi-Fi + firmware), so the AUDIO is held back by the same amount and the
beat is heard when the light changes. A negative delay holds back the LIGHT instead
(for Bluetooth headphones that lag more than the bulb).
"""
import base64
import colorsys
import hashlib
import hmac
import json
import os
import queue
import socket
import threading
import time
from collections import deque

import numpy as np
import sounddevice as sd

WIZ_PORT = 38899


# ============================================================================ WiZ bulb
def local_ipv4s():
    """This PC's IPv4 addresses (skips loopback and self-assigned 169.254.x.x)."""
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    for probe in ("8.8.8.8", "10.255.255.255", "172.20.10.1", "192.168.1.1"):
        try:                                      # route lookup only: no packet is sent
            t = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            t.connect((probe, 9))
            ips.add(t.getsockname()[0])
            t.close()
        except OSError:
            pass
    return sorted(ip for ip in ips if not ip.startswith(("127.", "169.254.", "0.")))


def discover(timeout=2.5, hints=()):
    """Find WiZ bulbs; returns {ip: reply_dict}.

    Uses three methods together, because broadcast alone often fails on Windows
    (hotspots, VPN / Hyper-V / WSL adapters, firewall on 'Public' networks):
      1. broadcast to 255.255.255.255 and to each adapter's subnet broadcast
      2. a direct message to every address in each adapter's /24 subnet
         (direct replies get through the firewall like normal replies)
      3. a direct message to any IP we already know (the saved bulb)
    """
    msg = json.dumps({"method": "getPilot", "params": {}}).encode()
    local = local_ipv4s()
    targets = []
    for ip in local:
        base = ip.rsplit(".", 1)[0]
        targets += [f"{base}.{h}" for h in range(1, 255) if f"{base}.{h}" != ip]
    targets = list(dict.fromkeys(list(hints) + targets))
    bcasts = ["255.255.255.255"] + [ip.rsplit(".", 1)[0] + ".255" for ip in local]
    if any(ip.startswith("172.20.10.") for ip in local):
        bcasts.append("172.20.10.15")            # iPhone hotspot is a /28 network

    socks = []
    for bind_ip in [""] + local:                 # one socket per adapter so broadcasts leave on each
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.bind((bind_ip, 0))
            s.setblocking(False)
            socks.append(s)
        except OSError:
            pass
    if not socks:
        return {}

    found = {}
    end = time.time() + timeout
    rounds = 0
    while time.time() < end:
        if rounds < 3:                           # send three rounds (UDP can drop packets)
            for s in socks:
                for b in bcasts:
                    try:
                        s.sendto(msg, (b, WIZ_PORT))
                    except OSError:
                        pass
            for i, ip in enumerate(targets):
                try:
                    socks[0].sendto(msg, (ip, WIZ_PORT))
                except OSError:
                    pass
                if i % 64 == 63:
                    time.sleep(0.005)             # don't flood weak routers
            rounds += 1
        t_round = time.time() + 0.6
        while time.time() < min(t_round, end):
            got = False
            for s in socks:
                try:
                    data, addr = s.recvfrom(2048)
                except (BlockingIOError, OSError):
                    continue
                got = True
                try:
                    reply = json.loads(data)
                except ValueError:
                    continue
                if reply.get("method") == "getPilot" and addr[0] not in local:
                    found[addr[0]] = reply
            if not got:
                time.sleep(0.01)
    for s in socks:
        s.close()
    return found


def parse_key(text):
    """Accept the 32-hex udp_signing_key, a path to the WiZ home JSON export, or pasted JSON."""
    text = (text or "").strip().strip('"')
    if not text:
        return None
    blob = None
    if os.path.isfile(text):
        with open(text, encoding="utf-8") as f:
            blob = json.load(f)
    elif text.startswith("{"):
        blob = json.loads(text)
    if blob is not None:
        def find(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    if k == "udp_signing_key":
                        return v
                    r = find(v)
                    if r:
                        return r
            elif isinstance(o, list):
                for v in o:
                    r = find(v)
                    if r:
                        return r
        text = find(blob)
        if not text:
            raise ValueError("No udp_signing_key found in that JSON.")
    try:
        return bytes.fromhex(text)
    except ValueError:
        raise ValueError("The key must be 32 hex characters (or the exported home JSON).")


def build_packet(params, key=None, sort_keys=False):
    if key is None:
        return json.dumps({"method": "setPilot", "params": params}, separators=(",", ":")).encode()
    params = dict(params, sigTs=int(time.time()))
    body = json.dumps(params, separators=(",", ":"), sort_keys=sort_keys)
    sig = base64.b64encode(hmac.new(key, body.encode(), hashlib.sha256).digest()).decode()
    return ('{"method":"setPilot","env":"pro","params":%s,"hmac":"%s"}' % (body, sig)).encode()


ERROR_HINTS = {
    -32602: "Bulb refused the command. Add your signing key, or turn on 'Allow all controls' "
            "in the WiZ app (Settings > Security > Allow local communication).",
    -32605: "Signature rejected. Check the key, and sync the Windows clock.",
}


class WizSender:
    """Fire-and-forget UDP on its own thread; a listener thread records bulb errors."""

    def __init__(self):
        self.ips, self.key, self.sort_keys = [], None, False
        self.last_error = None
        self.sent = 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, 0xB8)
        except OSError:
            pass
        self.sock.bind(("", 0))
        self.q = queue.SimpleQueue()
        threading.Thread(target=self._run, daemon=True).start()
        threading.Thread(target=self._listen, daemon=True).start()

    def configure(self, ips, key=None, sort_keys=False):
        self.ips, self.key, self.sort_keys = list(ips), key, sort_keys
        self.last_error = None

    def send(self, params):
        self.q.put(dict(params))

    def _run(self):
        while True:
            params = self.q.get()
            try:                                   # coalesce: only the newest command matters
                while True:
                    params = self.q.get_nowait()
            except queue.Empty:
                pass
            pkt = build_packet(params, self.key, self.sort_keys)
            for ip in self.ips:
                try:
                    self.sock.sendto(pkt, (ip, WIZ_PORT))
                    self.sent += 1
                except OSError as e:
                    self.last_error = f"Network error: {e}"

    def _listen(self):
        while True:
            try:
                data, _ = self.sock.recvfrom(2048)
                err = json.loads(data).get("error")
            except (OSError, ValueError, AttributeError):
                time.sleep(0.2)
                continue
            if err:
                code = err.get("code")
                self.last_error = ERROR_HINTS.get(code, f"Bulb error {code}: {err.get('message')}")


def test_bulb(ip, key=None, progress=None):
    """Flash red, green, blue. Returns (ok, sort_keys, message)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(2)
    last = ""
    for sort_keys in ([False, True] if key else [False]):
        ok_all = True
        for name, rgb in (("red", (255, 0, 0)), ("green", (0, 255, 0)), ("blue", (0, 0, 255))):
            if progress:
                progress(f"Sending {name}...")
            p = {"r": rgb[0], "g": rgb[1], "b": rgb[2], "dimming": 100}
            try:
                s.sendto(build_packet(p, key, sort_keys), (ip, WIZ_PORT))
                reply = s.recvfrom(2048)[0].decode(errors="ignore")
            except socket.timeout:
                s.close()
                return False, False, "No reply from the bulb. Check the IP and that you're on the same Wi-Fi."
            except OSError as e:
                s.close()
                return False, False, f"Network error: {e}"
            if '"success":true' not in reply.replace(" ", ""):
                ok_all = False
                try:
                    code = json.loads(reply)["error"]["code"]
                    last = ERROR_HINTS.get(code, reply[:120])
                except (ValueError, KeyError, TypeError):
                    last = reply[:120]
                break
            time.sleep(0.6)
        if ok_all:
            s.sendto(build_packet({"temp": 2700, "dimming": 60}, key, sort_keys), (ip, WIZ_PORT))
            s.close()
            return True, sort_keys, "Bulb works! It flashed red, green and blue."
    s.close()
    return False, False, last or "The bulb refused the commands."


# ============================================================================ audio devices
API_ORDER = ["Windows WASAPI", "MME", "Windows DirectSound"]
SKIP_OUT = ("cable", "vb-audio", "sound mapper", "primary sound", "hands-free")


def refresh_devices():
    """Re-scan audio devices (PortAudio caches the list at start-up)."""
    try:
        sd._terminate()
        sd._initialize()
    except Exception:
        pass


def _apis():
    """Host APIs ordered by preference: [(index, name)]."""
    apis = [(i, a["name"]) for i, a in enumerate(sd.query_hostapis())]
    rank = {n: k for k, n in enumerate(API_ORDER)}
    return sorted(apis, key=lambda x: rank.get(x[1], 99))


def _same(a, b):
    a, b = a.lower().strip(), b.lower().strip()
    n = min(len(a), len(b), 31)                     # MME truncates names to 31 chars
    return n >= 6 and a[:n] == b[:n]


def list_outputs():
    """Output device names from the best host API (excluding the virtual cable)."""
    devs = sd.query_devices()
    api_idx = _apis()[0][0]
    names = []
    for d in devs:
        if d["hostapi"] == api_idx and d["max_output_channels"] > 0:
            if not any(k in d["name"].lower() for k in SKIP_OUT) and d["name"] not in names:
                names.append(d["name"])
    return names


def list_inputs():
    devs = sd.query_devices()
    api_idx = _apis()[0][0]
    return [d["name"] for d in devs if d["hostapi"] == api_idx and d["max_input_channels"] > 0]


def cable_status():
    """(cable_installed, cable_is_default_output)."""
    names = [d["name"] for d in sd.query_devices()]
    installed = any(n.startswith("CABLE Input") for n in names)
    try:
        default_out = sd.query_devices(kind="output")["name"]
    except Exception:
        default_out = ""
    return installed, default_out.startswith("CABLE Input")


def _candidates(out_name, in_name=None):
    """[(in_idx or None, out_idx, api_name)] in preference order, matched across host APIs."""
    devs = sd.query_devices()
    res = []
    for api_idx, api_name in _apis():
        outs = [i for i, d in enumerate(devs)
                if d["hostapi"] == api_idx and d["max_output_channels"] > 0 and _same(d["name"], out_name)]
        if not outs:
            continue
        ins = [i for i, d in enumerate(devs) if d["hostapi"] == api_idx and d["max_input_channels"] > 0
               and (_same(d["name"], in_name) if in_name else d["name"].startswith("CABLE Output"))]
        res.append((ins[0] if ins else None, outs[0], api_name))
    return res


# ============================================================================ DSP
class DelayLine:
    def __init__(self, max_samples, channels):
        self.n = int(max_samples)
        self.buf = np.zeros((self.n, channels), dtype=np.float32)
        self.w, self.delay = 0, 0

    def process(self, x):
        k = len(x)
        idx = np.arange(k)
        self.buf[(self.w + idx) % self.n] = x
        out = self.buf[(self.w - self.delay + idx) % self.n]
        self.w = (self.w + k) % self.n
        return out


class BeatDetector:
    """Bass spectral-flux onsets (sliding 2048-pt FFT, hop = block) + loudness AGC.
    A hit is reported one block later so its full punch is measured (engine compensates)."""

    def __init__(self, sr, block, sensitivity=1.5, min_gap=0.14, lo_hz=30, hi_hz=200):
        self.nfft = max(2048, block)
        self.ring = np.zeros(self.nfft, dtype=np.float32)
        self.window = np.hanning(self.nfft).astype(np.float32)
        freqs = np.fft.rfftfreq(self.nfft, 1 / sr)
        self.band = (freqs >= lo_hz) & (freqs <= hi_hz)
        self.prev = None
        self.hist = deque(maxlen=max(8, int(1.2 * sr / block)))
        self.k, self.min_gap = sensitivity, min_gap
        self.last_beat, self.peak, self.pending = 0.0, 1e-4, None

    def process(self, mono, now):
        k = len(mono)
        self.ring = np.roll(self.ring, -k)
        self.ring[-k:] = mono
        spec = np.abs(np.fft.rfft(self.ring * self.window))[self.band]
        logspec = np.log1p(spec * 100.0)
        if self.prev is None:
            self.prev = logspec
        flux = float(np.maximum(logspec - self.prev, 0).sum())
        self.prev = logspec

        rms = float(np.sqrt(np.mean(mono * mono)) + 1e-9)
        self.peak = max(rms, self.peak * 0.9995)
        level = min(1.0, rms / self.peak)
        punch = float(np.sqrt(np.sum(spec * spec)))

        out_beat, out_strength = False, 0.0
        if self.pending is not None:
            out_beat, out_strength = True, max(self.pending, punch)
            self.pending = None
        if len(self.hist) >= 8:
            h = np.fromiter(self.hist, dtype=np.float32)
            if (flux > h.mean() + self.k * h.std() and flux > 0.5 and rms > 1e-3
                    and now - self.last_beat >= self.min_gap):
                self.pending, self.last_beat = punch, now
        self.hist.append(flux)
        return out_beat, out_strength, level


PALETTES = {
    "Party":   [0.92, 0.62, 0.00, 0.75, 0.50, 0.08, 0.83, 0.33],
    "Rainbow": [0.00, 0.08, 0.15, 0.33, 0.50, 0.62, 0.75, 0.88],
    "Fire":    [0.00, 0.06, 0.97, 0.10, 0.02, 0.92],
    "Ocean":   [0.50, 0.62, 0.45, 0.70, 0.55, 0.78],
    "Neon":    [0.83, 0.50, 0.92, 0.33, 0.75, 0.15],
}


class LightBrain:
    """Beat strength -> brightness, colour change and glow length.
    Strong hits: full brightness, instant colour change (biggest skip colours), long glow.
    Soft hits: dimmer, same colour with shimmer, short blip. Floor follows song energy."""

    def __init__(self, emit, style):
        self.emit = emit
        self.beats = deque(maxlen=40)
        self.energy = self.env = 0.0
        self.tau = 0.2
        self.idx, self.budget, self.last_change = 0, 0.0, 0.0
        self.rng = np.random.default_rng()
        self.last_send, self.last_dim = 0.0, -1
        self.score = 0.0
        self.rgb = (0, 0, 0)
        self.dim = 0
        self.apply_style(style)
        self.hue, self.sat = self.palette[0], 1.0

    def apply_style(self, st):
        self.palette = PALETTES.get(st.get("palette", "Party"), PALETTES["Party"])
        self.idx %= len(self.palette)
        self.contrast = float(st.get("contrast", 1.4))
        self.color_speed = float(st.get("color_speed", 1.0))
        self.lo = max(10, int(st.get("min_bright", 10)))
        self.hi = max(self.lo, min(100, int(st.get("max_bright", 100))))
        self.min_dt = 1.0 / float(st.get("max_rate", 14))

    def _score(self, flux, level):
        self.beats.append(flux)
        if len(self.beats) < 6:
            rank = 0.6
        else:
            rank = float((np.fromiter(self.beats, dtype=np.float32) < flux).mean())
        return min(1.0, max(0.0, 0.75 * rank + 0.25 * level)) ** self.contrast

    def _pick_hue(self, score, now):
        n, step = len(self.palette), 0
        if score >= 0.9:
            step = 2 + (score >= 0.97)
        elif score >= 0.65:
            step = 1
        else:
            self.budget += (0.25 + score) * self.color_speed
            if self.budget >= 1.0 or now - self.last_change > 4.0:
                step = 1
        if step:
            self.idx = (self.idx + step) % n
            self.budget, self.last_change = 0.0, now
        jitter = 0.0 if step else self.rng.uniform(-0.025, 0.025)
        self.hue = (self.palette[self.idx] + jitter) % 1.0

    def update(self, beat, strength, level, now, dt):
        self.energy += (level - self.energy) * min(1.0, dt / 2.0)
        floor = 0.08 + 0.32 * self.energy ** 1.5
        if beat:
            score = self._score(strength, level)
            self.score = score
            self._pick_hue(score, now)
            self.sat = 0.88 + 0.12 * score
            self.env = max(self.env, 0.30 + 0.70 * score)
            self.tau = 0.10 + 0.40 * score
        else:
            self.env = floor + (self.env - floor) * np.exp(-dt / self.tau)
        dim = int(round(self.lo + (self.hi - self.lo) * min(1.0, self.env)))
        if beat or (now - self.last_send >= self.min_dt and abs(dim - self.last_dim) >= 5):
            r, g, b = colorsys.hsv_to_rgb(self.hue, self.sat, 1.0)
            self.rgb = (int(r * 255), int(g * 255), int(b * 255))
            self.dim = dim
            self.emit({"r": self.rgb[0], "g": self.rgb[1], "b": self.rgb[2], "dimming": dim})
            self.last_send, self.last_dim = now, dim


# ============================================================================ engine
class Engine:
    """Owns the audio stream. mode: None | 'live' | 'calibrate'."""

    BLOCK = 512

    def __init__(self):
        self.sender = WizSender()
        self.stream = None
        self.mode = None
        self.delay_ms = 120.0           # >0: audio waits; <0: light waits
        self.style = {"palette": "Party", "contrast": 1.4, "color_speed": 1.0,
                      "min_bright": 10, "max_bright": 100, "sensitivity": 1.5, "max_rate": 14}
        self.brain = None
        self.detector = None
        self.status = {"beats": 0, "level": 0.0, "api": "", "sr": 0, "latency_ms": 0,
                       "flash": 0.0, "xruns": 0}
        self._light_q = deque()
        self._lock = threading.Lock()

    # ---- bulb
    def set_bulb(self, ip, key=None, sort_keys=False):
        self.sender.configure([ip] if ip else [], key, sort_keys)

    def bulb_error(self):
        return self.sender.last_error

    def restore_bulb(self):
        if self.sender.ips:
            self.sender.send({"temp": 2700, "dimming": 60})

    # ---- style
    def set_style(self, **kw):
        self.style.update(kw)
        if self.brain:
            self.brain.apply_style(self.style)
        if self.detector:
            self.detector.k = float(self.style["sensitivity"])

    # ---- light scheduling (lets a negative delay hold back the light)
    def _emit(self, params, now):
        lag = max(0.0, -self.delay_ms) / 1000.0
        if lag <= 0:
            self.sender.send(params)
        else:
            self._light_q.append((now + lag, params))

    def _flush_lights(self, now):
        q = self._light_q
        while q and q[0][0] <= now:
            self.sender.send(q.popleft()[1])

    # ---- streams
    def start(self, mode, out_name, in_name=None):
        self.stop(restore=False)
        cands = _candidates(out_name, in_name)
        if not cands:
            raise RuntimeError(f"Output device '{out_name}' not found. Click Refresh.")
        if mode == "live" and all(c[0] is None for c in cands):
            raise RuntimeError("VB-Cable ('CABLE Output') not found. Install VB-Cable and restart Windows.")
        errors = []
        devs = sd.query_devices()
        for in_idx, out_idx, api in cands:
            if mode == "live" and in_idx is None:
                continue
            rates = []
            for r in (devs[out_idx]["default_samplerate"],
                      devs[in_idx]["default_samplerate"] if in_idx is not None else None, 48000, 44100):
                if r and int(r) not in rates:
                    rates.append(int(r))
            for sr in rates:
                try:
                    stream = self._open(mode, in_idx, out_idx, sr)
                    stream.start()
                except Exception as e:  # noqa: BLE001 - PortAudio raises many types
                    errors.append(f"{api} @ {sr} Hz: {e}")
                    continue
                self.stream, self.mode = stream, mode
                lat = stream.latency
                lat = lat[-1] if isinstance(lat, (tuple, list)) else lat
                self.status.update(api=api, sr=sr, latency_ms=int(lat * 1000))
                return
        raise RuntimeError("Could not open audio.\n" + "\n".join(errors[-3:]))

    def _open(self, mode, in_idx, out_idx, sr):
        devs = sd.query_devices()
        ch_out = min(2, devs[out_idx]["max_output_channels"])
        block = self.BLOCK
        dt = block / sr
        dl = DelayLine(sr * 3, ch_out)
        clock = {"t": 0.0, "next_click": 0.5, "dim_at": None}
        self.status["beats"] = 0
        self._light_q.clear()
        extra = block if mode == "live" else 0       # detector reports hits 1 block late

        def push_audio(src, out):
            dl.delay = int(max(0.0, self.delay_ms) * sr / 1000.0) + extra
            out[:] = dl.process(src)

        if mode == "live":
            ch_in = min(2, devs[in_idx]["max_input_channels"])
            self.detector = BeatDetector(sr, block, float(self.style["sensitivity"]))
            self.brain = LightBrain(lambda p: self._emit(p, clock["t"]), self.style)
            det, brain = self.detector, self.brain

            def cb(indata, outdata, frames, t, status):
                if status:
                    self.status["xruns"] += 1
                now = clock["t"]
                x = indata[:, :ch_in]
                beat, strength, level = det.process(x.mean(axis=1), now)
                brain.update(beat, strength, level, now, dt)
                self._flush_lights(now)
                if beat:
                    self.status["beats"] += 1
                self.status["level"] = level
                if ch_in == ch_out:
                    src = x
                elif ch_out == 1:
                    src = x.mean(axis=1, keepdims=True)
                else:
                    src = np.repeat(x[:, :1], ch_out, axis=1)
                push_audio(src, outdata)
                clock["t"] += dt

            return sd.Stream(device=(in_idx, out_idx), samplerate=sr, blocksize=block,
                             channels=(ch_in, ch_out), dtype="float32", latency="low", callback=cb)

        # calibration: tick + flash once per second through the exact same paths
        n = int(sr * 0.03)
        click = (np.sin(2 * np.pi * 1500 * np.arange(n) / sr) * np.exp(-np.arange(n) / (sr * 0.006))
                 ).astype(np.float32) * 0.8
        hues = [0.0, 0.33, 0.62, 0.83, 0.12, 0.5]
        hi = {"i": 0}
        self.brain = self.detector = None

        def cal_cb(outdata, frames, t, status):
            now = clock["t"]
            src = np.zeros((frames, ch_out), dtype=np.float32)
            start = clock["next_click"] - now
            if start < dt:
                off = max(0, int(start * sr))
                m = min(len(click), frames - off)
                src[off:off + m] += click[:m, None]
                h = hues[hi["i"] % len(hues)]
                hi["i"] += 1
                r, g, b = colorsys.hsv_to_rgb(h, 1, 1)
                self._emit({"r": int(r * 255), "g": int(g * 255), "b": int(b * 255), "dimming": 100}, now)
                self.status["flash"] = time.time()
                self.status["flash_rgb"] = (int(r * 255), int(g * 255), int(b * 255))
                clock["next_click"] += 1.0
                clock["dim_at"] = now + 0.4
            elif clock["dim_at"] is not None and now >= clock["dim_at"]:
                self._emit({"r": 40, "g": 40, "b": 255, "dimming": 10}, now)
                clock["dim_at"] = None
            self._flush_lights(now)
            push_audio(src, outdata)
            clock["t"] += dt

        return sd.OutputStream(device=out_idx, samplerate=sr, blocksize=block, channels=ch_out,
                               dtype="float32", latency="low", callback=cal_cb)

    def stop(self, restore=True):
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
        self.stream, self.mode = None, None
        self.brain = self.detector = None
        if restore:
            self.restore_bulb()

    def live_view(self):
        """Snapshot for the UI."""
        b = self.brain
        if b is None:
            return None
        return {"rgb": b.rgb, "dim": b.dim, "score": b.score, "level": self.status["level"],
                "beats": self.status["beats"]}

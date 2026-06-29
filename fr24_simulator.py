"""
FR24 Feeder Simulator
- HTTP  192.168.1.48:8754  → /monitor.json, /flights.json, index.html, settings.html
- TCP   192.168.1.48:30003 → SBS-1 (BaseStation) message stream
"""

import json
import math
import mimetypes
import os
import random
import socket
import threading
import time
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

STATIC_DIR = os.path.dirname(os.path.abspath(__file__))

HOST      = "192.168.1.48"
HTTP_PORT = 8754
SBS_PORT  = 30003

START_TIME = time.time()

# ── Aircraft pool ────────────────────────────────────────────────────────────
# Routes typical over Spain / W-Europe
AIRCRAFT_POOL = [
    {"icao": "3C4B4C", "reg": "D-AIPW", "type": "A320", "flight": "LH1806", "from": "MAD", "to": "FRA"},
    {"icao": "400F85", "reg": "G-EUUD", "type": "A320", "flight": "BA463",  "from": "LHR", "to": "MAD"},
    {"icao": "344659", "reg": "EC-MXY", "type": "A320", "flight": "VY1234", "from": "BCN", "to": "CDG"},
    {"icao": "3443C5", "reg": "EC-LVS", "type": "B738", "flight": "VY2019", "from": "PMI", "to": "MAD"},
    {"icao": "3C6444", "reg": "D-AIMK", "type": "A321", "flight": "LH3482", "from": "MUC", "to": "AGP"},
    {"icao": "484161", "reg": "OE-LBE", "type": "B738", "flight": "OS433",  "from": "VIE", "to": "MAD"},
    {"icao": "34634A", "reg": "EC-MKL", "type": "A320", "flight": "IB3155", "from": "MAD", "to": "LIS"},
    {"icao": "344F4A", "reg": "EC-NBO", "type": "A320", "flight": "VY7614", "from": "SVQ", "to": "BCN"},
    {"icao": "3C6780", "reg": "D-AINE", "type": "A319", "flight": "LH5671", "from": "BCN", "to": "HAM"},
    {"icao": "400F47", "reg": "G-TTNG", "type": "A320", "flight": "BA7130", "from": "LHR", "to": "AGP"},
    {"icao": "345190", "reg": "EC-OBK", "type": "B738", "flight": "UX1131", "from": "MAD", "to": "PMI"},
    {"icao": "3C6A8E", "reg": "D-AIUH", "type": "A320", "flight": "LH1034", "from": "FRA", "to": "BCN"},
    {"icao": "A08CCA", "reg": "N12010", "type": "B77W", "flight": "UA48",   "from": "EWR", "to": "MAD"},
    {"icao": "4010DE", "reg": "G-VIIO", "type": "B772", "flight": "BA75",   "from": "MAD", "to": "LHR"},
    {"icao": "34671C", "reg": "EC-LZJ", "type": "A320", "flight": "VY3900", "from": "BCN", "to": "SVQ"},
    {"icao": "495149", "reg": "EC-NTZ", "type": "A320", "flight": "VLG123", "from": "AGP", "to": "BCN"},
    {"icao": "4CADC4", "reg": "EI-EDP", "type": "B738", "flight": "RYR44",  "from": "MAD", "to": "DUB"},
    {"icao": "3C64A2", "reg": "D-AIZG", "type": "A320", "flight": "LH2056", "from": "FRA", "to": "SVQ"},
    {"icao": "3C5099", "reg": "D-AIBF", "type": "A319", "flight": "LH1180", "from": "MUC", "to": "MAD"},
    {"icao": "4CAEE6", "reg": "EI-DVG", "type": "B738", "flight": "RYR88",  "from": "STN", "to": "AGP"},
    {"icao": "346185", "reg": "EC-MNZ", "type": "A320", "flight": "IBE034", "from": "MAD", "to": "ORY"},
    {"icao": "440248", "reg": "G-EZWZ", "type": "A320", "flight": "EZY18",  "from": "LGW", "to": "MAD"},
    {"icao": "4951D5", "reg": "EC-NAJ", "type": "A320", "flight": "VLG554", "from": "BCN", "to": "PMI"},
    {"icao": "4CAC23", "reg": "EI-DAP", "type": "B738", "flight": "RYR62",  "from": "CRL", "to": "MAD"},
    {"icao": "348602", "reg": "EC-OAD", "type": "AT76", "flight": "ANE91T", "from": "MAD", "to": "VLC"},
    {"icao": "495297", "reg": "EC-NUG", "type": "A320", "flight": "VLG901", "from": "PMI", "to": "MAD"},
    {"icao": "0D10D5", "reg": "CN-ROW", "type": "B738", "flight": "RAM206", "from": "CMN", "to": "MAD"},
    {"icao": "4CAEE6", "reg": "EI-DVG", "type": "B738", "flight": "RYR88",  "from": "STN", "to": "AGP"},
    {"icao": "3C5EEB", "reg": "D-AIZR", "type": "A320", "flight": "LH1832", "from": "FRA", "to": "MAD"},
    {"icao": "4CAE53", "reg": "EI-DLR", "type": "B738", "flight": "RYR15",  "from": "MAD", "to": "ORK"},
]

# Deduplicate by ICAO
_seen = set()
_deduped = []
for _ac in AIRCRAFT_POOL:
    if _ac["icao"] not in _seen:
        _seen.add(_ac["icao"])
        _deduped.append(_ac)
AIRCRAFT_POOL = _deduped


# ── Position generator (shared by HTTP and SBS) ─────────────────────────────

def _ac_params(aircraft_id: int):
    """Return stable random flight parameters for a given pool index."""
    rng = random.Random(aircraft_id * 1000)
    return {
        "base_lat":  rng.uniform(36.5, 44.0),
        "base_lon":  rng.uniform(-9.0,  4.0),
        "speed_kts": rng.randint(380, 510),
        "heading":   rng.randint(0, 359),
        "altitude":  rng.choice([29000, 31000, 33000, 35000, 37000, 39000]),
        "vspeed":    rng.choice([-64, 0, 0, 0, 64, 128]),
        "squawk":    f"{rng.randint(1000, 7776):04d}",
    }

# Cache params so every call with same id returns identical constants
_PARAMS_CACHE = {i: _ac_params(i) for i in range(len(AIRCRAFT_POOL))}


def get_position(aircraft_id: int, t: float) -> dict:
    """Return current position dict for an aircraft at time t."""
    p   = _PARAMS_CACHE[aircraft_id % len(AIRCRAFT_POOL)]
    ac  = AIRCRAFT_POOL[aircraft_id % len(AIRCRAFT_POOL)]
    dist_nm = (p["speed_kts"] / 3600.0) * (t % 7200)
    lat = p["base_lat"] + dist_nm * math.cos(math.radians(p["heading"])) / 60.0
    lon = p["base_lon"] + dist_nm * math.sin(math.radians(p["heading"])) / (
        60.0 * math.cos(math.radians(p["base_lat"]))
    )
    return {
        "icao":     ac["icao"],
        "lat":      round(lat, 5),
        "lon":      round(lon, 5),
        "heading":  p["heading"],
        "altitude": p["altitude"],
        "speed":    p["speed_kts"],
        "squawk":   p["squawk"],
        "vspeed":   p["vspeed"],
        "flight":   ac["flight"],
        "type":     ac["type"],
        "reg":      ac["reg"],
        "from":     ac["from"],
        "to":       ac["to"],
    }


# ── HTTP data builders ───────────────────────────────────────────────────────

def build_flights_json(t: float) -> dict:
    rng = random.Random(int(t / 30))
    n   = rng.randint(6, len(AIRCRAFT_POOL))
    ids = rng.sample(range(len(AIRCRAFT_POOL)), n)

    result = {"full_count": n, "version": 4}
    for aid in ids:
        p = get_position(aid, t)
        result[p["icao"]] = [
            p["icao"], p["lat"], p["lon"], p["heading"],
            p["altitude"], p["speed"], p["squawk"],
            "F-ADSB", p["type"], p["reg"],
            int(t) - random.randint(0, 5),
            p["from"], p["to"], p["flight"],
            0, p["vspeed"], p["flight"], 0,
        ]
    return result


def _df_stats(uptime: int) -> str:
    """Return a hex DF-type histogram matching the real feeder format (32 slots)."""
    counts = ["0"] * 32
    counts[0]  = hex(int(uptime * 2))[2:]    # DF0  Short air-air
    counts[4]  = hex(int(uptime * 3))[2:]    # DF4  Surveillance altitude
    counts[5]  = hex(int(uptime * 1))[2:]    # DF5  Surveillance identity
    counts[11] = hex(int(uptime * 8))[2:]    # DF11 All-call reply
    counts[17] = hex(int(uptime * 60))[2:]   # DF17 Extended squitter (ADS-B)
    counts[18] = hex(int(uptime * 4))[2:]    # DF18 TIS-B
    counts[20] = hex(int(uptime * 2))[2:]    # DF20 Comm-B altitude
    return ",".join(counts)


def build_monitor_json(t: float) -> dict:
    """Flat string-valued dict matching the real FR24 feeder /monitor.json schema."""
    uptime     = int(t - START_TIME)
    connect_ts = int(START_TIME)
    connect_dt = datetime.fromtimestamp(connect_ts).strftime("%Y-%m-%d %H:%M:%S")
    now_dt     = datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S")
    num_msg    = int(uptime * 12 + random.randint(0, 5))

    # Active aircraft count — same logic as build_flights_json
    rng  = random.Random(int(t / 30))
    n_ac = rng.randint(6, len(AIRCRAFT_POOL))

    # Timing sync cycles every 1200 s (timesyncd default interval)
    timing_cycle       = uptime % 1200
    timing_last_ts     = int(t) - timing_cycle
    num_timeouts       = int(uptime / 60)   # ~1 global timeout per minute
    last_rx_timeout_ts = connect_ts - 5    # just before first connect

    return {
        "ac_map_size":                  str(n_ac),
        "build_arch":                   "static_armel",
        "build_flavour":                "generic",
        "build_os":                     "Linux",
        "build_revision":               "T202605251242",
        "build_timetamp":               "May 25 2026 12:54:59",
        "build_version":                "1.0.57-1",
        "cfg_baudrate":                 "",
        "cfg_bs":                       "no",
        "cfg_host":                     "127.0.0.1:30005",
        "cfg_mpx":                      "",
        "cfg_path":                     "",
        "cfg_raw":                      "no",
        "cfg_receiver":                 "beast-tcp",
        "cfg_windowmode":               "0",
        "d11_map_size":                 "0",
        "df-stats":                     _df_stats(uptime),
        "df-stats-since":               str(int(t)),
        "extended_ui":                  "no",
        "feed_alias":                   "T-LEBZ21",
        "feed_configured_mode":         "UDP",
        "feed_current_mode":            "UDP",
        "feed_current_server":          "blender.prod.fr24.io",
        "feed_last_ac_sent_num":        str(n_ac),
        "feed_last_ac_sent_time":       str(int(t) - 30),
        "feed_last_attempt_time":       str(connect_ts),
        "feed_last_config_info":        "",
        "feed_last_config_result":      "success",
        "feed_last_connected_time":     str(connect_ts),
        "feed_legacy_id":               "11576",
        "feed_num_ac_adsb_tracked":     str(n_ac),
        "feed_num_ac_non_adsb_tracked": "0",
        "feed_num_ac_tracked":          str(n_ac),
        "feed_status":                  "connected",
        "feed_status_message":          "",
        "feed_type":                    "adsb",
        "fr24key":                      "4b43a4c6e79677ad",
        "gps_tods":                     "0",
        "last_json_utc":                str(int(t)),
        "last_rx_connect_status":       "OK",
        "last_rx_connect_time":         str(connect_ts),
        "last_rx_connect_time_s":       connect_dt,
        "last_rx_global_timeout":       str(last_rx_timeout_ts),
        "local_ips":                    "192.168.0.11,fe80::f26a:98d9:4711:a38a",
        "local_tods":                   str(int(t) % 86400),
        "msg_ring_full":                "false",
        "msg_ring_length":              "0",
        "num_global_timeouts":          str(num_timeouts),
        "num_messages":                 str(num_msg),
        "num_resyncs":                  "0",
        "offline-mode":                 "yes",
        "open_fds":                     "7",
        "rx_connected":                 "1",
        "shutdown":                     "no",
        "time_update_utc":              str(int(t)),
        "time_update_utc_s":            now_dt,
        "timestamp_source":             "SYSTEM-VALIDATED",
        "timing_is_valid":              "1",
        "timing_last_drift":            "+0.000",
        "timing_last_offset":           "+0.000",
        "timing_last_result":           "success",
        "timing_source":                "timesyncd",
        "timing_time_last_attempt":     str(timing_last_ts),
        "timing_time_last_success":     str(timing_last_ts),
        "timing_time_since_last_success": str(timing_cycle),
        "wifi_allowed":                 "0",
    }


# ── HTTP server ──────────────────────────────────────────────────────────────

class FR24Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[HTTP {datetime.now().strftime('%H:%M:%S')}] "
              f"{self.address_string()} {fmt % args}")

    def send_json(self, data: dict):
        body = json.dumps(data, separators=(",", ":")).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def serve_static(self):
        path = self.path.split("?")[0]
        if path in ("/", ""):
            path = "/index.html"
        fp = os.path.join(STATIC_DIR, path.lstrip("/"))
        if not os.path.isfile(fp):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")
            return
        mime, _ = mimetypes.guess_type(fp)
        with open(fp, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        t = time.time()
        if   self.path == "/flights.json": self.send_json(build_flights_json(t))
        elif self.path == "/monitor.json": self.send_json(build_monitor_json(t))
        else:                              self.serve_static()


# ── SBS-1 (BaseStation) TCP server ──────────────────────────────────────────
#
# Format (22 comma-separated fields, CRLF terminated):
# MSG,<type>,<ses>,<ac_id>,<hex>,<flt_id>,<date_gen>,<time_gen>,
#     <date_log>,<time_log>,<callsign>,<alt>,<spd>,<trk>,<lat>,<lon>,
#     <vspeed>,<squawk>,<alert>,<emrg>,<spi>,<onground>
#
# Type 1  → callsign only
# Type 3  → altitude + lat + lon
# Type 4  → speed + track + vspeed
# Type 8  → squitter (presence only)

_sbs_clients: list[socket.socket] = []
_sbs_lock = threading.Lock()

# Rolling counters matching the sample data pattern
_ses_id  = 333
_flt_ctr = 100   # increments per message

def _sbs_dt(t: float):
    dt = datetime.fromtimestamp(t)
    return dt.strftime("%Y/%m/%d"), dt.strftime("%H:%M:%S.") + f"{dt.microsecond//1000:03d}"


def make_sbs_msg(msg_type: int, aid: int, flt_id: int, t: float) -> str:
    """Build one SBS CSV line for the given message type."""
    p        = get_position(aid, t)
    date, ts = _sbs_dt(t)
    icao     = p["icao"]
    ac_id    = aid + 1

    # 22 fields; start with empties and fill per type
    f = [""] * 22
    f[0]  = "MSG"
    f[1]  = str(msg_type)
    f[2]  = str(_ses_id)
    f[3]  = str(ac_id)
    f[4]  = icao
    f[5]  = str(flt_id)
    f[6]  = date
    f[7]  = ts
    f[8]  = date
    f[9]  = ts

    if msg_type == 1:
        f[10] = p["flight"]          # callsign
        f[21] = "0"

    elif msg_type == 3:
        f[11] = str(p["altitude"])   # altitude
        f[14] = str(p["lat"])
        f[15] = str(p["lon"])
        f[18] = "0"                  # alert
        f[19] = "0"                  # emergency
        f[20] = "0"                  # SPI
        f[21] = "0"                  # onground

    elif msg_type == 4:
        f[12] = f"{p['speed']:.1f}"  # groundspeed
        f[13] = f"{p['heading']:.1f}"# track
        f[16] = str(p["vspeed"])     # vertical rate

    elif msg_type == 8:
        f[21] = "0"

    return ",".join(f) + "\r\n"


def _broadcast(line: str):
    """Send a line to all connected SBS clients; drop dead ones."""
    data = line.encode()
    dead = []
    with _sbs_lock:
        for conn in _sbs_clients:
            try:
                conn.sendall(data)
            except OSError:
                dead.append(conn)
        for conn in dead:
            _sbs_clients.remove(conn)
            try:
                conn.close()
            except OSError:
                pass


def _sbs_stream():
    """Background thread: generate SBS messages and broadcast them."""
    # Weighted message-type distribution matching real dump1090 output:
    # MSG,8 most common (squitter), then MSG,4 (velocity), MSG,3 (position), MSG,1 (rare)
    type_weights = [
        (8, 40),
        (4, 30),
        (3, 25),
        (1,  5),
    ]
    types, weights = zip(*type_weights)
    flt_id = _flt_ctr

    while True:
        t      = time.time()
        n_ac   = len(AIRCRAFT_POOL)
        aid    = random.randint(0, n_ac - 1)
        mtype  = random.choices(types, weights=weights, k=1)[0]
        line   = make_sbs_msg(mtype, aid, flt_id, t)
        flt_id = (flt_id % 999) + 100

        with _sbs_lock:
            has_clients = len(_sbs_clients) > 0

        if has_clients:
            _broadcast(line)

        # ~12–18 messages per second, matching a busy SDR receiver
        time.sleep(random.uniform(0.055, 0.085))


def _handle_sbs_client(conn: socket.socket, addr):
    """Watch for client disconnects (they don't send anything, just receive)."""
    try:
        while True:
            data = conn.recv(1)
            if not data:
                break
    except OSError:
        pass
    finally:
        with _sbs_lock:
            if conn in _sbs_clients:
                _sbs_clients.remove(conn)
        try:
            conn.close()
        except OSError:
            pass
        print(f"[SBS  {datetime.now().strftime('%H:%M:%S')}] "
              f"Client disconnected: {addr[0]}:{addr[1]}")


def _sbs_accept(server_sock: socket.socket):
    """Accept loop for the SBS TCP server."""
    while True:
        try:
            conn, addr = server_sock.accept()
        except OSError:
            break
        with _sbs_lock:
            _sbs_clients.append(conn)
        print(f"[SBS  {datetime.now().strftime('%H:%M:%S')}] "
              f"Client connected: {addr[0]}:{addr[1]}")
        threading.Thread(target=_handle_sbs_client, args=(conn, addr),
                         daemon=True).start()


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Start SBS TCP server
    sbs_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sbs_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sbs_sock.bind((HOST, SBS_PORT))
    sbs_sock.listen(10)
    threading.Thread(target=_sbs_accept,  args=(sbs_sock,), daemon=True).start()
    threading.Thread(target=_sbs_stream,  daemon=True).start()

    # Start HTTP server (blocking main thread)
    http = HTTPServer((HOST, HTTP_PORT), FR24Handler)

    print(f"FR24 Simulator started")
    print(f"  HTTP  http://{HOST}:{HTTP_PORT}/")
    print(f"        http://{HOST}:{HTTP_PORT}/monitor.json")
    print(f"        http://{HOST}:{HTTP_PORT}/flights.json")
    print(f"  SBS-1 tcp://{HOST}:{SBS_PORT}   (BaseStation stream)")
    print("Press Ctrl+C to stop.\n")
    print("SkyDronex - DoverKan.\n")

    try:
        http.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        sbs_sock.close()

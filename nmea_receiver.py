# Livre de Bord Nautique
# Copyright (C) 2026  [LeGrosMario]
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License.
#
# https://www.gnu.org/licenses/gpl-3.0.html

"""
nmea_receiver.py
Écoute le flux NMEA en UDP ou TCP et parse les trames pour extraire les données navigation.

Modes supportés :
  - UDP  : écoute passive sur un port local (centrale broadcast/multicast)
  - TCP  : connexion cliente vers une adresse IP:port (multiplexeur WiFi, ex. iKommunicate,
            Yacht Devices YDWG-02, B&G Zeus, etc.)
"""

import socket
import threading
import time
from datetime import datetime, timezone


class NMEAData:
    """Snapshot des données NMEA les plus récentes."""
    def __init__(self):
        self.time_utc: str = ""
        self.lat: float = None
        self.lon: float = None
        self.cog: float = None   # Course Over Ground (°)
        self.sog: float = None   # Speed Over Ground (kn)
        self.awa: float = None   # Apparent Wind Angle (°)
        self.aws: float = None   # Apparent Wind Speed (kn)
        self.twd: float = None   # True Wind Direction (°)
        self.twa: float = None   # True Wind Angle (°)
        self.tws: float = None   # True Wind Speed (kn)
        self.hdg: float = None   # Heading (°)
        self.last_update: float = 0.0

    def to_dict(self) -> dict:
        return {
            "time_utc": self.time_utc,
            "lat": round(self.lat, 6) if self.lat is not None else None,
            "lon": round(self.lon, 6) if self.lon is not None else None,
            "cog": round(self.cog, 1) if self.cog is not None else None,
            "sog": round(self.sog, 2) if self.sog is not None else None,
            "awa": round(self.awa, 1) if self.awa is not None else None,
            "aws": round(self.aws, 2) if self.aws is not None else None,
            "twd": round(self.twd, 1) if self.twd is not None else None,
            "twa": round(self.twa, 1) if self.twa is not None else None,
            "tws": round(self.tws, 2) if self.tws is not None else None,
        }

    def copy(self):
        n = NMEAData()
        n.__dict__.update(self.__dict__)
        return n


# ---------------------------------------------------------------------------
# Fonctions utilitaires de parsing
# ---------------------------------------------------------------------------

def _nmea_checksum_valid(sentence: str) -> bool:
    """Vérifie le checksum NMEA."""
    try:
        if '*' not in sentence:
            return True  # pas de checksum, on accepte
        body, chk = sentence[1:].split('*', 1)
        calculated = 0
        for c in body:
            calculated ^= ord(c)
        return calculated == int(chk[:2], 16)
    except Exception:
        return False


def _parse_lat(val: str, hemi: str) -> float | None:
    if not val or not hemi:
        return None
    try:
        deg = int(float(val) / 100)
        mins = float(val) - deg * 100
        result = deg + mins / 60.0
        if hemi in ('S', 'W'):
            result = -result
        return result
    except Exception:
        return None


def _safe_float(val: str) -> float | None:
    try:
        return float(val)
    except Exception:
        return None


def _fmt_time(raw: str) -> str:
    """Formate HHMMSS.ss → HH:MM:SS UTC."""
    try:
        return f"{raw[0:2]}:{raw[2:4]}:{raw[4:6]} UTC"
    except Exception:
        return raw


# ---------------------------------------------------------------------------
# Récepteur NMEA (UDP ou TCP)
# ---------------------------------------------------------------------------

class NMEAReceiver:
    """
    Réception NMEA multiprotocole :

      UDP (défaut) — écoute passive sur un port local.
        NMEAReceiver(mode='udp', port=2000)

      TCP — connexion cliente vers un serveur distant (multiplexeur WiFi, etc.).
        NMEAReceiver(mode='tcp', host='192.168.76.1', port=10110)

    Les deux modes partagent le même parser et le même objet NMEAData.
    En cas de déconnexion TCP, une reconnexion automatique est tentée toutes les 5 s.
    """

    RECONNECT_DELAY = 5  # secondes entre deux tentatives TCP

    def __init__(self, mode: str = 'udp', host: str = '', port: int = 2000):
        if mode not in ('udp', 'tcp'):
            raise ValueError(f"mode doit être 'udp' ou 'tcp', pas {mode!r}")
        self.mode = mode
        self.host = host
        self.port = port
        self.data = NMEAData()
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread = None
        self._callbacks = []
        self._connected = False   # pertinent uniquement en mode TCP

    # ── API publique ────────────────────────────────────────────────────────

    def get_snapshot(self) -> NMEAData:
        with self._lock:
            return self.data.copy()

    def add_callback(self, fn):
        """Enregistre une fonction appelée après chaque trame parsée avec succès."""
        self._callbacks.append(fn)

    @property
    def is_connected(self) -> bool:
        """True si le flux est actif (UDP: toujours True après bind ; TCP: connexion établie)."""
        return self._connected

    def start(self):
        self._running = True
        target = self._run_udp if self.mode == 'udp' else self._run_tcp
        self._thread = threading.Thread(target=target, daemon=True, name=f"NMEA-{self.mode}")
        self._thread.start()

    def stop(self):
        self._running = False
        self._connected = False

    # ── Boucle UDP ──────────────────────────────────────────────────────────

    def _run_udp(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(1.0)
        try:
            sock.bind(('', self.port))
        except OSError as e:
            print(f"[NMEA/UDP] Impossible de lier le port {self.port}: {e}")
            return

        print(f"[NMEA/UDP] Écoute sur le port {self.port}")
        self._connected = True
        while self._running:
            try:
                raw, _ = sock.recvfrom(4096)
                self._process_raw(raw)
            except socket.timeout:
                continue
            except Exception as e:
                print(f"[NMEA/UDP] Erreur: {e}")
        self._connected = False
        sock.close()

    # ── Boucle TCP ──────────────────────────────────────────────────────────

    def _run_tcp(self):
        """
        Connexion TCP vers host:port avec reconnexion automatique.
        Les trames NMEA arrivent sous forme de lignes texte terminées par \r\n ou \n.
        Un buffer gère les paquets fragmentés ou multi-trames.
        """
        while self._running:
            sock = None
            try:
                print(f"[NMEA/TCP] Connexion vers {self.host}:{self.port}…")
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(10.0)
                sock.connect((self.host, self.port))
                sock.settimeout(2.0)
                self._connected = True
                print(f"[NMEA/TCP] Connecté à {self.host}:{self.port}")

                buf = b""
                while self._running:
                    try:
                        chunk = sock.recv(4096)
                        if not chunk:
                            print("[NMEA/TCP] Connexion fermée par le serveur.")
                            break
                        buf += chunk
                        # Découper sur les fins de ligne
                        while b'\n' in buf:
                            line, buf = buf.split(b'\n', 1)
                            text = line.decode('ascii', errors='ignore').strip()
                            if text.startswith('$') or text.startswith('!'):
                                self._parse_sentence(text)
                    except socket.timeout:
                        continue
                    except Exception as e:
                        print(f"[NMEA/TCP] Erreur lecture: {e}")
                        break

            except (ConnectionRefusedError, OSError, socket.timeout) as e:
                print(f"[NMEA/TCP] Échec connexion: {e}")
            finally:
                self._connected = False
                if sock:
                    try:
                        sock.close()
                    except Exception:
                        pass

            if self._running:
                print(f"[NMEA/TCP] Nouvelle tentative dans {self.RECONNECT_DELAY}s…")
                time.sleep(self.RECONNECT_DELAY)

    # ── Parsing commun ──────────────────────────────────────────────────────

    def _process_raw(self, raw: bytes):
        """Décode et dispatche les lignes brutes (mode UDP)."""
        text = raw.decode('ascii', errors='ignore')
        for line in text.splitlines():
            line = line.strip()
            if line.startswith('$') or line.startswith('!'):
                self._parse_sentence(line)

    def _parse_sentence(self, sentence: str):
        if not _nmea_checksum_valid(sentence):
            return

        if '*' in sentence:
            sentence = sentence[:sentence.index('*')]

        parts = sentence.split(',')
        tag = parts[0][1:]  # retire '$'

        updated = False
        with self._lock:
            d = self.data

            # --- RMC : position, SOG, COG, heure ---
            if tag in ('GPRMC', 'GNRMC', 'IIRMC'):
                if len(parts) >= 9 and parts[2] == 'A':
                    d.time_utc = _fmt_time(parts[1])
                    d.lat = _parse_lat(parts[3], parts[4])
                    d.lon = _parse_lat(parts[5], parts[6])
                    d.sog = _safe_float(parts[7])
                    d.cog = _safe_float(parts[8])
                    d.last_update = time.time()
                    updated = True

            # --- GGA : position + heure ---
            elif tag in ('GPGGA', 'GNGGA'):
                if len(parts) >= 6 and parts[6] not in ('0', ''):
                    d.time_utc = _fmt_time(parts[1])
                    d.lat = _parse_lat(parts[2], parts[3])
                    d.lon = _parse_lat(parts[4], parts[5])
                    d.last_update = time.time()
                    updated = True

            # --- VTG : COG + SOG ---
            elif tag in ('GPVTG', 'GNVTG', 'IIVTG'):
                if len(parts) >= 8:
                    d.cog = _safe_float(parts[1])
                    d.sog = _safe_float(parts[7])
                    updated = True

            # --- MWV : vent apparent ou vrai ---
            elif tag in ('IIMWV', 'WIMWV', 'MWVB'):
                if len(parts) >= 6 and parts[5] in ('A', ''):
                    angle = _safe_float(parts[1])
                    speed = _safe_float(parts[3])
                    ref   = parts[2]
                    unit  = parts[4]
                    if speed is not None and unit in ('N', 'K', 'M'):
                        if unit == 'K':
                            speed = speed / 1.852
                        elif unit == 'M':
                            speed = speed * 1.94384
                    if ref == 'R':
                        d.awa = angle
                        d.aws = speed
                    elif ref == 'T':
                        d.twa = angle
                        d.tws = speed
                    updated = True

            # --- MWD : direction vraie du vent ---
            elif tag in ('IIMWD', 'WIMWD'):
                if len(parts) >= 8:
                    d.twd = _safe_float(parts[1])
                    speed = _safe_float(parts[7])
                    unit  = parts[6] if len(parts) > 6 else 'N'
                    if speed is not None and unit == 'K':
                        speed = speed / 1.852
                    d.tws = speed
                    updated = True

            # --- HDG / HDT : cap ---
            elif tag in ('IIHDG', 'IIHDM', 'IIHDT', 'HCHDG', 'HCHDM'):
                if len(parts) >= 2:
                    d.hdg = _safe_float(parts[1])
                    updated = True

            # --- VHW : vitesse loch ---
            elif tag in ('IIVHW',):
                if len(parts) >= 6:
                    d.sog = _safe_float(parts[5])
                    updated = True

        if updated:
            for cb in self._callbacks:
                try:
                    cb()
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# Simulateur NMEA pour les tests sans bateau
# ---------------------------------------------------------------------------
import math

class NMEASimulator:
    """
    Envoie des trames NMEA simulées en UDP sur 127.0.0.1 pour les tests.
    Compatible quel que soit le mode (UDP ou TCP) du récepteur principal,
    car le récepteur UDP écoute sur le même port local.
    """

    def __init__(self, port: int = 2000, interval: float = 1.0):
        self.port = port
        self.interval = interval
        self._running = False
        self._t = 0.0

    def start(self):
        self._running = True
        threading.Thread(target=self._run, daemon=True, name="NMEA-sim").start()

    def stop(self):
        self._running = False

    def _run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        while self._running:
            for s in self._generate():
                sock.sendto((s + '\r\n').encode(), ('127.0.0.1', self.port))
            time.sleep(self.interval)
            self._t += self.interval
        sock.close()

    def _generate(self) -> list[str]:
        t = self._t
        lat  = 43.2965 + math.sin(t / 300) * 0.05
        lon  = 5.3811  + math.cos(t / 300) * 0.05
        sog  = 5.5     + math.sin(t / 60)  * 1.5
        cog  = (180    + math.sin(t / 120) * 30)  % 360
        awa  = (45     + math.sin(t / 45)  * 10)  % 360
        aws  = 12      + math.sin(t / 80)  * 3
        twd  = (210    + math.sin(t / 200) * 15)  % 360
        tws  = 10      + math.sin(t / 100) * 2
        twa  = (twd - cog + 360) % 360

        now    = datetime.now(timezone.utc)
        hhmmss = now.strftime('%H%M%S')
        ddmmyy = now.strftime('%d%m%y')

        lat_d = int(lat);  lat_m = (lat - lat_d) * 60
        lon_d = int(lon);  lon_m = (lon - lon_d) * 60

        def chk(s):
            c = 0
            for ch in s:
                c ^= ord(ch)
            return f"${s}*{c:02X}"

        return [
            chk(f"GPRMC,{hhmmss}.00,A,{lat_d:02d}{lat_m:07.4f},N,{lon_d:03d}{lon_m:07.4f},E,{sog:.1f},{cog:.1f},{ddmmyy},,,A"),
            chk(f"IIMWV,{awa:.1f},R,{aws:.1f},N,A"),
            chk(f"IIMWV,{twa:.1f},T,{tws:.1f},N,A"),
            chk(f"IIMWD,{twd:.1f},T,{twd:.1f},M,{tws:.2f},N,{tws*1.852:.2f},K"),
        ]

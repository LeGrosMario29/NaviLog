# Livre de Bord Nautique
# Copyright (C) 2026  [LeGrosMario]
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License.
#
# https://www.gnu.org/licenses/gpl-3.0.html

"""
logbook.py
Gestion du carnet de bord : points, fichier JSON, totalisateurs.
"""

import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# Catégories prédéfinies pour le champ "event"
EVENT_TYPES = [
    "routine",
    "virement",
    "météo",
    "moteur+",
    "moteur-",
    "voile",
    "HydroG+",
    "HydroG-",
    "radio",
    "VàB",
    "radio",
    "MOB",
    "AIS",
    "ASN"
]

def haversine_nm(lat1, lon1, lat2, lon2) -> float:
    """Distance en milles nautiques entre deux points GPS."""
    R = 3440.065  # rayon terre en NM
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


class LogPoint:
    """Un point du carnet de bord."""

    def __init__(self):
        self.timestamp: str = ""       # ISO 8601 local
        self.time_utc: str = ""
        self.lat: float = None
        self.lon: float = None
        self.cog: float = None
        self.sog: float = None
        self.awa: float = None
        self.aws: float = None
        self.twd: float = None
        self.twa: float = None
        self.tws: float = None
        self.event: str = "routine"    # catégorie prédéfinie
        self.note: str = ""            # texte libre
        self.auto: bool = False        # True si enregistré automatiquement

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}

    @classmethod
    def from_dict(cls, d: dict) -> "LogPoint":
        p = cls()
        for k, v in d.items():
            if hasattr(p, k):
                setattr(p, k, v)
        return p

    @classmethod
    def from_nmea(cls, nmea, event: str = "routine", note: str = "", auto: bool = False) -> "LogPoint":
        p = cls()
        p.timestamp = datetime.now().astimezone().isoformat(timespec='seconds')
        p.time_utc = nmea.time_utc
        p.lat = nmea.lat
        p.lon = nmea.lon
        p.cog = nmea.cog
        p.sog = nmea.sog
        p.awa = nmea.awa
        p.aws = nmea.aws
        p.twd = nmea.twd
        p.twa = nmea.twa
        p.tws = nmea.tws
        p.event = event
        p.note = note
        p.auto = auto
        return p

    def display_time(self) -> str:
        try:
            dt = datetime.fromisoformat(self.timestamp)
            return dt.strftime('%d/%m %H:%M')
        except Exception:
            return self.timestamp[:16] if self.timestamp else "—"

    def summary(self) -> str:
        parts = [self.display_time()]
        if self.sog is not None:
            parts.append(f"{self.sog:.1f}kn")
        if self.cog is not None:
            parts.append(f"COG {self.cog:.0f}°")
        if self.awa is not None:
            parts.append(f"AWA {self.awa:.0f}°")
        parts.append(f"[{self.event}]")
        if self.note:
            parts.append(self.note[:30])
        return "  ".join(parts)


class VoyageStats:
    """Statistiques calculées à la volée sur les points du voyage."""

    def __init__(self, points: list):
        self.distance_nm: float = 0.0
        self.elapsed_seconds: int = 0
        self.aws_min: float = None
        self.aws_max: float = None
        self.sog_min: float = None
        self.sog_max: float = None
        self.sog_avg_last_hour: float = None
        self._compute(points)

    def _compute(self, points: list):
        if not points:
            return

        # Distance cumulée
        dist = 0.0
        prev = None
        for p in points:
            if prev and prev.lat and prev.lon and p.lat and p.lon:
                dist += haversine_nm(prev.lat, prev.lon, p.lat, p.lon)
            prev = p
        self.distance_nm = dist

        # Durée
        try:
            t0 = datetime.fromisoformat(points[0].timestamp)
            t1 = datetime.fromisoformat(points[-1].timestamp)
            self.elapsed_seconds = int((t1 - t0).total_seconds())
        except Exception:
            pass

        # Min/max AWS et SOG
        aws_vals = [p.aws for p in points if p.aws is not None]
        sog_vals = [p.sog for p in points if p.sog is not None]
        if aws_vals:
            self.aws_min = min(aws_vals)
            self.aws_max = max(aws_vals)
        if sog_vals:
            self.sog_min = min(sog_vals)
            self.sog_max = max(sog_vals)

        # SOG moyenne dernière heure
        now = datetime.now().astimezone()
        last_hour = []
        for p in points:
            try:
                pt = datetime.fromisoformat(p.timestamp)
                if (now - pt).total_seconds() <= 3600 and p.sog is not None:
                    last_hour.append(p.sog)
            except Exception:
                pass
        if last_hour:
            self.sog_avg_last_hour = sum(last_hour) / len(last_hour)

    def elapsed_str(self) -> str:
        h = self.elapsed_seconds // 3600
        m = (self.elapsed_seconds % 3600) // 60
        return f"{h:02d}h{m:02d}"


class Logbook:
    """
    Carnet de bord : gère les points, la persistance JSON et les métadonnées voyage.
    """

    def __init__(self):
        self.voyage_name: str = ""
        self.distance_planned_nm: float = None
        self.points: list[LogPoint] = []
        self.filepath: Optional[Path] = None
        self._dirty: bool = False

    # ------------------------------------------------------------------
    # Métadonnées voyage
    # ------------------------------------------------------------------

    def set_voyage(self, name: str, distance_planned: float = None):
        self.voyage_name = name
        self.distance_planned_nm = distance_planned
        self._dirty = True

    # ------------------------------------------------------------------
    # Points
    # ------------------------------------------------------------------

    def add_point(self, point: LogPoint) -> int:
        """Ajoute un point, trie par timestamp, retourne l'index."""
        self.points.append(point)
        self.points.sort(key=lambda p: p.timestamp)
        self._dirty = True
        return self.points.index(point)

    def update_point(self, index: int, point: LogPoint):
        self.points[index] = point
        self._dirty = True

    def delete_point(self, index: int):
        del self.points[index]
        self._dirty = True

    def get_stats(self) -> VoyageStats:
        return VoyageStats(self.points)

    # ------------------------------------------------------------------
    # Persistance JSON
    # ------------------------------------------------------------------

    def new_file(self, path: Path):
        self.filepath = path
        self.points = []
        self.voyage_name = ""
        self.distance_planned_nm = None
        self._dirty = False

    def save(self, path: Path = None):
        target = path or self.filepath
        if not target:
            raise ValueError("Aucun fichier spécifié pour la sauvegarde.")
        self.filepath = target
        data = {
            "voyage_name": self.voyage_name,
            "distance_planned_nm": self.distance_planned_nm,
            "created": datetime.now().astimezone().isoformat(timespec='seconds'),
            "points": [p.to_dict() for p in self.points],
        }
        target = Path(target)
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        self._dirty = False

    def load(self, path: Path):
        target = Path(path)
        data = json.loads(target.read_text(encoding='utf-8'))
        self.filepath = target
        self.voyage_name = data.get("voyage_name", "")
        self.distance_planned_nm = data.get("distance_planned_nm")
        self.points = [LogPoint.from_dict(d) for d in data.get("points", [])]
        self._dirty = False

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    @property
    def filename(self) -> str:
        return self.filepath if self.filepath else "Sans titre"


class AutoRecorder:
    """
    Surveille les données NMEA et enregistre automatiquement un point
    si un changement significatif est détecté (cap, vitesse, vent).
    """

    THRESHOLDS = {
        'cog': (60.0, "virement"),     # degrés virement ou empannage
        'cog': (20.0, "routine"),   # degrés chgt de direction
        'awa': (25.0, "météo"),    # degrés
        'aws': (3.0, "météo"),     # nœuds
        'sog': (1.5, "routine"),     # nœuds
    }
    MIN_INTERVAL = 60  # secondes entre deux auto-points

    def __init__(self, logbook: Logbook, get_nmea_fn, on_new_point_fn=None):
        self._logbook = logbook
        self._get_nmea = get_nmea_fn
        self._on_new_point = on_new_point_fn
        self._last_values = {}
        self._last_auto_time = 0.0
        self._running = False
        self._thread = None

    def start(self):
        self._running = True
        import threading
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _run(self):
        while self._running:
            time.sleep(5)
            self._check()

    def _check(self):
        now = time.time()
        if now - self._last_auto_time < self.MIN_INTERVAL:
            return

        snap = self._get_nmea()
        changed = False
        for key, (threshold, ev) in self.THRESHOLDS.items():
            val = getattr(snap, key)
            prev = self._last_values.get(key)
            if val is not None and prev is not None:
                diff = abs(val - prev)
                # Pour les angles, tenir compte de la circularité
                if key in ('cog', 'awa'):
                    diff = min(diff, 360 - diff)
                if diff >= threshold:
                    changed = True
                    break

        if changed:
            point = LogPoint.from_nmea(snap, event=ev, note="changement détecté: "+key+" ("+str(prev)+")", auto=True)
            self._logbook.add_point(point)
            self._last_auto_time = now
            # Mettre à jour les valeurs de référence
            for key in self.THRESHOLDS:
                val = getattr(snap, key)
                if val is not None:
                    self._last_values[key] = val
            if self._on_new_point:
                self._on_new_point(point)
        else:
            # Initialiser les valeurs de référence si elles sont vides
            for key in self.THRESHOLDS:
                if key not in self._last_values:
                    val = getattr(snap, key)
                    if val is not None:
                        self._last_values[key] = val


class PeriodicRecorder:
    """Enregistre automatiquement un point à intervalle régulier."""

    def __init__(self, logbook: Logbook, get_nmea_fn, interval_minutes: int = 15,
                 on_new_point_fn=None):
        self._logbook = logbook
        self._get_nmea = get_nmea_fn
        self._interval = interval_minutes * 60
        self._on_new_point = on_new_point_fn
        self._running = False
        self._thread = None

    def set_interval(self, minutes: int):
        self._interval = minutes * 60
        # Recalcule immédiatement la prochaine échéance
        self._next_record = time.time() + self._interval

    def start(self):
        self._running = True
        self._next_record = time.time() + self._interval
        import threading
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _run(self):
        while self._running:
            time.sleep(5)
            if time.time() >= self._next_record:
                snap = self._get_nmea()
                point = LogPoint.from_nmea(snap, event="routine", note="", auto=True)
                self._logbook.add_point(point)
                self._next_record = time.time() + self._interval
                if self._on_new_point:
                    self._on_new_point(point)

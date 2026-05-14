# NaviLog: votre Livre de Bord Nautique
# Copyright (C) 2026  [LeGrosMario]
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License.
#
# https://www.gnu.org/licenses/gpl-3.0.html

"""
ui_main.py
Fenêtre principale du livre de bord — tableau de bord + liste des points.
"""
import customtkinter as ctk
import tkinter as tk
from tkinter import ttk

import threading
import time

from logbook import Logbook, LogPoint, EVENT_TYPES, PeriodicRecorder, AutoRecorder
from nmea_receiver import NMEAReceiver, NMEASimulator

from theme import Fonts

# ── Palette marine sombre ───────────────────────────────────────────────────
BG       = "#0d1b2a"
BG2      = "#1b2d3e"
BG3      = "#24404f"
ACCENT   = "#00b4d8"
ACCENT2  = "#48cae4"
WARN     = "#f4a261"
OK       = "#52b788"
TEXT     = "#e0f4ff"
TEXT2    = "#90b8cc"
TEXT_DIM = "#506070"
RED      = "#e63946"


def _fmt_float(v, decimals=1, unit=""):
    if v is None:
        return "—"
    return f"{v:.{decimals}f}{unit}"


class StatBox(ctk.CTkFrame):
    """Petite boîte affichant un label + une valeur + unité."""

    def __init__(self, parent, label, unit="", **kwargs):
        super().__init__(parent, fg_color=BG2, border_width=0, **kwargs)
        ctk.CTkLabel(self, text=label.upper(), font=Fonts.FONT_SMALL, fg_color=BG2,
                 text_color=TEXT_DIM).pack(anchor='w', padx=8, pady=(6, 0))
        self._var = tk.StringVar(value="—")
        self._unit = unit
        self._val_label = ctk.CTkLabel(self, textvariable=self._var,
                                   font=Fonts.FONT_VALUE, fg_color=BG2, text_color=ACCENT)
        self._val_label.pack(anchor='w', padx=8, pady=(0, 6))

    def set(self, value, color=None):
        self._var.set(value)
        if color:
            self._val_label.configure(text_color=color)

    def set_float(self, v, decimals=1, unit="", color=None):
        self.set(_fmt_float(v, decimals, unit or self._unit), color)


class NMEAGauge(ctk.CTkFrame):
    """Ligne d'affichage des données NMEA temps réel + moyenne 1h."""

    def __init__(self, parent):
        super().__init__(parent, fg_color=BG)

        self._vars = {}   # name -> (val_var, avg_var, unit)
        fields = [
            ("SOG", "kn"), ("COG", "°"), ("AWA", "°"), ("AWS", "kn"),
            ("TWD", "°"), ("TWA", "°"), ("TWS", "kn"),
        ]
        for i, (name, unit) in enumerate(fields):
            f = ctk.CTkFrame(self, fg_color=BG3)
            f.grid(row=0, column=i, padx=2, pady=2, sticky='ew')
            self.columnconfigure(i, weight=1)
            ctk.CTkLabel(f, text=name, font=Fonts.FONT_SMALL, fg_color=BG3, text_color=TEXT_DIM).pack()
            val_var = tk.StringVar(value="—")
            avg_var = tk.StringVar(value="")
            ctk.CTkLabel(f, textvariable=val_var, font=Fonts.FONT_VALUE, fg_color=BG3, text_color=ACCENT2).pack()
            ctk.CTkLabel(f, textvariable=avg_var, font=Fonts.FONT_SMALL, fg_color=BG3, text_color=TEXT_DIM).pack()
            self._vars[name] = (val_var, avg_var, unit)

    def update_from_nmea(self, snap, avgs: dict = None):
        mapping = {
            'SOG': snap.sog, 'COG': snap.cog, 'AWA': snap.awa, 'AWS': snap.aws,
            'TWD': snap.twd, 'TWA': snap.twa, 'TWS': snap.tws,
        }
        avgs = avgs or {}
        for name, val in mapping.items():
            val_var, avg_var, unit = self._vars[name]
            val_var.set(_fmt_float(val, 1, unit))
            avg = avgs.get(name)
            avg_var.set(f"({_fmt_float(avg, 1, unit)})" if avg is not None else "")


class PointDialog(ctk.CTkToplevel):
    """Dialogue de création ou d'édition d'un point."""

    def __init__(self, parent, point: LogPoint = None, title="Nouveau point"):
        super().__init__(parent)
        self.title(title)
        self.configure(fg_color=BG)
        self.resizable(False, False)
        self.grab_set()
        self.result: LogPoint = None
        self._point = point or LogPoint()
        self._build()
        self.transient(parent)
        self.wait_window()

    def _build(self):
        p = self._point
        pad = dict(padx=12, pady=4)

        # En-tête NMEA (lecture seule si édition, éditable si nouveau)
        nmea_frame = tk.LabelFrame(self, text=" Données NMEA ", fg=ACCENT,
                                   bg=BG, font=Fonts.FONT_SMALL, bd=1,
                                   highlightbackground=BG3)
        nmea_frame.pack(fill='x', padx=12, pady=(12, 4))

        self._nmea_vars = {}
        fields = [
            ("Heure UTC", "time_utc", str),
            ("Lat", "lat", float), ("Lon", "lon", float),
            ("COG °", "cog", float), ("SOG kn", "sog", float),
            ("AWA °", "awa", float), ("AWS kn", "aws", float),
            ("TWD °", "twd", float), ("TWA °", "twa", float),
            ("TWS kn", "tws", float),
        ]
        for i, (label, attr, typ) in enumerate(fields):
            r, c = divmod(i, 5)
            ctk.CTkLabel(nmea_frame, text=label, font=Fonts.FONT_SMALL, fg_color=BG,
                     text_color=TEXT2).grid(row=r*2, column=c, padx=6, pady=(4, 0), sticky='w')
            val = getattr(p, attr)
            var = tk.StringVar(value="" if val is None else str(val))
            self._nmea_vars[attr] = (var, typ)
            e = ctk.CTkEntry(nmea_frame, textvariable=var, font=Fonts.FONT_SMALL,
                         fg_color=BG3, text_color=TEXT, width=12)
            e.grid(row=r*2+1, column=c, padx=6, pady=(0, 4), sticky='ew')
            nmea_frame.columnconfigure(c, weight=1)

        # Timestamp
        ts_frame = ctk.CTkFrame(self, fg_color=BG)
        ts_frame.pack(fill='x', padx=12, pady=2)
        ctk.CTkLabel(ts_frame, text="Timestamp :", font=Fonts.FONT_SMALL, fg_color=BG,
                 text_color=TEXT2).pack(side='left')
        self._ts_var = tk.StringVar(value=p.timestamp)
        ctk.CTkEntry(ts_frame, textvariable=self._ts_var, font=Fonts.FONT_SMALL,
                 fg_color=BG3, text_color=TEXT, width=120).pack(side='left', padx=8)

        # Événement
        ev_frame = ctk.CTkFrame(self, fg_color=BG)
        ev_frame.pack(fill='x', padx=12, pady=4)
        ctk.CTkLabel(ev_frame, text="Événement :", font=Fonts.FONT_SMALL, fg_color=BG,
                 text_color=TEXT2).pack(side='left')
        self._event_var = tk.StringVar(value=p.event or "routine")
        ev_menu = ctk.CTkComboBox(ev_frame, variable=self._event_var,
                               values=EVENT_TYPES, state='readonly',
                               font=Fonts.FONT_SMALL, width=120)
        ev_menu.pack(side='left', padx=8)

        # Note libre
        note_frame = tk.LabelFrame(self, text=" Note ", fg=ACCENT, bg=BG,
                                   font=Fonts.FONT_SMALL, bd=1)
        note_frame.pack(fill='x', padx=12, pady=4)
        self._note = ctk.CTkTextbox(note_frame, height=3, font=Fonts.FONT_SMALL,
                             fg_color=BG3, text_color=TEXT, wrap='word')
        self._note.pack(fill='x', padx=6, pady=6)
        if p.note:
            self._note.insert('1.0', p.note)

        # Boutons
        btn_frame = ctk.CTkFrame(self, fg_color=BG)
        btn_frame.pack(fill='x', padx=12, pady=10)
        ctk.CTkButton(btn_frame, text="✓ Enregistrer", font=Fonts.FONT_LABEL,
                  fg_color=OK, text_color=BG, command=self._save).pack(side='left', padx=4)
        ctk.CTkButton(btn_frame, text="✗ Annuler", font=Fonts.FONT_LABEL,
                  fg_color=BG3, text_color=TEXT2, command=self.destroy).pack(side='left', padx=4)

    def _save(self):
        p = LogPoint()
        p.timestamp = self._ts_var.get()
        p.event = self._event_var.get()
        p.note = self._note.get('1.0', 'end-1c')

        for attr, (var, typ) in self._nmea_vars.items():
            raw = var.get().strip()
            if raw == "" or raw == "None":
                setattr(p, attr, None)
            else:
                try:
                    setattr(p, attr, typ(raw))
                except ValueError:
                    setattr(p, attr, None)

        self.result = p
        self.destroy()


class SettingsDialog(ctk.CTkToplevel):
    """Paramètres du voyage et de l'enregistrement."""

    def __init__(self, parent, logbook: Logbook, interval_var: tk.IntVar):
        super().__init__(parent)
        self.title("Paramètres du voyage")
        self.configure(fg_color=BG)
        self.resizable(False, False)
        self.grab_set()
        self.grab_set()
        self._logbook = logbook
        self._interval_var = interval_var
        self._build()
        self.transient(parent)
        self.wait_window()

    def _build(self):
        fr = ctk.CTkFrame(self, fg_color=BG)
        fr.pack(padx=20, pady=16)

        def row(label, var, width=30):
            ctk.CTkLabel(fr, text=label, font=Fonts.FONT_SMALL, fg_color=BG, text_color=TEXT2,
                     anchor='w', width=24).pack(anchor='w', pady=(6, 0))
            e = ctk.CTkEntry(fr, textvariable=var, font=Fonts.FONT_SMALL, fg_color=BG3,
                         text_color=TEXT, width=width)
            e.pack(fill='x', pady=(0, 2))
            return e

        self._name_var = tk.StringVar(value=self._logbook.voyage_name)
        self._dist_var = tk.StringVar(value="" if self._logbook.distance_planned_nm is None
                                      else str(self._logbook.distance_planned_nm))
        self._interval_local = tk.StringVar(value=str(self._interval_var.get()))
        self._filename_var = tk.StringVar(value=str(self._logbook.filename))

        row("Nom du voyage", self._name_var)
        row("Distance ortho prévue (NM)", self._dist_var, 12)
        row("Intervalle d'enregistrement auto (min)", self._interval_local, 6)
        row("Nom du fichier de log", self._filename_var)

        ctk.CTkButton(fr, text="✓ Valider", font=Fonts.FONT_LABEL,
                  fg_color=OK, text_color=BG, command=self._save).pack(pady=(12, 0))

    def _save(self):
        name = self._name_var.get().strip()
        dist_raw = self._dist_var.get().strip()
        dist = None
        if dist_raw:
            try:
                dist = float(dist_raw)
            except ValueError:
                pass
        self._logbook.set_voyage(name, dist)
        try:
            iv = int(self._interval_local.get())
            if 1 <= iv <= 1440:
                self._interval_var.set(iv)
        except ValueError:
            pass
        if self._filename_var.get().strip() != "":
            self._logbook.filepath = self._filename_var.get().strip()
        self.destroy()


class MainWindow(ctk.CTk):
    """Fenêtre principale de l'application."""
    
    def __init__(self, nmea_mode: str = 'udp', nmea_host: str = '',
                 nmea_port: int = 2000, use_sim: bool = True):
        super().__init__()
        self.title("⚓ NaviLog")
        self.configure(fg_color=BG)
        self.minsize(1100, 800)

        Fonts.init()

        # Modèle
        self._logbook = Logbook()
        self._interval_var = tk.IntVar(value=15)

        # NMEA — UDP ou TCP selon les paramètres
        self._nmea = NMEAReceiver(mode=nmea_mode, host=nmea_host, port=nmea_port)
        self._nmea.add_callback(self._on_nmea_update)
        self._nmea_mode = nmea_mode
        self._nmea_host = nmea_host
        self._nmea_port = nmea_port

        # Enregistreurs
        self._periodic = PeriodicRecorder(
            self._logbook, self._nmea.get_snapshot,
            interval_minutes=self._interval_var.get(),
            on_new_point_fn=self._on_new_auto_point
        )
        self._auto_detect = AutoRecorder(
            self._logbook, self._nmea.get_snapshot,
            on_new_point_fn=self._on_new_auto_point
        )

        # Simulateur UDP (uniquement en mode UDP si activé)
        self._use_sim = use_sim and nmea_mode == 'udp'
        self._sim = NMEASimulator(port=nmea_port, interval=1.0)

        self._build_ui()
        self._refresh_points()
        self._start_services()
        self._tick()

    # ── Construction UI ─────────────────────────────────────────────────────

    def _build_ui(self):   
        # Barre du haut : titre + voyage
        top = ctk.CTkFrame(self, fg_color=BG)
        top.pack(fill='x', padx=0, pady=6)

        ctk.CTkLabel(top, text="⚓ NaviLog", font=Fonts.FONT_MEDIUM,
                 fg_color=BG, text_color=ACCENT).pack(side='left', padx=16)
                 
        self._voyage_label = ctk.CTkLabel(top, text="— Sans voyage —",
                                      font=Fonts.FONT_TITLE, fg_color=BG, text_color=WARN)
        self._voyage_label.pack(side='left', padx=16)

        # Boutons menu
        for label, cmd in [
            ("Nouveau", self._new_file),
            ("Ouvrir", self._open_file),
            ("Enregistrer", self._save_file),
            ("Paramètres", self._open_settings),
        ]:
            ctk.CTkButton(top, text=label, font=Fonts.FONT_SMALL, fg_color=BG3, text_color=TEXT,
                      command=cmd).pack(side='right', padx=3)

        # Indicateur de connexion NMEA
        self._nmea_status = ctk.CTkLabel(top, text="● NMEA", font=Fonts.FONT_SMALL,
                                     fg_color=BG, text_color=TEXT_DIM)
        self._nmea_status.pack(side='right', padx=8)

        sep = ctk.CTkFrame(self, fg_color=BG3, height=1)
        sep.pack(fill='x')

        # Jauge NMEA temps réel
        gauge_frame = ctk.CTkFrame(self, fg_color=BG)
        gauge_frame.pack(fill='x', padx=8, pady=4)
        self._gauge = NMEAGauge(gauge_frame)
        self._gauge.pack(fill='x')

        sep2 = ctk.CTkFrame(self, fg_color=BG3, height=1)
        sep2.pack(fill='x')

        # Contenu principal : stats à gauche, liste à droite
        main = ctk.CTkFrame(self, fg_color=BG)
        main.pack(fill='both', expand=True, padx=0)

        # Panneau stats gauche
        left = ctk.CTkFrame(main, fg_color=BG, width=200)
        left.pack(side='left', fill='y', padx=8, pady=8)
        left.pack_propagate(False)
        self._build_stats_panel(left)

        sep3 = ctk.CTkFrame(main, fg_color=BG3, width=1)
        sep3.pack(side='left', fill='y')

        # Panneau points droite
        right = ctk.CTkFrame(main, fg_color=BG)
        right.pack(side='left', fill='both', expand=True, padx=8, pady=8)
        self._build_points_panel(right)

    def _build_stats_panel(self, parent):
        ctk.CTkLabel(parent, text="STATISTIQUES", font=Fonts.FONT_SMALL, fg_color=BG,
                 text_color=TEXT_DIM).pack(anchor='w', pady=(0, 6))

        def stat(label, unit=""):
            b = StatBox(parent, label, unit)
            b.pack(fill='x', pady=3)
            return b

        self._sb_planned  = stat("Ortho prévue", " NM")
        self._sb_dist     = stat("Distance parcourue", " NM")
        self._sb_time     = stat("Temps écoulé")
        self._sb_aws_range = stat("Vent app. min / max", " kn")
        self._sb_sog_range = stat("SOG min / max", " kn")
        self._sb_sog_avg  = stat("SOG moy. 1h", " kn")

        # Position actuelle
        ctk.CTkLabel(parent, text="POSITION", font=Fonts.FONT_SMALL, fg_color=BG,
                 text_color=TEXT_DIM).pack(anchor='w', pady=(16, 0))
        self._pos_label = ctk.CTkLabel(parent, text="— —", font=Fonts.FONT_LABEL,
                                   fg_color=BG, text_color=TEXT2)
        self._pos_label.pack(anchor='w')
        self._time_label = ctk.CTkLabel(parent, text="", font=Fonts.FONT_SMALL,
                                    fg_color=BG, text_color=TEXT_DIM)
        self._time_label.pack(anchor='w')

    def _build_points_panel(self, parent):
        hdr = ctk.CTkFrame(parent, fg_color=BG)
        hdr.pack(fill='x')
        ctk.CTkLabel(hdr, text="POINTS ENREGISTRÉS", font=Fonts.FONT_SMALL,
                 fg_color=BG, text_color=TEXT_DIM).pack(side='left')

        for label, cmd in [
            ("+ Nouveau point", self._new_point),
            ("✎ Modifier", self._edit_point),
            ("🗑 Supprimer", self._delete_point),
        ]:
            ctk.CTkButton(hdr, text=label, font=Fonts.FONT_SMALL, fg_color=BG3, text_color=TEXT,
                      command=cmd).pack(side='right', padx=2)

        # Filtre
        filter_frame = ctk.CTkFrame(parent, fg_color=BG)
        filter_frame.pack(fill='x', pady=4)
        
        # menu déroulant pour filtrer par évènement (à améliorer pour pouvoir en choisir plusieurs)
        ctk.CTkLabel(filter_frame, text="Filtre événement :", font=Fonts.FONT_SMALL,
                 fg_color=BG, text_color=TEXT2).pack(side='left')
        self._filter_var = ctk.StringVar(value="tous")
        filter_menu = ctk.CTkComboBox(filter_frame, variable=self._filter_var,
                                   values=["tous"] + EVENT_TYPES, state='readonly',
                                   font=Fonts.FONT_SMALL, width=120, command=self._refresh_points)
        filter_menu.pack(side='left', padx=6)

        # checkbox pour masquer ou non les points automatiques
        self._show_auto_var = ctk.StringVar(value="show")
        checkbox_show_auto = ctk.CTkCheckBox(filter_frame, text="Montrer points auto",
                                             command=self._refresh_points, variable= self._show_auto_var, onvalue="show", offvalue="hide")
        checkbox_show_auto.pack(side='left', padx=6)

        # Liste
        list_frame = ctk.CTkFrame(parent, fg_color=BG)
        list_frame.pack(fill='both', expand=True)

        style = ttk.Style()
        style.theme_use('clam')
        style.configure("Log.Treeview",
                         background=BG2, foreground=TEXT,
                         fieldbackground=BG2, rowheight=24,
                         font=Fonts.FONT_SMALL)
        style.configure("Log.Treeview.Heading",
                         background=BG3, foreground=ACCENT2,
                         font=Fonts.FONT_SMALL)
        style.map("Log.Treeview",
                  background=[('selected', BG3)],
                  foreground=[('selected', ACCENT)])

        cols = ("time", "sog", "cog", "awa", "aws", "event", "note")

        self._tree = ttk.Treeview(list_frame, columns=cols, show='headings',
                                   style="Log.Treeview", selectmode='browse')

        headers = {
            "time": ("Date/Heure", 110),
            "sog": ("SOG kn", 70),
            "cog": ("COG°", 60),
            "awa": ("AWA°", 60),
            "aws": ("AWS kn", 70),
            "event": ("Événement", 90),
            "note": ("Note", 250),
        }
        for col, (text, width) in headers.items():
            self._tree.heading(col, text=text)
            self._tree.column(col, width=width, anchor='center')
        self._tree.column("note", anchor='w')

        sb = ctk.CTkScrollbar(list_frame, orientation='vertical',
                           command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')

        self._tree.bind('<Double-1>', lambda e: self._edit_point())

        # Barre de statut
        self._status_var = tk.StringVar(value="Prêt.")
        ctk.CTkLabel(parent, textvariable=self._status_var, font=Fonts.FONT_SMALL,
                 fg_color=BG, text_color=TEXT_DIM, anchor='w').pack(fill='x', pady=(4, 0))

    # ── Services ─────────────────────────────────────────────────────────────

    def _start_services(self):
        if self._use_sim:
            self._sim.start()
        self._nmea.start()
        self._periodic.start()
        self._auto_detect.start()

    # ── Callbacks NMEA ────────────────────────────────────────────────────────

    def _on_nmea_update(self):
        # Appelé depuis le thread NMEA — on schedule dans le thread UI
        self.after(0, self._refresh_nmea_ui)

    def _refresh_nmea_ui(self):
        snap = self._nmea.get_snapshot()
        avgs = self._compute_gauge_avgs()
        self._gauge.update_from_nmea(snap, avgs)
        # Position
        if snap.lat and snap.lon:
            lat_s = f"{'N' if snap.lat >= 0 else 'S'} {abs(snap.lat):.4f}°"
            lon_s = f"{'E' if snap.lon >= 0 else 'W'} {abs(snap.lon):.4f}°"
            self._pos_label.configure(text=f"{lat_s}  {lon_s}")
        self._time_label.configure(text=snap.time_utc)
        # Indicateur NMEA : couleur selon fraîcheur des données
        age = time.time() - snap.last_update
        color = OK if age < 5 else (WARN if age < 30 else RED)
        if self._nmea_mode == 'tcp':
            conn = "TCP ✓" if self._nmea.is_connected else "TCP …"
            self._nmea_status.configure(text=f"● {conn}", text_color=color)
        else:
            self._nmea_status.configure(text="● UDP", text_color=color)

    def _compute_gauge_avgs(self) -> dict:
        """Calcule la moyenne de chaque paramètre sur les points de la dernière heure."""
        from datetime import datetime
        now = datetime.now().astimezone()
        keys = {
            'SOG': 'sog', 'COG': 'cog', 'AWA': 'awa', 'AWS': 'aws',
            'TWD': 'twd', 'TWA': 'twa', 'TWS': 'tws',
        }
        buckets = {k: [] for k in keys}
        for p in self._logbook.points:
            try:
                pt = datetime.fromisoformat(p.timestamp)
                if (now - pt).total_seconds() <= 3600:
                    for gauge_key, attr in keys.items():
                        val = getattr(p, attr)
                        if val is not None:
                            buckets[gauge_key].append(val)
            except Exception:
                pass
        return {k: (sum(v) / len(v)) for k, v in buckets.items() if v}

    def _on_new_auto_point(self, point: LogPoint):
        self.after(0, self._refresh_points)
        self.after(0, lambda: self._status("Point auto enregistré."))

    # ── Rafraîchissement UI ──────────────────────────────────────────────────

    def _tick(self):
        """Rafraîchi toutes les 5 secondes."""
        self._refresh_stats()
        self.after(5000, self._tick)

    def _refresh_stats(self):
        stats = self._logbook.get_stats()
        self._sb_dist.set(f"{stats.distance_nm:.2f} NM")
        self._sb_planned.set(
            f"{self._logbook.distance_planned_nm:.0f} NM"
            if self._logbook.distance_planned_nm else "—"
        )
        self._sb_time.set(stats.elapsed_str() if stats.elapsed_seconds else "—")

        aws_min = _fmt_float(stats.aws_min, 1) if stats.aws_min is not None else "—"
        aws_max = _fmt_float(stats.aws_max, 1) if stats.aws_max is not None else "—"
        self._sb_aws_range.set(f"{aws_min} / {aws_max} kn")

        sog_min = _fmt_float(stats.sog_min, 2) if stats.sog_min is not None else "—"
        sog_max = _fmt_float(stats.sog_max, 2) if stats.sog_max is not None else "—"
        self._sb_sog_range.set(f"{sog_min} / {sog_max} kn")

        self._sb_sog_avg.set_float(stats.sog_avg_last_hour, 2, " kn")

        # Voyage
        vn = self._logbook.voyage_name or "— Sans voyage —"
        self._voyage_label.configure(text=vn)
        title = f"⚓ {vn}" if self._logbook.voyage_name else "⚓ NaviLog"
        if self._logbook.is_dirty:
            title += " *"
        self.title(title)

    def _refresh_points(self, discard=""):
        filter_ev = self._filter_var.get()
        show_auto = self._show_auto_var.get()
        self._tree.delete(*self._tree.get_children())
        for i, p in enumerate(self._logbook.points):
            if (filter_ev != "tous" and p.event != filter_ev) or (show_auto != "show" and p.auto == 1):
                continue
            auto_mark = "●" if p.auto else ""
            self._tree.insert('', 'end', iid=str(i), values=(
                p.display_time(),
                _fmt_float(p.sog, 2),
                _fmt_float(p.cog, 0),
                _fmt_float(p.awa, 0),
                _fmt_float(p.aws, 1),
                p.event,
                p.note[:50] if p.note else "",
                auto_mark,
            ), tags=('auto',) if p.auto else ())
        self._tree.tag_configure('auto', foreground=TEXT_DIM)
        self._status(f"{len(self._logbook.points)} point(s) enregistré(s).")
        self._refresh_stats()

    def _status(self, msg: str):
        self._status_var.set(msg)

    # ── Actions points ────────────────────────────────────────────────────────

    def _new_point(self):
        snap = self._nmea.get_snapshot()
        from datetime import datetime as dt
        pre = LogPoint.from_nmea(snap, event="routine", note="", auto=False)
        if not pre.timestamp:
            pre.timestamp = dt.now().astimezone().isoformat(timespec='seconds')
        dlg = PointDialog(self, point=pre, title="Nouveau point")
        if dlg.result:
            self._logbook.add_point(dlg.result)
            self._refresh_points()

    def _edit_point(self):
        sel = self._tree.selection()
        if not sel:
            tk.messagebox.showinfo("Info", "Sélectionnez un point à modifier.")
            return
        idx = int(sel[0])
        dlg = PointDialog(self, point=self._logbook.points[idx], title="Modifier le point")
        if dlg.result:
            self._logbook.update_point(idx, dlg.result)
            self._refresh_points()

    def _delete_point(self):
        sel = self._tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        if tk.messagebox.askyesno("Confirmer", "Supprimer ce point ?"):
            self._logbook.delete_point(idx)
            self._refresh_points()

    # ── Fichiers ──────────────────────────────────────────────────────────────

    def _new_file(self):
        if self._logbook.is_dirty:
            if not tk.messagebox.askyesno("Non sauvegardé",
                                       "Des modifications non sauvegardées. Continuer ?"):
                return
        path = tk.filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("Tous", "*.*")],
            title="Nouveau carnet de bord"
        )
        if path:
            self._logbook.new_file(path)
            self._open_settings()
            self._refresh_points()

    def _open_file(self):
        if self._logbook.is_dirty:
            if not tk.messagebox.askyesno("Non sauvegardé",
                                       "Des modifications non sauvegardées. Continuer ?"):
                return
        path = tk.filedialog.askopenfilename(
            filetypes=[("JSON", "*.json"), ("Tous", "*.*")],
            title="Ouvrir un carnet de bord"
        )
        if path:
            try:
                self._logbook.load(path)
                self._refresh_points()
                self._status(f"Fichier chargé : {self._logbook.filename}")
            except Exception as e:
                tk.messagebox.showerror("Erreur", f"Impossible de charger le fichier :\n{e}")

    def _save_file(self):
        path = self._logbook.filepath
        if not path:
            path = tk.filedialog.asksaveasfilename(
                defaultextension=".json",
                filetypes=[("JSON", "*.json")],
                title="Enregistrer sous…"
            )
            if not path:
                return
            else:
                self._logbook.filepath = path
        try:
            self._logbook.save(path)
            self._status(f"Sauvegardé : {self._logbook.filename}")
        except Exception as e:
            tk.messagebox.showerror("Erreur", f"Impossible de sauvegarder :\n{e}")

    def _open_settings(self):
        SettingsDialog(self, self._logbook, self._interval_var)
        self._periodic.set_interval(self._interval_var.get())
        self._refresh_stats()

    def on_close(self):
        if self._logbook.is_dirty:
            if tk.messagebox.askyesno("Quitter", "Sauvegarder avant de quitter ?"):
                self._save_file()
        self._nmea.stop()
        if self._use_sim:
            self._sim.stop()
        self._periodic.stop()
        self._auto_detect.stop()
        self.destroy()

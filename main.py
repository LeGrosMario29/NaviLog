# Livre de Bord Nautique
# Copyright (C) 2026  [LeGrosMario]
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License.
#
# https://www.gnu.org/licenses/gpl-3.0.html

"""
main.py
Point d'entrée du Livre de Bord nautique.

Exemples d'utilisation :
    python main.py                              # simulateur NMEA intégré (UDP 2000)
    python main.py --no-sim                     # flux UDP réel sur le port 2000
    python main.py --no-sim --port 10110        # flux UDP sur un port différent
    python main.py --tcp 192.168.76.1 10110     # flux TCP (multiplexeur WiFi, etc.)
    python main.py --tcp 192.168.76.1           # TCP port par défaut 10110
"""

import sys
import argparse

# ── Parse des arguments CLI ─────────────────────────────────────────────────
parser = argparse.ArgumentParser(
    description="Livre de Bord nautique NMEA",
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog="""
Exemples :
  python main.py                           simulateur intégré (test sans bateau)
  python main.py --no-sim                  UDP port 2000 (centrale broadcast)
  python main.py --no-sim --port 10110     UDP port 10110
  python main.py --tcp 192.168.76.1        TCP 192.168.76.1:10110 (iKommunicate…)
  python main.py --tcp 192.168.76.1 2000   TCP 192.168.76.1:2000
"""
)
parser.add_argument('--no-sim', action='store_true',
                    help="Désactive le simulateur NMEA interne")
parser.add_argument('--port', type=int, default=2000,
                    help="Port UDP local (défaut: 2000, ignoré si --tcp)")
parser.add_argument('--tcp', nargs='+', metavar=('HOST', 'PORT'),
                    help="Mode TCP : --tcp <host> [port]  (port défaut: 10110)")
args = parser.parse_args()

# ── Résolution du mode et des paramètres réseau ─────────────────────────────
if args.tcp:
    mode = 'tcp'
    host = args.tcp[0]
    port = int(args.tcp[1]) if len(args.tcp) >= 2 else 10110
    use_sim = False   # le simulateur envoie en UDP local, inutile en mode TCP
else:
    mode = 'udp'
    host = ''
    port = args.port
    use_sim = not args.no_sim

# ── Lancement UI ─────────────────────────────────────────────────────────────
from ui_main import MainWindow

app = MainWindow(nmea_mode=mode, nmea_host=host, nmea_port=port, use_sim=use_sim)

if mode == 'tcp':
    print(f"[INFO] Mode TCP — connexion vers {host}:{port}")
else:
    if use_sim:
        print(f"[INFO] Mode UDP — simulateur actif sur 127.0.0.1:{port}")
    else:
        print(f"[INFO] Mode UDP — en attente du flux NMEA sur le port {port}")

app.protocol("WM_DELETE_WINDOW", app.on_close)
app.mainloop()

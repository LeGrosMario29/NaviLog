# NaviLog — Livre de bord électronique

Application Python/CustomTkinter de carnet de bord pour voilier, avec réception NMEA via UDP ou TCP.
Attention en TCP un seul client possible donc pas de cohabitation avec QtVLM ou OpenCPN.
Dans ce cas prévoir un multiplexage ou astuce équivalente (kplex ou socat par exemple).

## Prérequis

```bash
pip install customtkinter
```

Python 3.10+ requis (typage union `X | Y`).

## Lancement

```bash
# Avec simulateur NMEA intégré (pour tester sans bateau)
python main.py

# Avec flux NMEA réel (centrale de navigation → UDP port 2000)
python main.py --no-sim

# Flux NMEA sur un port différent
python main.py --no-sim --port xyz

# Avec flux NMEA réel (centrale de navigation → TCP port 10110 par défaut)
python main.py --no-sim --tcp <host> [port]
```

## Fonctionnalités

### Réception NMEA (UDP)
- Trames supportées : `RMC`, `GGA`, `VTG`, `MWV` (vent apparent/vrai), `MWD`, `HDG/HDM/HDT`
- Données extraites : position (lat/lon), heure UTC, SOG, COG, AWA, AWS, TWD, TWA, TWS

### Enregistrement automatique
- **Périodique** : toutes les N minutes (réglable, défaut 15 min)
- **Sur changement** : détection de changements significatifs sur cap (>20°), vitesse (>1,5 kn), vent apparent (>25°/3 kn)

### Points du carnet
- Création manuelle pré-remplie avec les données NMEA en cours
- Différentes catégories : `routine`, `virement`, `météo`, `moteur+`, `moteur-`, `voile`, `HydroG+`, `HydroG-`, `VàB`, `radio`, `MOB`, `AIS`, `ASN`
- Champ note libre
- Édition/suppression de chaque point
- Filtre par catégorie d'événement

### Tableau de bord
- Distance parcourue (haversine sur les points GPS)
- Temps écoulé
- Vent apparent min/max
- SOG min/max/moyenne dernière heure
- Distance ortho prévue (saisie au démarrage)

### Persistance
- Format JSON lisible/éditable
- Ouvrir un voyage passé pour modification
- Sauvegarde manuelle ou automatique

## Structure des fichiers

```
logbook/
├── main.py           # Point d'entrée + arguments CLI
├── ui_main.py        # Fenêtre principale, dialogs
├── logbook.py        # Modèle données, statistiques, enregistreurs
├── nmea_receiver.py  # Réception UDP, parsing NMEA, simulateur
└── README.md
```

## Format JSON

```json
{
  "voyage_name": "Marseille → Ajaccio",
  "distance_planned_nm": 185.0,
  "created": "2024-07-15T08:00:00+02:00",
  "points": [
    {
      "timestamp": "2024-07-15T08:00:00+02:00",
      "time_utc": "06:00:00 UTC",
      "lat": 43.2965,
      "lon": 5.3811,
      "cog": 185.0,
      "sog": 6.2,
      "awa": 45.0,
      "aws": 14.0,
      "twd": 210.0,
      "twa": 25.0,
      "tws": 11.0,
      "event": "voile",
      "note": "Grand large, brise établie",
      "auto": false
    }
  ]
}
```

## Configuration réseau de la centrale

Configurer la centrale de navigation (ex. B&G, Garmin, Raymarine, Navionics) pour émettre
les trames NMEA 0183 en UDP unicast ou broadcast vers l'adresse IP du PC, port 2000.

Sur certaines centrales, le multicast 239.x.x.x est également supporté — dans ce cas,
adapter `nmea_receiver.py` pour rejoindre le groupe multicast.

Si TCP uniquement disponible sur la centrale de navigation (ex. B&G), et si utilisation conjointe avec un autre logiciel type QtVLM ou OpenCPN, prévoir de dupliquer le flux TCP.
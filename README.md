# Denon HEOS Controller Web App + PC Audio Bridge

Diese App läuft auf deinem Windows-PC als lokaler Webserver und steuert deinen Denon AVR über HEOS/AVR TCP. Zusätzlich gibt es eine **PC Audio Bridge**.

Wichtig: Der PC wird damit **nicht zu einem echten HEOS-Lautsprecher**. HEOS-Lautsprecher/Player sind proprietär. Die Bridge ist der praktische Weg: VLC, Stream-URLs oder externe AirPlay/DLNA/RTP-Receiver werden über die Weboberfläche gestartet/bedient.

## Start

1. ZIP entpacken
2. `scripts/install.bat` ausführen
3. `scripts/start_web.bat` ausführen
4. Browser öffnen:
   - auf dem PC: `http://127.0.0.1:5050`
   - im WLAN: `http://DEINE-PC-IP:5050`

Deine PC-IP zeigt dir `scripts/show_my_ip.bat`.

## Denon verbinden

In der Webseite:

1. Denon-IP eintragen
2. Speichern
3. Status prüfen

HEOS-Port: `1255`  
AVR-Port: `23`

## PC Audio Bridge

Die Bridge kann:

- Stream-URL am PC öffnen
- VLC automatisch starten, falls installiert
- optional externe AirPlay-/DLNA-Receiver-Programme starten
- Status für PC-IP, PC-Name und VLC anzeigen

Empfohlen:

1. VLC installieren
2. In der Webseite unter **PC Audio Bridge** den VLC-Pfad eintragen, falls er nicht automatisch erkannt wird:
   `C:\Program Files\VideoLAN\VLC\vlc.exe`
3. Stream-URL eintragen
4. **Am PC abspielen** drücken

## Was damit nicht geht

Der Denon AVR kann seinen kompletten HDMI-/TV-/AVR-Ton normalerweise nicht einfach per HEOS an einen beliebigen Windows-PC senden. Dafür brauchst du je nach Ziel:

- HDMI Audio Capture
- USB-Audio-Interface
- AirPlay/DLNA/RTP Bridge
- professionell: Dante Virtual Soundcard

## Projektstruktur

```text
denon_heos_controller/
├── app/
│   ├── audio_bridge.py
│   ├── heos_client.py
│   ├── routes.py
│   ├── templates/index.html
│   └── static/
├── config/settings.json
├── scripts/
│   ├── install.bat
│   ├── start_web.bat
│   ├── show_my_ip.bat
│   └── open_firewall_port_5050_admin.bat
├── requirements.txt
└── run.py
```

## Fehlerbehebung: TimeoutError Port 1255

Wenn beim Drücken von Play ein `TimeoutError` erscheint, erreicht der PC den Denon nicht über HEOS-Port 1255.

1. Prüfe die Denon-IP in der Weboberfläche.
2. Starte `scripts/test_denon_ports.bat`.
3. Prüfe im Denon-Menü: Netzwerk / Netzwerksteuerung / Network Control = Always On bzw. Immer aktiv.
4. PC und Denon müssen im gleichen Netzwerk/WLAN/VLAN sein.
5. Teste in PowerShell:

```powershell
Test-NetConnection DEINE_DENON_IP -Port 1255
Test-NetConnection DEINE_DENON_IP -Port 23
```

Die App stürzt ab dieser Version bei Timeouts nicht mehr ab, sondern gibt eine Diagnose im Ausgabefeld zurück.

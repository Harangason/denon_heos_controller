import json
import socket
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
settings = json.loads((ROOT / 'config' / 'settings.json').read_text(encoding='utf-8'))
ip = settings.get('denon_ip')
timeout = float(settings.get('socket_timeout_seconds', 3))
ports = [('HEOS', int(settings.get('heos_port', 1255))), ('AVR', int(settings.get('avr_port', 23)))]
print(f'Denon-IP: {ip}')
for name, port in ports:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            print(f'[OK] {name} Port {port} erreichbar')
    except Exception as exc:
        print(f'[FEHLER] {name} Port {port} nicht erreichbar: {type(exc).__name__}: {exc}')
print('\nWenn beide Ports fehlschlagen: IP falsch, anderes WLAN/VLAN, Denon aus, oder Network Control/Netzwerksteuerung am Denon nicht aktiv.')
print('Wenn nur HEOS 1255 fehlschlägt: HEOS-Modul/Modell/Port blockiert oder Denon unterstützt HEOS CLI so nicht.')

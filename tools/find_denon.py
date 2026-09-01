from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.discovery import discover_denon_devices  # noqa: E402


if __name__ == "__main__":
    result = discover_denon_devices()
    print(f"Netze: {', '.join(result['networks'])}")
    if not result["devices"]:
        print("Kein Gerät mit HEOS/AVR/Web-Port gefunden.")
    for device in result["devices"]:
        print(f"{device['ip']}  offene Ports: {device['open_ports']}  Treffer: {device['score']}  {device['kind']}")

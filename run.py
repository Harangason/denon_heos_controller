import json
import socket
from pathlib import Path

from waitress import serve
from app import create_app

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config" / "settings.json"


def local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def load_server_settings():
    with CONFIG.open("r", encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg.get("web_host", "0.0.0.0"), int(cfg.get("web_port", 5050))


app = create_app()

if __name__ == "__main__":
    host, port = load_server_settings()
    lan_ip = local_ip()
    print("=" * 60)
    print("Denon HEOS Controller läuft")
    print(f"Dieser PC:     http://127.0.0.1:{port}")
    print(f"Im WLAN/LAN:   http://{lan_ip}:{port}")
    print("Hinweis: Windows-Firewall muss Python für private Netzwerke erlauben.")
    print("=" * 60)
    serve(app, host=host, port=port)

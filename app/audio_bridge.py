"""PC Audio Bridge helpers.

This module does not emulate a real HEOS speaker. HEOS playback devices are
proprietary. The bridge provides pragmatic Windows integration points:
- open a stream URL in VLC/Windows default player
- start optional external receiver tools if the user installs them
- expose status and setup hints to the web UI
"""
from __future__ import annotations

import os
import json
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Dict

from .heos_client import load_settings, save_settings

RUNTIME_DIR = Path(__file__).resolve().parents[1] / "runtime"
VLC_STATE_FILE = RUNTIME_DIR / "vlc_state.json"


def local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def detect_vlc() -> str | None:
    candidates = [
        shutil.which("vlc"),
        r"C:\Program Files\VideoLAN\VLC\vlc.exe",
        r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
    ]
    for path in candidates:
        if path and Path(path).exists():
            return str(path)
    return None


def _bridge_settings() -> Dict[str, Any]:
    return load_settings().get("audio_bridge", {})


def _read_vlc_state() -> Dict[str, Any]:
    if not VLC_STATE_FILE.exists():
        return {}
    try:
        return json.loads(VLC_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_vlc_state(state: Dict[str, Any]) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    VLC_STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _is_pid_running(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        return f'"{pid}"' in result.stdout or f",{pid}," in result.stdout
    except Exception:
        return False


def _vlc_rc_target() -> tuple[str, int]:
    bridge = _bridge_settings()
    host = str(bridge.get("vlc_rc_host") or "127.0.0.1").strip()
    try:
        port = int(bridge.get("vlc_rc_port") or 4212)
    except (TypeError, ValueError):
        port = 4212
    return host, max(1, min(65535, port))


def _send_vlc_rc(command: str) -> Dict[str, Any]:
    host, port = _vlc_rc_target()
    try:
        with socket.create_connection((host, port), timeout=1.5) as sock:
            sock.sendall((command.strip() + "\n").encode("utf-8"))
            sock.settimeout(0.5)
            chunks = []
            while True:
                try:
                    data = sock.recv(4096)
                except socket.timeout:
                    break
                if not data:
                    break
                chunks.append(data)
        response = b"".join(chunks).decode("utf-8", errors="ignore").strip()
        return {"ok": True, "command": command, "response": response}
    except Exception as exc:
        return {
            "ok": False,
            "error": type(exc).__name__,
            "message": str(exc),
            "hint": "VLC muss von dieser App gestartet worden sein, damit die lokale RC-Steuerung aktiv ist.",
        }


def vlc_status() -> Dict[str, Any]:
    bridge = _bridge_settings()
    vlc_path = str(bridge.get("vlc_path") or detect_vlc() or "").strip()
    state = _read_vlc_state()
    pid = state.get("pid")
    running = _is_pid_running(int(pid)) if pid else False
    host, port = _vlc_rc_target()
    return {
        "ok": True,
        "installed": bool(vlc_path and Path(vlc_path).exists()),
        "running": running,
        "pid": pid if running else None,
        "vlc_path": vlc_path,
        "rc_host": host,
        "rc_port": port,
        "last_url": state.get("url", ""),
        "started_at": state.get("started_at", ""),
    }


def status() -> Dict[str, Any]:
    settings = load_settings()
    vlc = vlc_status()
    return {
        "ok": True,
        "mode": settings.get("audio_bridge", {}).get("mode", "manual"),
        "pc_name": socket.gethostname(),
        "pc_ip": local_ip(),
        "vlc_path": vlc.get("vlc_path"),
        "vlc": vlc,
        "note": "PC ist kein echter HEOS-Lautsprecher. Die Bridge nutzt VLC, AirPlay/DLNA/RTP-Hilfsprogramme oder Stream-URLs.",
    }


def update_bridge_settings(data: Dict[str, Any]) -> Dict[str, Any]:
    settings = load_settings()
    bridge = settings.setdefault("audio_bridge", {})
    for key in [
        "mode",
        "vlc_path",
        "default_stream_url",
        "vlc_rc_host",
        "vlc_rc_port",
        "vlc_volume",
        "airplay_tool_path",
        "dlna_tool_path",
        "rtp_port",
    ]:
        if key in data and data[key] is not None:
            bridge[key] = data[key]
    save_settings(settings)
    return settings


def open_stream(url: str) -> Dict[str, Any]:
    return start_vlc_stream(url)


def start_vlc_stream(url: str) -> Dict[str, Any]:
    url = str(url or "").strip()
    if not url:
        return {"ok": False, "error": "Keine Stream-URL angegeben"}
    settings = load_settings()
    bridge = settings.get("audio_bridge", {})
    vlc_path = str(bridge.get("vlc_path") or detect_vlc() or "").strip()
    host, port = _vlc_rc_target()
    volume = bridge.get("vlc_volume", 160)
    try:
        volume = max(0, min(320, int(volume)))
    except (TypeError, ValueError):
        volume = 160
    try:
        if vlc_path:
            process = subprocess.Popen(
                [
                    vlc_path,
                    url,
                    "--extraintf",
                    "rc",
                    "--rc-host",
                    f"{host}:{port}",
                    "--qt-start-minimized",
                    "--no-video-title-show",
                    "--volume",
                    str(volume),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _write_vlc_state({"pid": process.pid, "url": url, "started_at": time.strftime("%Y-%m-%d %H:%M:%S")})
            return {"ok": True, "player": "VLC", "url": url, "pid": process.pid, "rc_port": port}
        os.startfile(url)  # type: ignore[attr-defined]
        return {"ok": True, "player": "Windows default", "url": url}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "url": url}


def vlc_command(command: str, value: Any = None) -> Dict[str, Any]:
    allowed = {"play": "play", "pause": "pause", "stop": "stop", "next": "next", "previous": "prev", "quit": "quit"}
    if command == "volume":
        try:
            volume = max(0, min(320, int(value)))
        except (TypeError, ValueError):
            return {"ok": False, "error": "Ungültige VLC-Lautstärke"}
        return _send_vlc_rc(f"volume {volume}")
    rc_command = allowed.get(command)
    if not rc_command:
        return {"ok": False, "error": "Unbekannter VLC-Befehl"}
    return _send_vlc_rc(rc_command)


def stop_vlc() -> Dict[str, Any]:
    quit_result = vlc_command("quit")
    state = _read_vlc_state()
    pid = state.get("pid")
    if pid and _is_pid_running(int(pid)):
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True, timeout=5, check=False)
        except Exception:
            pass
    _write_vlc_state({})
    return {"ok": True, "message": "VLC wurde gestoppt.", "rc": quit_result}


def start_external(kind: str) -> Dict[str, Any]:
    settings = load_settings()
    bridge = settings.get("audio_bridge", {})
    key = {"airplay": "airplay_tool_path", "dlna": "dlna_tool_path"}.get(kind)
    if not key:
        return {"ok": False, "error": "Unbekannter Bridge-Typ"}
    tool_path = str(bridge.get(key) or "").strip()
    if not tool_path:
        return {"ok": False, "error": f"Kein Pfad für {kind} Tool konfiguriert"}
    if not Path(tool_path).exists():
        return {"ok": False, "error": f"{kind} Tool nicht gefunden", "path": tool_path}
    try:
        subprocess.Popen([tool_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"ok": True, "started": kind, "path": tool_path}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "path": tool_path}

import json
import socket
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, quote

ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILE = ROOT / "config" / "settings.json"
DEFAULT_SETTINGS: Dict[str, Any] = {
    "denon_ip": "",
    "heos_port": 1255,
    "avr_port": 23,
    "socket_timeout_seconds": 3,
    "web_host": "0.0.0.0",
    "web_port": 5050,
    "audio_bridge": {
        "mode": "manual",
        "vlc_path": "",
        "default_stream_url": "",
        "vlc_rc_host": "127.0.0.1",
        "vlc_rc_port": 4212,
        "vlc_volume": 160,
        "airplay_tool_path": "",
        "dlna_tool_path": "",
        "rtp_port": 5004,
    },
    "ui": {
        "active_tab": "daily",
        "selected_player_id": "",
        "default_heos_input": "inputs/tvaudio",
        "favorite_preset": 1,
        "live_enabled": True,
        "live_interval_seconds": 5,
    },
}


def _merged_settings(raw: Dict[str, Any]) -> Dict[str, Any]:
    settings = {**DEFAULT_SETTINGS, **raw}
    settings["audio_bridge"] = {
        **DEFAULT_SETTINGS["audio_bridge"],
        **raw.get("audio_bridge", {}),
    }
    settings["ui"] = {
        **DEFAULT_SETTINGS["ui"],
        **raw.get("ui", {}),
    }
    return settings


def load_settings() -> Dict[str, Any]:
    if not CONFIG_FILE.exists():
        save_settings(DEFAULT_SETTINGS)
        return _merged_settings({})
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as file:
            raw = json.load(file)
    except (OSError, json.JSONDecodeError):
        return _merged_settings({})
    return _merged_settings(raw if isinstance(raw, dict) else {})


def save_settings(settings: Dict[str, Any]) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")


class DenonHeosClient:
    def __init__(self) -> None:
        self.settings = load_settings()
        self.ip = str(self.settings.get("denon_ip", "")).strip()
        self.heos_port = int(self.settings.get("heos_port", 1255))
        self.avr_port = int(self.settings.get("avr_port", 23))
        self.timeout = float(self.settings.get("socket_timeout_seconds", 3))

    def _error(self, port: int, command: str, exc: Exception) -> Dict[str, Any]:
        return {
            "ok": False,
            "error": type(exc).__name__,
            "message": str(exc),
            "ip": self.ip,
            "port": port,
            "command": command,
            "hint": (
                "Denon-IP prüfen, AVR/HEOS muss im gleichen Netzwerk sein, "
                "Port 1255 für HEOS und Port 23 für AVR testen. "
                "Am Denon Netzwerksteuerung/Network Control auf Always On stellen."
            ),
        }

    def _missing_ip(self) -> Dict[str, Any]:
        return {
            "ok": False,
            "error": "NoIpConfigured",
            "message": "Keine Denon-IP konfiguriert.",
            "hint": "Trage die IP-Adresse deines Denon AVR ein und speichere die Verbindung.",
        }

    def _send_raw(self, port: int, command: str, line_end: str = "\r\n", buffer: int = 65535) -> Dict[str, Any]:
        if not self.ip:
            return self._missing_ip()
        try:
            with socket.create_connection((self.ip, port), timeout=self.timeout) as sock:
                sock.sendall((command + line_end).encode("utf-8"))
                sock.settimeout(self.timeout)
                chunks = []
                while True:
                    try:
                        data = sock.recv(buffer)
                    except socket.timeout:
                        break
                    if not data:
                        break
                    chunks.append(data)
                    if len(data) < buffer:
                        break
                raw = b"".join(chunks).decode("utf-8", errors="ignore")
                return {"ok": True, "raw": raw, "ip": self.ip, "port": port, "command": command}
        except Exception as exc:
            return self._error(port, command, exc)

    def send_heos(self, command: str) -> Dict[str, Any]:
        sent = self._send_raw(self.heos_port, command, "\r\n")
        if not sent.get("ok"):
            return sent
        raw = sent.get("raw", "")
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        if not lines:
            return {**sent, "ok": False, "error": "NoHeosResponse", "message": "Keine HEOS Antwort erhalten"}
        for line in lines:
            try:
                data = json.loads(line)
                data.setdefault("ok", data.get("heos", {}).get("result") == "success")
                message = data.get("heos", {}).get("message", "")
                if message:
                    data["message_fields"] = dict(parse_qsl(message, keep_blank_values=True))
                return data
            except json.JSONDecodeError:
                continue
        return {**sent, "ok": False, "error": "InvalidJson", "message": "HEOS Antwort war kein JSON"}

    def send_avr(self, command: str) -> Dict[str, Any]:
        sent = self._send_raw(self.avr_port, command, "\r", buffer=2048)
        if not sent.get("ok"):
            return sent
        return {"ok": True, "raw": sent.get("raw", "").strip(), "command": command, "ip": self.ip, "port": self.avr_port}

    def send_avr_batch(self, commands: List[str], collect_seconds: float = 1.2) -> Dict[str, Any]:
        if not self.ip:
            return self._missing_ip()
        try:
            with socket.create_connection((self.ip, self.avr_port), timeout=self.timeout) as sock:
                sock.settimeout(0.2)
                for command in commands:
                    sock.sendall((command + "\r").encode("utf-8"))
                    time.sleep(0.08)
                chunks = []
                end = time.time() + collect_seconds
                while time.time() < end:
                    try:
                        data = sock.recv(4096)
                    except socket.timeout:
                        continue
                    if not data:
                        break
                    chunks.append(data)
                raw = b"".join(chunks).decode("utf-8", errors="ignore")
                lines = [line.strip() for line in raw.replace("\n", "\r").split("\r") if line.strip()]
                return {"ok": True, "raw": raw, "lines": lines, "ip": self.ip, "port": self.avr_port}
        except Exception as exc:
            return self._error(self.avr_port, ",".join(commands), exc)

    @staticmethod
    def _latest_prefix(lines: List[str], prefix: str) -> str:
        for line in reversed(lines):
            if line.startswith(prefix):
                return line
        return ""

    @staticmethod
    def _latest_master_volume(lines: List[str]) -> str:
        for line in reversed(lines):
            if line.startswith("MV") and not line.startswith("MVMAX"):
                return line
        return ""

    @staticmethod
    def _decode_volume(line: str) -> str:
        value = line[2:].strip()
        if not value or value.startswith("MAX"):
            return ""
        try:
            numeric = int(value) / (10 if len(value) == 3 else 1)
        except ValueError:
            return value
        db_value = numeric - 80
        return f"{db_value:.1f} dB" if len(value) == 3 else f"{db_value:.0f} dB"

    @staticmethod
    def _decode_input(line: str) -> str:
        value = line[2:].strip()
        names = {
            "TV": "TV Audio",
            "BD": "Blu-ray",
            "MPLAY": "Media Player",
            "GAME": "Game",
            "HEOS": "HEOS",
            "TUNER": "Tuner",
            "CD": "CD",
            "AUX1": "AUX",
            "SAT/CBL": "CBL/SAT",
        }
        return names.get(value, value)

    @staticmethod
    def _speaker_name(code: str) -> str:
        names = {
            "FL": "Front L",
            "FR": "Front R",
            "C": "Center",
            "SW": "Subwoofer",
            "SL": "Surround L",
            "SR": "Surround R",
            "SBL": "Surround Back L",
            "SBR": "Surround Back R",
            "FHL": "Front Height L",
            "FHR": "Front Height R",
            "FDL": "Front Dolby L",
            "FDR": "Front Dolby R",
        }
        return names.get(code, code)

    @staticmethod
    def _decode_channel_trim(value: str) -> str:
        try:
            trim = int(value) - 50
        except ValueError:
            return value
        return f"{trim:+d} dB"

    def get_avr_snapshot(self) -> Dict[str, Any]:
        commands = [
            "PW?",
            "SI?",
            "MV?",
            "MU?",
            "MS?",
            "CV?",
            "SSINFAISFSV ?",
            "SSINFAISFOR ?",
            "SSINFAISSIG ?",
        ]
        data = self.send_avr_batch(commands, collect_seconds=1.4)
        if not data.get("ok"):
            return data
        lines = data.get("lines", [])
        power_line = self._latest_prefix(lines, "PW")
        input_line = self._latest_prefix(lines, "SI")
        volume_line = self._latest_master_volume(lines)
        mute_line = self._latest_prefix(lines, "MU")
        sound_line = self._latest_prefix(lines, "MS")
        sample_rate_line = self._latest_prefix(lines, "SSINFAISFSV")
        input_format_line = self._latest_prefix(lines, "SSINFAISFOR")
        input_signal_line = self._latest_prefix(lines, "SSINFAISSIG")
        speakers_by_code = {}
        for line in lines:
            if not line.startswith("CV") or line == "CVEND":
                continue
            body = line[2:].strip()
            if " " not in body:
                continue
            code, value = body.split(" ", 1)
            speakers_by_code[code] = {
                "code": code,
                "name": self._speaker_name(code),
                "trim": self._decode_channel_trim(value.strip()),
            }
        return {
            "ok": True,
            "power": power_line[2:] if power_line else "",
            "input": self._decode_input(input_line) if input_line else "",
            "volume": self._decode_volume(volume_line) if volume_line else "",
            "mute": mute_line[2:] if mute_line else "",
            "sound_mode": sound_line[2:].strip() if sound_line else "",
            "sample_rate": sample_rate_line.replace("SSINFAISFSV", "").strip(),
            "input_format": input_format_line.replace("SSINFAISFOR", "").strip(),
            "input_signal": input_signal_line.replace("SSINFAISSIG", "").strip(),
            "speakers": list(speakers_by_code.values()),
            "raw_lines": lines,
        }

    def ping_ports(self) -> Dict[str, Any]:
        if not self.ip:
            missing = self._missing_ip()
            return {
                "heos": {**missing, "port": self.heos_port},
                "avr": {**missing, "port": self.avr_port},
            }
        result = {}
        for name, port in {"heos": self.heos_port, "avr": self.avr_port}.items():
            try:
                with socket.create_connection((self.ip, port), timeout=self.timeout):
                    result[name] = {"ok": True, "ip": self.ip, "port": port}
            except Exception as exc:
                result[name] = {"ok": False, "ip": self.ip, "port": port, "error": type(exc).__name__, "message": str(exc)}
        return result

    def get_players(self) -> Dict[str, Any]:
        return self.send_heos("heos://player/get_players")

    def get_groups(self) -> Dict[str, Any]:
        return self.send_heos("heos://group/get_groups")

    def ungroup_player(self, pid: str) -> Dict[str, Any]:
        return self.send_heos(f"heos://group/set_group?pid={quote(str(pid), safe='')}")

    def get_mute(self, pid: Optional[str] = None) -> Dict[str, Any]:
        player_id = pid or self.first_player_id()
        if not player_id:
            return {"ok": False, "error": "NoHeosPlayer", "message": "Kein HEOS Player gefunden."}
        return self.send_heos(f"heos://player/get_mute?pid={player_id}")

    def set_mute(self, state: str, pid: Optional[str] = None) -> Dict[str, Any]:
        player_id = pid or self.first_player_id()
        if not player_id:
            return {"ok": False, "error": "NoHeosPlayer", "message": "Kein HEOS Player gefunden."}
        mute_state = "on" if state == "on" else "off"
        return self.send_heos(f"heos://player/set_mute?pid={player_id}&state={mute_state}")

    def player_ids(self) -> List[str]:
        data = self.get_players()
        if not data.get("ok", False) and "payload" not in data:
            return []
        payload: List[Dict[str, Any]] = data.get("payload", [])
        return [str(player.get("pid")) for player in payload if player.get("pid")]

    def first_player_id(self) -> Optional[str]:
        ids = self.player_ids()
        if not ids:
            return None
        return ids[0]

    def _selected_player_id(self, pid: Optional[str] = None) -> Optional[str]:
        player_id = str(pid or self.settings.get("ui", {}).get("selected_player_id") or "").strip()
        return player_id or self.first_player_id()

    def set_play_state(self, state: str, pid: Optional[str] = None) -> Dict[str, Any]:
        player_id = pid or self.first_player_id()
        if not player_id:
            ports = self.ping_ports()
            return {"ok": False, "error": "NoHeosPlayer", "message": "Kein HEOS Player gefunden oder HEOS-Port nicht erreichbar.", "ports": ports}
        return self.send_heos(f"heos://player/set_play_state?pid={player_id}&state={state}")

    def get_play_state(self, pid: Optional[str] = None) -> Dict[str, Any]:
        player_id = pid or self.first_player_id()
        if not player_id:
            return {"ok": False, "error": "NoHeosPlayer", "message": "Kein HEOS Player gefunden."}
        return self.send_heos(f"heos://player/get_play_state?pid={player_id}")

    def play_next(self, pid: Optional[str] = None) -> Dict[str, Any]:
        player_id = pid or self.first_player_id()
        if not player_id:
            return {"ok": False, "error": "NoHeosPlayer", "message": "Kein HEOS Player gefunden."}
        return self.send_heos(f"heos://player/play_next?pid={player_id}")

    def play_previous(self, pid: Optional[str] = None) -> Dict[str, Any]:
        player_id = pid or self.first_player_id()
        if not player_id:
            return {"ok": False, "error": "NoHeosPlayer", "message": "Kein HEOS Player gefunden."}
        return self.send_heos(f"heos://player/play_previous?pid={player_id}")

    def get_now_playing(self, pid: Optional[str] = None) -> Dict[str, Any]:
        player_id = pid or self.first_player_id()
        if not player_id:
            return {"ok": False, "error": "NoHeosPlayer", "message": "Kein HEOS Player gefunden."}
        return self.send_heos(f"heos://player/get_now_playing_media?pid={player_id}")

    def get_volume(self, pid: Optional[str] = None) -> Dict[str, Any]:
        player_id = pid or self.first_player_id()
        if not player_id:
            return {"ok": False, "error": "NoHeosPlayer", "message": "Kein HEOS Player gefunden."}
        return self.send_heos(f"heos://player/get_volume?pid={player_id}")

    def set_heos_volume(self, level: int, pid: Optional[str] = None) -> Dict[str, Any]:
        player_id = pid or self.first_player_id()
        if not player_id:
            return {"ok": False, "error": "NoHeosPlayer", "message": "Kein HEOS Player gefunden."}
        level = max(0, min(100, int(level)))
        return self.send_heos(f"heos://player/set_volume?pid={player_id}&level={level}")

    def play_url(self, url: str, pid: Optional[str] = None) -> Dict[str, Any]:
        if not url:
            return {"ok": False, "error": "NoUrl", "message": "Keine Stream-URL angegeben."}
        player_id = pid or self.first_player_id()
        if not player_id:
            return {"ok": False, "error": "NoHeosPlayer", "message": "Kein HEOS Player gefunden."}
        return self.send_heos(f"heos://browse/play_stream?pid={player_id}&url={quote(url, safe='')}")

    def get_music_sources(self) -> Dict[str, Any]:
        return self.send_heos("heos://browse/get_music_sources")

    def browse_source(self, sid: str, browse_id: str = "", range_value: str = "0,49") -> Dict[str, Any]:
        if not sid:
            return {"ok": False, "error": "NoSource", "message": "Keine Quellen-ID angegeben."}
        command = f"heos://browse/browse?sid={quote(str(sid), safe='')}"
        if browse_id:
            command += f"&cid={quote(str(browse_id), safe='')}"
        if range_value:
            command += f"&range={quote(str(range_value), safe=',')}"
        return self.send_heos(command)

    def get_search_criteria(self, sid: str) -> Dict[str, Any]:
        if not sid:
            return {"ok": False, "error": "NoSource", "message": "Keine Quellen-ID angegeben."}
        return self.send_heos(f"heos://browse/get_search_criteria?sid={quote(str(sid), safe='')}")

    def search_source(self, sid: str, search: str, scid: str, range_value: str = "0,49") -> Dict[str, Any]:
        if not sid:
            return {"ok": False, "error": "NoSource", "message": "Keine Quellen-ID angegeben."}
        search = str(search or "").strip()
        if not search:
            return {"ok": False, "error": "NoSearch", "message": "Kein Suchbegriff angegeben."}
        command = (
            f"heos://browse/search?sid={quote(str(sid), safe='')}"
            f"&search={quote(search, safe='')}"
            f"&scid={quote(str(scid or ''), safe='')}"
        )
        if range_value:
            command += f"&range={quote(str(range_value), safe=',')}"
        return self.send_heos(command)

    def play_station(self, sid: str, mid: str, name: str = "", cid: str = "", pid: Optional[str] = None) -> Dict[str, Any]:
        player_id = pid or self.first_player_id()
        if not player_id:
            return {"ok": False, "error": "NoHeosPlayer", "message": "Kein HEOS Player gefunden."}
        if not sid or not mid:
            return {"ok": False, "error": "MissingStation", "message": "Quelle und Medien-ID werden benötigt."}
        command = f"heos://browse/play_stream?pid={player_id}&sid={quote(str(sid), safe='')}&mid={quote(str(mid), safe='')}"
        if cid:
            command += f"&cid={quote(str(cid), safe='')}"
        if name:
            command += f"&name={quote(str(name), safe='')}"
        return self.send_heos(command)

    def add_to_queue(
        self,
        sid: str,
        cid: str = "",
        mid: str = "",
        aid: int = 1,
        pid: Optional[str] = None,
    ) -> Dict[str, Any]:
        player_id = pid or self.first_player_id()
        if not player_id:
            return {"ok": False, "error": "NoHeosPlayer", "message": "Kein HEOS Player gefunden."}
        if not sid:
            return {"ok": False, "error": "NoSource", "message": "Keine Quellen-ID angegeben."}
        if not cid and not mid:
            return {"ok": False, "error": "NoMedia", "message": "Container oder Medien-ID fehlt."}
        add_mode = max(1, min(4, int(aid)))
        command = f"heos://browse/add_to_queue?pid={player_id}&sid={quote(str(sid), safe='')}"
        if cid:
            command += f"&cid={quote(str(cid), safe='')}"
        if mid:
            command += f"&mid={quote(str(mid), safe='')}"
        command += f"&aid={add_mode}"
        return self.send_heos(command)

    def play_preset(self, preset: int, pid: Optional[str] = None) -> Dict[str, Any]:
        player_id = pid or self.first_player_id()
        if not player_id:
            return {"ok": False, "error": "NoHeosPlayer", "message": "Kein HEOS Player gefunden."}
        preset = max(1, int(preset))
        return self.send_heos(f"heos://browse/play_preset?pid={player_id}&preset={preset}")

    def play_input(self, input_name: str, pid: Optional[str] = None, source_pid: Optional[str] = None) -> Dict[str, Any]:
        player_id = pid or self.first_player_id()
        if not player_id:
            return {"ok": False, "error": "NoHeosPlayer", "message": "Kein HEOS Player gefunden."}
        input_name = str(input_name or "").strip()
        if not input_name:
            return {"ok": False, "error": "NoInput", "message": "Kein HEOS-Eingang ausgewählt."}
        command = f"heos://browse/play_input?pid={player_id}&input={quote(input_name, safe='/')}"
        if source_pid:
            command += f"&spid={quote(str(source_pid), safe='')}"
        return self.send_heos(command)

    def get_heos_playlists(self) -> Dict[str, Any]:
        return self.send_heos("heos://browse/get_heos_playlists")

    @staticmethod
    def _play_state_value(result: Dict[str, Any]) -> str:
        payload = result.get("payload", {})
        if isinstance(payload, dict) and payload.get("state"):
            return str(payload.get("state"))
        fields = result.get("message_fields", {})
        if isinstance(fields, dict) and fields.get("state"):
            return str(fields.get("state"))
        return ""

    @staticmethod
    def _player_name_by_id(players: List[Dict[str, Any]]) -> Dict[str, str]:
        return {
            str(player.get("pid")): str(player.get("name") or player.get("pid"))
            for player in players
            if player.get("pid")
        }

    def stop_other_players(self, main_pid: Optional[str] = None, mute_fallback: bool = True) -> Dict[str, Any]:
        main_player_id = self._selected_player_id(main_pid)
        if not main_player_id:
            return {"ok": False, "error": "NoHeosPlayer", "message": "Kein HEOS Player gefunden."}
        ungrouped = []
        group_data = self.get_groups()
        if group_data.get("ok", False) or "payload" in group_data:
            for group in group_data.get("payload", []):
                group_players = group.get("players", []) if isinstance(group, dict) else []
                if not any(str(player.get("pid")) == main_player_id for player in group_players):
                    continue
                leader = next((player for player in group_players if player.get("role") == "leader"), None)
                leader_id = str((leader or {}).get("pid") or main_player_id)
                result = self.ungroup_player(leader_id)
                ungrouped.append({"pid": leader_id, "gid": group.get("gid"), "result": result})
                time.sleep(0.2)
        players_data = self.get_players()
        players = players_data.get("payload", []) if isinstance(players_data.get("payload", []), list) else []
        player_names = self._player_name_by_id(players)
        player_ids = [str(player.get("pid")) for player in players if player.get("pid")]
        stopped = []
        failed = []
        for player_id in player_ids:
            if player_id == main_player_id:
                continue
            result = self.set_play_state("stop", player_id)
            item = {"pid": player_id, "name": player_names.get(player_id, player_id), "result": result}
            if result.get("ok", False):
                stopped.append(item)
            else:
                failed.append(item)
        time.sleep(0.4)
        still_playing = []
        muted = []
        mute_failed = []
        checked = []
        for player_id in player_ids:
            if player_id == main_player_id:
                continue
            state_result = self.get_play_state(player_id)
            state = self._play_state_value(state_result)
            item = {
                "pid": player_id,
                "name": player_names.get(player_id, player_id),
                "state": state,
                "result": state_result,
            }
            checked.append(item)
            if state != "play":
                continue
            still_playing.append(item)
            if not mute_fallback:
                continue
            mute_result = self.set_mute("on", player_id)
            mute_item = {
                "pid": player_id,
                "name": player_names.get(player_id, player_id),
                "result": mute_result,
            }
            if mute_result.get("ok", False):
                muted.append(mute_item)
            else:
                mute_failed.append(mute_item)
        return {
            "ok": not failed and not mute_failed and not (still_playing and not mute_fallback),
            "main_player_id": main_player_id,
            "ungrouped_count": len(ungrouped),
            "stopped_count": len(stopped),
            "failed_count": len(failed),
            "checked_count": len(checked),
            "still_playing_count": len(still_playing),
            "muted_count": len(muted),
            "mute_failed_count": len(mute_failed),
            "ungrouped": ungrouped,
            "stopped": stopped,
            "failed": failed,
            "checked": checked,
            "still_playing": still_playing,
            "muted": muted,
            "mute_failed": mute_failed,
            "message": (
                "Hauptraum wurde entkoppelt, andere Räume wurden gestoppt und verbleibende Wiedergabe wurde gemutet."
                if muted and ungrouped else
                "Andere Räume wurden gestoppt und verbleibende Wiedergabe wurde gemutet."
                if muted else
                "Hauptraum wurde entkoppelt und andere HEOS-Räume wurden gestoppt."
                if ungrouped and stopped else
                "Hauptraum wurde von anderen HEOS-Räumen entkoppelt."
                if ungrouped else
                "Andere HEOS-Räume wurden gestoppt."
                if stopped else
                "Keine weiteren HEOS-Räume gefunden."
            ),
        }

    def stop_secondary_avr_zones(self) -> Dict[str, Any]:
        result = self.send_avr_batch(["Z2OFF", "Z3OFF"], collect_seconds=0.6)
        return {
            **result,
            "commands": ["Z2OFF", "Z3OFF"],
            "message": "AVR-Nebenzonen wurden ausgeschaltet.",
        }

    def power_on(
        self,
        main_pid: Optional[str] = None,
        stop_other_rooms: bool = True,
        mute_fallback: bool = True,
        stop_avr_zones: bool = True,
    ) -> Dict[str, Any]:
        avr_result = self.send_avr("PWON")
        if not stop_other_rooms:
            return avr_result
        time.sleep(0.4)
        cleanup = self.stop_other_players(main_pid, mute_fallback)
        zones = self.stop_secondary_avr_zones() if stop_avr_zones else {"ok": True, "skipped": True}
        return {
            **avr_result,
            "ok": bool(avr_result.get("ok")) and cleanup.get("ok", False) and zones.get("ok", False),
            "message": cleanup.get("message", ""),
            "main_player_id": cleanup.get("main_player_id"),
            "ungrouped_count": cleanup.get("ungrouped_count", 0),
            "stopped_count": cleanup.get("stopped_count", 0),
            "failed_count": cleanup.get("failed_count", 0),
            "checked_count": cleanup.get("checked_count", 0),
            "still_playing_count": cleanup.get("still_playing_count", 0),
            "muted_count": cleanup.get("muted_count", 0),
            "mute_failed_count": cleanup.get("mute_failed_count", 0),
            "zones_off_count": 0 if zones.get("skipped") else len(zones.get("commands", [])),
            "cleanup": cleanup,
            "zones": zones,
        }

    def standby(self) -> Dict[str, Any]:
        return self.send_avr("PWSTANDBY")

    def volume_up(self) -> Dict[str, Any]:
        return self.send_avr("MVUP")

    def volume_down(self) -> Dict[str, Any]:
        return self.send_avr("MVDOWN")

    def set_volume(self, volume: int) -> Dict[str, Any]:
        volume = max(0, min(98, int(volume)))
        return self.send_avr(f"MV{volume:02d}")

    def mute_on(self) -> Dict[str, Any]:
        return self.send_avr("MUON")

    def mute_off(self) -> Dict[str, Any]:
        return self.send_avr("MUOFF")

    def input_source(self, source: str) -> Dict[str, Any]:
        allowed = {
            "tv": "SITV", "bluetooth": "SIBT", "heos": "SIHEOS", "aux": "SIAUX1",
            "game": "SIGAME", "bluray": "SIBD", "media_player": "SIMPLAY",
            "cd": "SICD", "tuner": "SITUNER", "cblsat": "SISAT/CBL"
        }
        command = allowed.get(source)
        if not command:
            return {"ok": False, "error": f"Unbekannte Quelle: {source}"}
        return self.send_avr(command)

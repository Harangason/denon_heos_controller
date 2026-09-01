from flask import Blueprint, jsonify, render_template, request
from .heos_client import DenonHeosClient, load_settings, save_settings
from . import audio_bridge
from .discovery import discover_denon_devices

bp = Blueprint("main", __name__)
INT_SETTINGS = {"heos_port", "avr_port", "web_port"}
FLOAT_SETTINGS = {"socket_timeout_seconds"}


def client() -> DenonHeosClient:
    return DenonHeosClient()


def json_body() -> dict:
    data = request.get_json(force=True, silent=True) or {}
    return data if isinstance(data, dict) else {}


def parse_int(value, fallback: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(minimum, min(maximum, parsed))


def parse_float(value, fallback: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return max(minimum, min(maximum, parsed))


@bp.route("/")
def index():
    settings = load_settings()
    return render_template("index.html", settings=settings)


@bp.get("/api/settings")
def get_settings():
    return jsonify(load_settings())


@bp.post("/api/settings")
def update_settings():
    data = json_body()
    settings = load_settings()
    for key in ["denon_ip", "heos_port", "avr_port", "socket_timeout_seconds", "web_host", "web_port"]:
        if key not in data or data[key] in (None, ""):
            continue
        if key in INT_SETTINGS:
            settings[key] = parse_int(data[key], int(settings.get(key, 0)), 1, 65535)
        elif key in FLOAT_SETTINGS:
            settings[key] = parse_float(data[key], float(settings.get(key, 3)), 0.5, 20)
        else:
            settings[key] = str(data[key]).strip()
    save_settings(settings)
    return jsonify({"ok": True, "settings": settings})


@bp.post("/api/ui/settings")
def update_ui_settings():
    data = json_body()
    settings = load_settings()
    ui = settings.setdefault("ui", {})
    for key in ["active_tab", "selected_player_id", "default_heos_input"]:
        if key in data and data[key] is not None:
            ui[key] = str(data[key]).strip()
    if "favorite_preset" in data:
        ui["favorite_preset"] = parse_int(data.get("favorite_preset"), int(ui.get("favorite_preset", 1)), 1, 100)
    if "live_enabled" in data:
        ui["live_enabled"] = bool(data.get("live_enabled"))
    if "live_interval_seconds" in data:
        ui["live_interval_seconds"] = parse_int(
            data.get("live_interval_seconds"),
            int(ui.get("live_interval_seconds", 5)),
            2,
            60,
        )
    save_settings(settings)
    return jsonify({"ok": True, "settings": settings})


@bp.get("/api/discover")
def discover():
    return jsonify(discover_denon_devices())


@bp.post("/api/discover/apply")
def discover_apply():
    data = json_body()
    ip = str(data.get("ip", "")).strip()
    if not ip:
        return jsonify({"ok": False, "error": "NoIp", "message": "Keine IP ausgewählt."}), 400
    settings = load_settings()
    settings["denon_ip"] = ip
    save_settings(settings)
    return jsonify({"ok": True, "message": f"Denon-IP auf {ip} gesetzt.", "settings": settings})


@bp.get("/api/status")
def status():
    c = client()
    result = {"ok": True, "ports": c.ping_ports()}
    settings = load_settings()
    requested_player_id = str(request.args.get("pid") or settings.get("ui", {}).get("selected_player_id") or "").strip()
    avr_port_ok = bool(result["ports"].get("avr", {}).get("ok"))
    if avr_port_ok:
        try:
            result["avr_status"] = c.get_avr_snapshot()
        except Exception as exc:
            result["avr_status"] = {"ok": False, "error": str(exc)}
    heos_port_ok = bool(result["ports"].get("heos", {}).get("ok"))
    if not heos_port_ok:
        result["players"] = {
            "ok": False,
            "error": "HeosUnavailable",
            "message": "HEOS-Port ist nicht erreichbar. Player-Abfrage wurde übersprungen.",
        }
        result["now_playing"] = {
            "ok": False,
            "error": "HeosUnavailable",
            "message": "HEOS-Port ist nicht erreichbar. Aktuelle Wiedergabe wurde übersprungen.",
        }
        return jsonify(result)
    try:
        result["players"] = c.get_players()
    except Exception as exc:
        result["players"] = {"error": str(exc)}
    try:
        players = result.get("players", {}).get("payload", [])
        player_ids = {str(player.get("pid")) for player in players if player.get("pid")}
        player_id = requested_player_id if requested_player_id in player_ids else None
        player_id = player_id or (str(players[0].get("pid")) if players else None)
        result["selected_player_id"] = player_id
        result["now_playing"] = c.get_now_playing(player_id) if player_id else {
            "ok": False,
            "error": "NoHeosPlayer",
            "message": "Kein HEOS Player gefunden.",
        }
        result["play_state"] = c.get_play_state(player_id) if player_id else {}
        result["heos_volume"] = c.get_volume(player_id) if player_id else {}
    except Exception as exc:
        result["now_playing"] = {"error": str(exc)}
    return jsonify(result)


@bp.post("/api/heos/play")
def heos_play():
    return jsonify(client().set_play_state("play", json_body().get("pid")))


@bp.post("/api/heos/pause")
def heos_pause():
    return jsonify(client().set_play_state("pause", json_body().get("pid")))


@bp.post("/api/heos/stop")
def heos_stop():
    return jsonify(client().set_play_state("stop", json_body().get("pid")))


@bp.post("/api/heos/next")
def heos_next():
    return jsonify(client().play_next(json_body().get("pid")))


@bp.post("/api/heos/previous")
def heos_previous():
    return jsonify(client().play_previous(json_body().get("pid")))


@bp.post("/api/heos/play_url")
def heos_play_url():
    data = json_body()
    return jsonify(client().play_url(data.get("url", ""), data.get("pid")))


@bp.post("/api/heos/volume")
def heos_volume():
    data = json_body()
    level = parse_int(data.get("level"), 40, 0, 100)
    return jsonify(client().set_heos_volume(level, data.get("pid")))


@bp.post("/api/heos/input")
def heos_input():
    data = json_body()
    return jsonify(client().play_input(data.get("input", ""), data.get("pid"), data.get("spid")))


@bp.post("/api/heos/preset")
def heos_preset():
    data = json_body()
    preset = parse_int(data.get("preset"), 1, 1, 100)
    return jsonify(client().play_preset(preset, data.get("pid")))


@bp.get("/api/heos/sources")
def heos_sources():
    return jsonify(client().get_music_sources())


@bp.get("/api/heos/playlists")
def heos_playlists():
    return jsonify(client().get_heos_playlists())


@bp.post("/api/heos/browse")
def heos_browse():
    data = json_body()
    return jsonify(client().browse_source(data.get("sid", ""), data.get("cid", data.get("id", "")), data.get("range", "0,49")))


@bp.post("/api/heos/search")
def heos_search():
    data = json_body()
    return jsonify(client().search_source(data.get("sid", ""), data.get("search", ""), data.get("scid", ""), data.get("range", "0,49")))


@bp.post("/api/heos/search_criteria")
def heos_search_criteria():
    data = json_body()
    return jsonify(client().get_search_criteria(data.get("sid", "")))


@bp.post("/api/heos/queue")
def heos_queue():
    data = json_body()
    aid = parse_int(data.get("aid"), 1, 1, 4)
    return jsonify(client().add_to_queue(data.get("sid", ""), data.get("cid", ""), data.get("mid", ""), aid, data.get("pid")))


@bp.post("/api/heos/station")
def heos_station():
    data = json_body()
    return jsonify(client().play_station(data.get("sid", ""), data.get("mid", ""), data.get("name", ""), data.get("cid", ""), data.get("pid")))


@bp.post("/api/avr/<action>")
def avr_action(action: str):
    c = client()
    data = json_body()
    mapping = {
        "standby": c.standby,
        "volume_up": c.volume_up,
        "volume_down": c.volume_down,
        "mute_on": c.mute_on,
        "mute_off": c.mute_off,
    }
    if action == "power_on":
        stop_other_rooms = data.get("stop_other_rooms", True) is not False
        mute_fallback = data.get("mute_fallback", True) is not False
        stop_avr_zones = data.get("stop_avr_zones", True) is not False
        return jsonify(c.power_on(data.get("pid"), stop_other_rooms, mute_fallback, stop_avr_zones))
    fn = mapping.get(action)
    if not fn:
        return jsonify({"error": "Unbekannte AVR-Aktion"}), 400
    return jsonify(fn())


@bp.post("/api/avr/volume")
def avr_volume():
    data = json_body()
    volume = parse_int(data.get("volume"), 40, 0, 98)
    return jsonify(client().set_volume(volume))


@bp.post("/api/avr/input")
def avr_input():
    source = str(json_body().get("source", "")).strip()
    return jsonify(client().input_source(source))


@bp.get("/api/audio_bridge/status")
def audio_bridge_status():
    return jsonify(audio_bridge.status())


@bp.post("/api/audio_bridge/settings")
def audio_bridge_settings():
    data = json_body()
    return jsonify({"ok": True, "settings": audio_bridge.update_bridge_settings(data)})


@bp.post("/api/audio_bridge/open_stream")
def audio_bridge_open_stream():
    data = json_body()
    return jsonify(audio_bridge.open_stream(data.get("url", "")))


@bp.get("/api/audio_bridge/vlc/status")
def audio_bridge_vlc_status():
    return jsonify(audio_bridge.vlc_status())


@bp.post("/api/audio_bridge/vlc/open_stream")
def audio_bridge_vlc_open_stream():
    data = json_body()
    return jsonify(audio_bridge.start_vlc_stream(data.get("url", "")))


@bp.post("/api/audio_bridge/vlc/command")
def audio_bridge_vlc_command():
    data = json_body()
    return jsonify(audio_bridge.vlc_command(str(data.get("command", "")).strip(), data.get("value")))


@bp.post("/api/audio_bridge/vlc/stop")
def audio_bridge_vlc_stop():
    return jsonify(audio_bridge.stop_vlc())


@bp.post("/api/audio_bridge/start/<kind>")
def audio_bridge_start(kind: str):
    return jsonify(audio_bridge.start_external(kind))

"""Small command line interface to the running core (REST API).

  python -m luxafor core                    start the core daemon
  python -m luxafor status                  show current LED/status
  python -m luxafor color #FF0000 [--led ZONE] [--device ID]
  python -m luxafor off
  python -m luxafor set <Statusname> [--duration 30] (min, default units)
  python -m luxafor restore                 'Automatischen Status wiederherstellen'
  python -m luxafor test                    device smoke test
  python -m luxafor diagnose                run diagnostics
  python -m luxafor devices                 list devices
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from urllib.error import URLError, HTTPError

from luxafor.core import config


def api_base() -> str:
    host, port = config.API_HOST, config.API_PORT
    try:
        with open(config.CONFIG_HOME / "api-endpoint") as fh:
            base = fh.read().strip()
            if base:
                return base
    except OSError:
        pass
    return f"http://{host}:{port}"


def request(method: str, path: str, payload: dict | None = None, timeout: float = 10) -> dict | list:
    # timeout wird hier für login lange Zeiten gebraucht
    url = api_base() + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
            return json.loads(body) if body else {}
    except HTTPError as exc:
        try:
            return json.loads(exc.read().decode())
        except Exception:
            return {"error": f"HTTP {exc.code}"}
    except (URLError, OSError) as exc:
        print(f"Fehler: Luxafor-Kern nicht erreichbar ({url}): {exc}", file=sys.stderr)
        print("Starte den Hintergrunddienst: systemctl --user start luxafor-core", file=sys.stderr)
        sys.exit(2)


def main_core() -> None:
    from luxafor.core.app import run_core
    run_core()


def cmd_status(_args) -> None:
    snap = request("GET", "/api/status")
    cur = snap.get("current", {})
    print(f"LED: {cur.get('color')} ({cur.get('effect')}) via {cur.get('label')}")
    print(f"Herkunft: {cur.get('origin')}  pausiert: {'ja' if snap.get('paused') else 'nein'}")
    pres = snap.get("presence")
    if pres:
        print(f"Teams: {pres.get('availability')} / {pres.get('activity')}")


def cmd_devices(_args) -> None:
    data = request("GET", "/api/devices")
    for d in data.get("devices", []):
        print(f" {d.get('id'):12} {d.get('model'):26} offen:{'ja' if d.get('open') else 'nein'}"
              f" sim:{'ja' if d.get('simulated') else 'nein'} letzte Farbe:{d.get('color')}")


def cmd_color(args) -> None:
    payload = {"color": args.color, "led": args.led}
    if args.device:
        payload["device"] = args.device
    print(request("POST", "/api/device/color", payload))


def cmd_off(args) -> None:
    payload = {"device": args.device} if args.device else {}
    print(request("POST", "/api/device/off", payload))


def cmd_set(args) -> None:
    payload = {"status": args.name, "duration": int((args.duration or 0) * 60)}
    print(request("POST", "/api/status", payload))


def cmd_restore(_args) -> None:
    print(request("POST", "/api/status/restore", {}))


def cmd_test(_args) -> None:
    print(request("POST", "/api/device/test", {}))


def cmd_diagnose(_args) -> None:
    data = request("GET", "/api/diagnostics")
    for c in data.get("checks", []):
        mark = "OK " if c.get("ok") is True else ("FEH" if c.get("ok") is False else " ? ")
        print(f"[{mark}] {c.get('check')}: {c.get('message')}")
        if c.get("ok") is False and c.get("hint"):
            print(f"        Hinweis: {c.get('hint')}")


def cmd_login(_args) -> None:
    """One-Click-Anmeldung: Browser öffnet aus der Shell; Ergebnis wird angezeigt."""
    import threading
    import webbrowser
    import urllib.request
    import json as _json

    result: dict = {}

    def _do_login() -> None:
        result.update(request("POST", "/api/auth/login", timeout=240) or {})

    thread = threading.Thread(target=_do_login, daemon=True)
    thread.start()

    print("Warte auf Anmelde-Link vom Kern … (der Link wird im Standardbrowser geöffnet)")
    url_seen = {"flag": False}
    import time as _t
    deadline = _t.time() + 30
    while _t.time() < deadline and not url_seen["flag"] and thread.is_alive():
        try:
            with urllib.request.urlopen(api_base() + "/api/events", timeout=5) as resp:
                for raw in resp:
                    line = raw.decode(errors="replace").strip()
                    if line.startswith("event: auth_url"):
                        url_seen["flag"] = True
                    elif url_seen["flag"] and line.startswith("data: "):
                        try:
                            payload = _json.loads(line[6:])
                        except _json.JSONDecodeError:
                            continue
                        url = payload.get("url")
                        if url:
                            print("Öffne Browser:", url)
                            try:
                                webbrowser.open(url)
                            except Exception as exc:
                                print("Bitte manuell öffnen:", url, "-", exc)
                        break
                if url_seen["flag"]:
                    break
        except (urllib.request.URLError, OSError, TimeoutError):
            pass
    print("Anmeldung läuft im Browser … (beendet sich nach Bestätigung)")
    thread.join(timeout=240)
    if result.get("ok"):
        acc = (result.get("account") or {}).get("user") or "?"
        print("✓ Angemeldet als:", acc)
    elif result:
        print("✗ ", result.get("message") or result)
    else:
        print("  Kein Ergebnis — Anmeldung ggf. noch im Browser bestätigen.")


def main_gui() -> None:
    from luxafor.ui.main import main
    main()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="luxafor", description="Luxafor Linux CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("core", help="startet den Kern-Dienst (Vordergrund)")
    sub.add_parser("status", help="aktueller Status").set_defaults(func=cmd_status)
    sub.add_parser("devices", help="Geräte auflisten").set_defaults(func=cmd_devices)

    c = sub.add_parser("color", help="Farbe setzen (#RRGGBB)")
    c.add_argument("color")
    c.add_argument("--led", default="all", help="all|front|back|1..6")
    c.add_argument("--device", default=None)
    c.set_defaults(func=cmd_color)

    o = sub.add_parser("off", help="LED ausschalten")
    o.add_argument("--device", default=None)
    o.set_defaults(func=cmd_off)

    s = sub.add_parser("set", help="manuellen Status aus dem Katalog setzen")
    s.add_argument("name")
    s.add_argument("--duration", type=float, default=0, help="Minuten nach Ablauf automatische Fortsetzung")
    s.set_defaults(func=cmd_set)

    sub.add_parser("restore", help="automatischen Status wiederherstellen").set_defaults(func=cmd_restore)
    sub.add_parser("login", help="Microsoft-365-Anmeldung (Browser öffnet sich)").set_defaults(func=cmd_login)
    sub.add_parser("test", help="Gerätetest").set_defaults(func=cmd_test)
    sub.add_parser("diagnose", help="Diagnosen ausführen").set_defaults(func=cmd_diagnose)
    return p


def main() -> None:
    args = build_parser().parse_args()
    if args.cmd == "core":
        main_core()
        return
    args.func(args)


if __name__ == "__main__":
    main()
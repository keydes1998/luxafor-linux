#!/usr/bin/env python3
"""Protokoll- und Rechte-Probe für die Luxafor Flag Gen2 (04d8:f372).

Die Gen2-Firmware nutzt das offizielle Mode-Protokoll (dokumentiert in der
Luxafor-Spec, implementiert u. a. im Rust-Crate 'luxafor'):

    Solid : [0x00, 0x01, LED, R, G, B]
    Fade  : [0x00, 0x02, LED, R, G, B, Time]
    Strobe: [0x00, 0x03, LED, R, G, B, Speed, 0x00, Repeat]
    Wave  : [0x00, 0x04, WaveType, R, G, B, 0x00, Repeat, Speed]
    Pattern: [0x00, 0x06, PatternType, Repeat]
    Off   : [0x00, 0x00, ord('O')]

Wichtig: Bei Gen2 ist 0x41 = alle RÜCK-Seiten-LEDs, 0x42 = alle VORDER-Seiten.

Ausführen im normalen Terminal:
    ~/.local/share/luxafor/venv/bin/python scripts/probe_flag_protocol.py
"""
import os
import sys
import time
import glob

sys.path.insert(0, "src")

from luxafor.hardware.base import Led, LedCommand, GEN1, GEN2, protocol_for, looks_like_luxafor  # noqa: E402

LINE = "-" * 62


def section(title: str) -> None:
    print(f"\n{LINE}\n{title}\n{LINE}")


def find_hidraw_nodes() -> list[tuple[str, str, str]]:
    out = []
    for sysfs in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        name = os.path.basename(sysfs)
        try:
            with open(f"{sysfs}/device/uevent") as fh:
                ue = fh.read()
        except OSError:
            continue
        vid = pid = ""
        for line in ue.splitlines():
            if line.startswith("HID_ID="):
                p = line.split(":")
                if len(p) >= 3:
                    vid, pid = p[1].lower(), p[2].lower()
        out.append((f"/dev/{name}", vid, pid))
    return out


def report_rights(nodes) -> None:
    section("A) Rechte der hidraw-Nodes")
    for node, vid, pid in nodes:
        if vid not in ("000004d2", "000004d8"):
            continue
        try:
            st = os.stat(node)
            print(f"  {node}  vid={vid} pid={pid}  mode={oct(st.st_mode)[-4:]} "
                  f"uid={st.st_uid} lesbar={os.access(node, os.R_OK)} "
                  f"schreibbar={os.access(node, os.W_OK)}")
        except OSError as exc:
            print(f"  {node}  vid={vid} pid={pid}  Fehler: errno={exc.errno} ({exc})")


def direct_write_test(nodes):
    section("B) Direkter hidraw-Schreibtest (ohne hidapi)")
    for node, vid, pid in nodes:
        if pid != "0000f372" and pid != "0000bada":
            continue
        mode = GEN2 if pid == "0000f372" else GEN1
        try:
            fd = os.open(node, os.O_RDWR)
            cmd = LedCommand(kind="color", rgb=(0, 176, 48), led=Led.ALL)
            # Gen2: [0x00, 0x01, LED, R, G, B]; Gen1: [0x00, 0xFF, LED, R, G, B]
            buf = cmd.as_bytes(mode)
            n = os.write(fd, buf)
            os.close(fd)
            print(f"  {node} ({mode}): GRÜN geschrieben ({n} byte) — "
                  f"leuchtet jetzt GRÜN? (2 s)")
            time.sleep(2)
            return mode, node
        except OSError as exc:
            print(f"  {node} ({mode}): Fehler errno={exc.errno} = {os.strerror(exc.errno)}"
                  + ("  → Stick ab-/anstecken + ggf. neu aus-/einloggen" if exc.errno in (13, 1) else ""))
    return None, None


def hidapi_phases(node: str, mode: str) -> None:
    section("C) Protokoll-Phasen über hidapi (jede Phase 2 s — BEOBACHTEN)")
    import hid
    dev = hid.device()
    path_bytes = node.encode() if "/" in node else bytes(node)
    try:
        dev.open_path(path_bytes)
        print("  open ok")
    except Exception as exc:
        print(f"  open fehlgeschlagen: {exc}")
        return

    ALL = 0xFF
    F = 0x42 if mode == GEN2 else 0x41   # front-all je Gen
    B = 0x41 if mode == GEN2 else 0x42

    def phase(n, label, buf: bytes):
        try:
            ret = dev.write(buf)
            print(f"  Phase {n}: {label:<40} → {ret} bytes")
        except Exception as exc:
            print(f"  Phase {n}: {label:<40} FEHLER: {exc}")
        time.sleep(2)

    # Hilfs-Encoder nutzt die echte Protokoll-Encoder
    def solid(rgb, led=Led.ALL):
        return bytes([0x00]) + bytes(LedCommand(kind="color", rgb=rgb, led=led).encode(mode)) + bytes(7)

    phase(1, f"{mode}: SOLID GRÜN (alle)", solid((0, 176, 48)))
    phase(2, f"{mode}: SOLID ROT (alle)", solid((255, 0, 0)))
    phase(3, f"{mode}: SOLID GELB (front 0x{F:02X})", solid((255, 216, 94), Led.FRONT))
    phase(4, f"{mode}: SOLID BLAU (back 0x{B:02X})", solid((0, 90, 255), Led.BACK))
    phase(5, f"{mode}: SOLID WEISS (alle)", solid((255, 255, 255)))

    strobe = LedCommand(kind="strobe", rgb=(0, 255, 0), led=Led.ALL, speed=4, repeat=8)
    phase(6, f"{mode}: STROBE grün", bytes([0x00]) + bytes(strobe.encode(mode)) + bytes(7))

    wave = LedCommand(kind="wave", rgb=(255, 128, 0), wave_type=2, wave_delay=2, repeat=1)
    phase(7, f"{mode}: WAVE type 2 orange", bytes([0x00]) + bytes(wave.encode(mode)) + bytes(7))

    pattern = LedCommand(kind="pattern", pattern_id=5, repeat=3)  # gen2: police
    phase(8, f"{mode}: PATTERN 5", bytes([0x00]) + bytes(pattern.encode(mode)) + bytes(7))

    fade = LedCommand(kind="color", rgb=(255, 0, 0), led=Led.ALL)
    fade_buf = bytes([0x00, 0x02, 0xFF, 255, 0, 0, 5])  # fade rot in 5 s (nur gen2)
    if mode == GEN2:
        phase(9, f"{mode}: FADE rot (5 s)", fade_buf)
    else:
        phase(9, "(FADE nur in Gen2) — übersprungen", bytes(9))

    phase(10, f"{mode}: OFF", bytes([0x00]) + bytes(LedCommand(kind="off").encode(mode)) + bytes(7))

    # Version abfragen (gen2 dokumentiert: 0x80)
    try:
        dev.write(bytes([0x00, 0x80]) + bytes(7))
        time.sleep(0.3)
        resp = dev.read(9, timeout_ms=300)
        if resp:
            print(f"  Version/Serial-Antwort: {list(resp)}")
        else:
            print("  (keine Version-Antwort — Input-Report nicht erwartet)")
    except Exception as exc:
        print("  Version-Abfrage: ", exc)
    dev.close()

    print(f"""

Zusammenfassung — BITTE MELDEN:
  ✓ Phasen 1-5 (Solid-Farben) sichtbar?  Welchen Zonen?
  ✓ Phasen 6-9 (Effekte) sichtbar?       Nur Strobe?
  Falls alles sichtbar: Protokoll {mode} bestätigt ✓
""")


def main() -> int:
    section("0) Luxafor-Geräte laut hidapi")
    try:
        import hid
        for i in hid.enumerate(0, 0):
            if looks_like_luxafor(i.get("vendor_id", 0), i.get("product_id", 0),
                                  i.get("product_string", "") or ""):
                print(f"  vid={i['vendor_id']:04x} pid={i['product_id']:04x} "
                      f"product={i.get('product_string') or '?'} path={i['path']}")
    except Exception as exc:
        print("  hidapi-Fehler:", exc)

    nodes = find_hidraw_nodes()
    report_rights(nodes)
    mode, node = direct_write_test(nodes)
    if node:
        hidapi_phases(node, mode)
    else:
        print("\nKein Gerät schreibbar — erst Rechte klären (Abschnitt A/B oben).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
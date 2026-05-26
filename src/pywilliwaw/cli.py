"""
Williwaw interactive REPL.

Commands (always available):
  devices               scan and list nearby BLE devices
  connect <name|#>      connect to a device by name or scan-list index
  quit                  exit

Commands (when connected):
  disconnect            disconnect from current device
  fan                   toggle fan on/off
  speed <1-15>          set fan speed
  sweep <0|1>           enable or disable oscillation
  ospeed <1-3>          set oscillation speed (1=Low 2=Medium 3=High)
  center                return sweep head to center
  sleep <minutes|off>   hardware sleep timer: turn off after N min (1–1440)
  thermostat <°C|off>   auto-mode: run fan while temp ≥ °C (15–27)
  sensors               show paired temperature sensors
  status                show current fan state
"""

import asyncio
import json
import readline  # noqa: F401 — enables up/down arrow history in input()
from pathlib import Path

from bleak.exc import BleakGATTProtocolError

from pywilliwaw import Williwaw, discover, find_by_address, find_by_name

fan: Williwaw | None = None
scan_results: list = []

_CONFIG_PATH = Path.home() / ".config" / "williwaw" / "fans.json"


def _load_known_fans() -> list[dict]:
    try:
        return json.loads(_CONFIG_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_known_fan(f: Williwaw) -> None:
    known = _load_known_fans()
    if not any(e["address"] == f.address for e in known):
        known.append({"address": f.address, "name": f.name})
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CONFIG_PATH.write_text(json.dumps(known, indent=2))


# ── startup reconnect ──────────────────────────────────────────────────────────

async def _try_reconnect() -> None:
    global fan
    known = _load_known_fans()
    if not known:
        return

    names = ", ".join(e["name"] for e in known)
    print(f"Looking for known fan(s) ({names})…", end=" ", flush=True)

    # Phase 1: scan for all known devices in parallel (safe to cancel).
    async def scan_one(entry: dict):
        try:
            return await find_by_address(entry["address"], timeout=3.0)
        except Exception:
            return None

    scan_tasks = [asyncio.create_task(scan_one(e)) for e in known]
    done, pending = await asyncio.wait(scan_tasks, timeout=3.0, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()

    device = None
    for t in done:
        try:
            result = t.result()
            if result is not None:
                device = result
                break
        except Exception:
            pass

    if device is None:
        print("not found, use 'connect'")
        return

    # Phase 2: connect to the found device — never cancelled mid-flight.
    try:
        f = Williwaw(device)
        await f.connect()
        fan = f
        print(f"connected ({fan.name})")
    except Exception:
        print("found but could not connect, use 'connect'")


# ── device commands ────────────────────────────────────────────────────────────

async def cmd_devices() -> None:
    global scan_results
    print("Scanning for 5 seconds…")
    scan_results = await discover(timeout=5.0)
    scan_results.sort(key=lambda d: d.name or "")
    if not scan_results:
        print("No devices found.")
        return
    for i, d in enumerate(scan_results):
        print(f"  [{i}]  {d.name or '(unknown)':<30}  {d.address}")


async def cmd_connect(target: str) -> None:
    global fan

    if fan and fan.is_connected:
        print("Already connected. Run 'disconnect' first.")
        return

    if target.isdigit():
        idx = int(target)
        if not scan_results:
            print("No scan results. Run 'devices' first.")
            return
        if idx >= len(scan_results):
            print(f"Index {idx} out of range (0–{len(scan_results)-1}).")
            return
        device = scan_results[idx]
    else:
        print(f"Scanning for '{target}'…")
        device = await find_by_name(target, timeout=10.0)
        if device is None:
            print(f"Device '{target}' not found.")
            return

    print(f"Connecting to {device.name} ({device.address})…")
    fan = Williwaw(device)
    await fan.connect()
    _save_known_fan(fan)
    print(f"Connected.  fan={'on' if fan.fan else 'off'}  speed={fan.speed}  sweep={'on' if fan.sweep else 'off'}")


async def cmd_disconnect() -> None:
    global fan
    if not fan or not fan.is_connected:
        print("Not connected.")
        return
    await fan.disconnect()
    fan = None
    print("Disconnected.")


# ── REPL loop ──────────────────────────────────────────────────────────────────

async def repl() -> None:
    loop = asyncio.get_running_loop()
    print("Williwaw REPL. Type 'help' for commands.\n")
    await _try_reconnect()

    while True:
        connected = fan and fan.is_connected
        prompt = f"williwaw{'@' + fan.address if connected else ''}> "

        try:
            line = await loop.run_in_executor(None, lambda: input(prompt))
        except (EOFError, KeyboardInterrupt):
            break

        parts = line.strip().split()
        if not parts:
            continue
        cmd, args = parts[0].lower(), parts[1:]

        if cmd in ("quit", "exit", "q"):
            break

        elif cmd == "help":
            print(__doc__)

        elif cmd == "devices":
            await cmd_devices()

        elif cmd == "connect":
            if not args:
                print("usage: connect <name|#>")
            else:
                await cmd_connect(" ".join(args))

        elif cmd == "disconnect":
            await cmd_disconnect()

        elif cmd in ("fan", "speed", "sweep", "ospeed", "center", "sleep", "thermostat", "sensors", "status"):
            if not connected:
                print("Not connected. Use 'connect <name|#>' first.")
                continue
            try:
                if cmd == "fan":
                    await fan.toggle()
                elif cmd == "status":
                    osp = {1: "Low", 2: "Medium", 3: "High"}.get(fan.oscillation_speed, "?")
                    print(f"fan={'on' if fan.fan else 'off'}  speed={fan.speed}  sweep={'on' if fan.sweep else 'off'}  ospeed={osp}")
                elif cmd == "speed":
                    if len(args) != 1 or not args[0].isdigit():
                        print("usage: speed <1-15>")
                    else:
                        await fan.set_speed(int(args[0]))
                        print(f"speed → {args[0]}")
                elif cmd == "sweep":
                    if len(args) != 1 or args[0] not in ("0", "1"):
                        print("usage: sweep <0|1>")
                    else:
                        enable = bool(int(args[0]))
                        if bool(fan.sweep) == enable:
                            print(f"sweep already {'on' if enable else 'off'}")
                        else:
                            await fan.set_sweep(enable)
                            print(f"sweep → {'on' if enable else 'off'}")
                elif cmd == "ospeed":
                    if len(args) != 1 or args[0] not in ("1", "2", "3"):
                        print("usage: ospeed <1|2|3>  (1=Low 2=Medium 3=High)")
                    else:
                        osp = int(args[0])
                        await fan.set_oscillation_speed(osp)
                        print(f"ospeed → {['', 'Low', 'Medium', 'High'][osp]}")
                elif cmd == "center":
                    await fan.center_oscillation()
                    print("sweep → center")
                elif cmd == "sleep":
                    if len(args) != 1:
                        print("usage: sleep <minutes|off>")
                    elif args[0] == "off":
                        await fan.set_sleep_timer(0)
                        print("sleep timer cancelled")
                    elif args[0].isdigit() and 1 <= int(args[0]) <= 1440:
                        minutes = int(args[0])
                        await fan.set_sleep_timer(minutes)
                        print(f"sleep timer → {minutes} min")
                    else:
                        print("usage: sleep <1-1440|off>")
                elif cmd == "thermostat":
                    if len(args) != 1:
                        print("usage: thermostat <15-27|off>")
                    elif args[0] == "off":
                        await fan.clear_auto_mode()
                        print("thermostat → off")
                    elif args[0].isdigit() and 15 <= int(args[0]) <= 27:
                        t = int(args[0])
                        await fan.set_thermostat(t)
                        print(f"thermostat → {t}°C")
                    else:
                        print("usage: thermostat <15-27|off>")
                elif cmd == "sensors":
                    if not fan.sensors:
                        print("No sensor readings (pair sensors via the Williwaw app first).")
                    else:
                        for s in fan.sensors:
                            print(f"  {s.name}  {s.temperature:.1f}°C  bat={s.battery}%")
            except BleakGATTProtocolError as e:
                print(f"device error: {e}")
            except ValueError as e:
                print(f"error: {e}")

        else:
            print(f"Unknown command: {cmd!r}  (type 'help' for commands)")

    if fan and fan.is_connected:
        await cmd_disconnect()


def main() -> None:
    asyncio.run(repl())


if __name__ == "__main__":
    main()

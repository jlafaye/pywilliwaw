"""
Williwaw interactive REPL.

Commands (always available):
  devices               scan and list nearby BLE devices
  connect <name|#>      connect to a device by name or scan-list index
  quit                  exit

Commands (when connected):
  disconnect            disconnect from current device
  fan [0|off|1|on]      toggle fan, or set explicitly on/off
  speed <1-15>          set fan speed
  oscillation [0|off|1|on]  toggle oscillation, or set explicitly on/off
  ospeed <1-3>          set oscillation speed (1=Low 2=Medium 3=High)
  center                return sweep head to center
  sleep <minutes|off>   hardware sleep timer: turn off after N min (1–1440)
  thermostat <°C|off>   auto-mode: run fan while temp ≥ °C (15–27)
  sensors               show paired temperature sensors
  status                show current fan state
"""

import asyncio
import json
import logging
import readline  # noqa: F401 — enables up/down arrow history in input()
import sys
from pathlib import Path

from bleak.exc import BleakGATTProtocolError

from pywilliwaw import Williwaw, discover, find_by_address, find_by_name

fan: Williwaw | None = None
scan_results: list = []

_CONFIG_PATH = Path.home() / ".config" / "williwaw" / "fans.json"

# ── color helpers ──────────────────────────────────────────────────────────────

_USE_COLOR = sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text


def _dim(t: str) -> str:
    return _c("2", t)


def _bold(t: str) -> str:
    return _c("1", t)


def _cyan(t: str) -> str:
    return _c("36", t)


def _green(t: str) -> str:
    return _c("32", t)


def _yellow(t: str) -> str:
    return _c("33", t)


def _red(t: str) -> str:
    return _c("31", t)


def _arrow(val: str) -> str:
    return f"{_cyan('→')} {_bold(val)}"


def _fan_state(on: bool) -> str:
    return _green("on") if on else _dim("off")


def _ok(msg: str) -> None:
    print(_green("✓") + " " + msg)


def _err(msg: str) -> None:
    print(_red("✗") + " " + msg)


def _fmt_status() -> str:
    osp = {1: "Low", 2: "Medium", 3: "High"}.get(fan.oscillation_speed, "?")
    parts = [
        f"fan={_fan_state(bool(fan.fan))}",
        f"speed={_bold(str(fan.speed))}",
        f"oscillation={_fan_state(bool(fan.oscillation))}",
        f"ospeed={_bold(osp)}",
    ]
    return "  ".join(parts)


# ── config persistence ─────────────────────────────────────────────────────────


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
    print(f"{_dim('Looking for')} {_bold(names)}…", end=" ", flush=True)

    async def scan_one(entry: dict):
        try:
            return await find_by_address(entry["address"], timeout=3.0)
        except Exception:
            return None

    scan_tasks = [asyncio.create_task(scan_one(e)) for e in known]
    done, pending = await asyncio.wait(
        scan_tasks, timeout=3.0, return_when=asyncio.FIRST_COMPLETED
    )
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
        print(_dim("not found, use 'connect'"))
        return

    try:
        f = Williwaw(device)
        await f.connect()
        fan = f
        print(_green("connected") + f" ({_bold(fan.name)})")
    except Exception:
        print(_yellow("found but could not connect, use 'connect'"))


# ── device commands ────────────────────────────────────────────────────────────


async def cmd_devices() -> None:
    global scan_results
    print(_dim("Scanning for 5 seconds…"))
    scan_results = await discover(timeout=5.0)
    scan_results.sort(key=lambda d: d.name or "")
    if not scan_results:
        print(_dim("No devices found."))
        return
    for i, d in enumerate(scan_results):
        idx = _cyan(f"[{i}]")
        name = _bold(d.name or "(unknown)")
        addr = _dim(d.address)
        print(f"  {idx}  {name:<40}  {addr}")


async def cmd_connect(target: str) -> None:
    global fan

    if fan and fan.is_connected:
        _err("Already connected. Run 'disconnect' first.")
        return

    if target.isdigit():
        idx = int(target)
        if not scan_results:
            _err("No scan results. Run 'devices' first.")
            return
        if idx >= len(scan_results):
            _err(f"Index {idx} out of range (0–{len(scan_results)-1}).")
            return
        device = scan_results[idx]
    else:
        print(_dim(f"Scanning for '{target}'…"))
        device = await find_by_name(target, timeout=10.0)
        if device is None:
            _err(f"Device '{target}' not found.")
            return

    print(_dim(f"Connecting to {device.name} ({device.address})…"))
    fan = Williwaw(device)
    await fan.connect()
    _save_known_fan(fan)
    print(_green("Connected.") + "  " + _fmt_status())


async def cmd_disconnect() -> None:
    global fan
    if not fan or not fan.is_connected:
        _err("Not connected.")
        return
    await fan.disconnect()
    fan = None
    print(_dim("Disconnected."))


# ── REPL loop ──────────────────────────────────────────────────────────────────


async def repl() -> None:
    loop = asyncio.get_running_loop()
    print(_bold("Williwaw") + _dim(" REPL. Type 'help' for commands.") + "\n")
    await _try_reconnect()

    while True:
        connected = fan and fan.is_connected
        if connected:
            prompt = _bold("williwaw") + _dim("@") + _cyan(fan.address) + _dim("> ")
        else:
            prompt = _dim("williwaw> ")

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
                _err("usage: connect <name|#>")
            else:
                await cmd_connect(" ".join(args))

        elif cmd == "disconnect":
            await cmd_disconnect()

        elif cmd in (
            "fan",
            "speed",
            "oscillation",
            "ospeed",
            "center",
            "sleep",
            "thermostat",
            "sensors",
            "status",
        ):
            if not connected:
                _err("Not connected. Use 'connect <name|#>' first.")
                continue
            try:
                if cmd == "fan":
                    if not args:
                        new_state = not fan.fan
                        await fan.toggle()
                        print(f"fan {_arrow('on' if new_state else 'off')}")
                    elif args[0] in ("1", "on"):
                        if fan.fan:
                            print(_dim("fan already on"))
                        else:
                            await fan.toggle()
                            print(f"fan {_arrow('on')}")
                    elif args[0] in ("0", "off"):
                        if not fan.fan:
                            print(_dim("fan already off"))
                        else:
                            await fan.toggle()
                            print(f"fan {_arrow('off')}")
                    else:
                        _err("usage: fan [0|off|1|on]")
                elif cmd == "status":
                    print(_fmt_status())
                elif cmd == "speed":
                    if len(args) != 1 or not args[0].isdigit():
                        _err("usage: speed <1-15>")
                    else:
                        await fan.set_speed(int(args[0]))
                        print(f"speed {_arrow(args[0])}")
                elif cmd == "oscillation":
                    if not args:
                        enable = not bool(fan.oscillation)
                        await fan.set_oscillation(enable)
                        print(f"oscillation {_arrow('on' if enable else 'off')}")
                    elif args[0] in ("1", "on", "0", "off"):
                        enable = args[0] in ("1", "on")
                        label = "on" if enable else "off"
                        if bool(fan.oscillation) == enable:
                            print(_dim(f"oscillation already {label}"))
                        else:
                            await fan.set_oscillation(enable)
                            print(f"oscillation {_arrow(label)}")
                    else:
                        _err("usage: oscillation [0|off|1|on]")
                elif cmd == "ospeed":
                    if len(args) != 1 or args[0] not in ("1", "2", "3"):
                        _err("usage: ospeed <1|2|3>  (1=Low 2=Medium 3=High)")
                    else:
                        osp = int(args[0])
                        await fan.set_oscillation_speed(osp)
                        label = ["", "Low", "Medium", "High"][osp]
                        print(f"ospeed {_arrow(label)}")
                elif cmd == "center":
                    await fan.center_oscillation()
                    print(f"oscillation {_arrow('center')}")
                elif cmd == "sleep":
                    if len(args) != 1:
                        _err("usage: sleep <minutes|off>")
                    elif args[0] == "off":
                        await fan.set_sleep_timer(0)
                        print(_dim("sleep timer cancelled"))
                    elif args[0].isdigit() and 1 <= int(args[0]) <= 1440:
                        minutes = int(args[0])
                        await fan.set_sleep_timer(minutes)
                        print(f"sleep timer {_arrow(f'{minutes} min')}")
                    else:
                        _err("usage: sleep <1-1440|off>")
                elif cmd == "thermostat":
                    if len(args) != 1:
                        _err("usage: thermostat <15-27|off>")
                    elif args[0] == "off":
                        await fan.clear_auto_mode()
                        print(f"thermostat {_arrow('off')}")
                    elif args[0].isdigit() and 15 <= int(args[0]) <= 27:
                        t = int(args[0])
                        await fan.set_thermostat(t)
                        print(f"thermostat {_arrow(f'{t}°C')}")
                    else:
                        _err("usage: thermostat <15-27|off>")
                elif cmd == "sensors":
                    if not fan.sensors:
                        print(
                            _dim(
                                "No sensor readings (pair sensors via the Williwaw app first)."
                            )
                        )
                    else:
                        for s in fan.sensors:
                            temp = _bold(f"{s.temperature:.1f}°C")
                            bat = _dim(f"bat={s.battery}%")
                            print(f"  {_cyan(s.name)}  {temp}  {bat}")
            except BleakGATTProtocolError as e:
                _err(f"device error: {e}")
            except ValueError as e:
                _err(f"{e}")

        else:
            _err(f"Unknown command: {cmd!r}  (type 'help' for commands)")

    if fan and fan.is_connected:
        await cmd_disconnect()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    asyncio.run(repl())


if __name__ == "__main__":
    main()

"""
Williwaw interactive REPL.

Commands (always available):
  devices               scan and list nearby BLE devices
  connect <name|#>      connect to a device by name or scan-list index
  quit                  exit

Commands (when connected):
  disconnect            disconnect from current device
  toggle                toggle fan on/off
  speed <1-15>          set fan speed
  sweep <0|1>           enable or disable sweep
  sleep <minutes|off>   set/cancel sleep timer (1–1440 min)
  status                show current state
"""

import asyncio
import json
import readline  # noqa: F401 — enables up/down arrow history in input()
from pathlib import Path

from bleak.exc import BleakGATTProtocolError

from pywilliwaw import Williwaw, discover, find_by_address, find_by_name

fan: Williwaw | None = None
scan_results: list = []
_sleep_task: asyncio.Task | None = None

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


# ── sleep timer (software) ────────────────────────────────────────────────────

async def _sleep_worker(minutes: int) -> None:
    await asyncio.sleep(minutes * 60)
    if fan and fan.is_connected:
        try:
            await fan.toggle()
            print(f"\n[sleep] fan turned off after {minutes} min")
        except Exception as e:
            print(f"\n[sleep] error: {e}")


def _cancel_sleep() -> bool:
    global _sleep_task
    if _sleep_task and not _sleep_task.done():
        _sleep_task.cancel()
        _sleep_task = None
        return True
    return False


# ── startup reconnect ──────────────────────────────────────────────────────────

async def _try_reconnect() -> None:
    global fan
    known = _load_known_fans()
    if not known:
        return

    names = ", ".join(e["name"] for e in known)
    print(f"Looking for known fan(s) ({names})…", end=" ", flush=True)

    async def connect_one(entry: dict) -> Williwaw | None:
        try:
            device = await find_by_address(entry["address"], timeout=3.0)
            if device is None:
                return None
            f = Williwaw(device)
            await f.connect()
            return f
        except Exception:
            return None

    tasks = [asyncio.create_task(connect_one(e)) for e in known]
    done, pending = await asyncio.wait(tasks, timeout=3.0, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()

    for t in done:
        try:
            result = t.result()
            if result is not None:
                fan = result
                break
        except Exception:
            pass

    print(f"connected ({fan.name})" if fan else "not found, use 'connect'")


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
    _cancel_sleep()
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

        elif cmd in ("toggle", "speed", "sweep", "sleep", "status"):
            if not connected:
                print("Not connected. Use 'connect <name|#>' first.")
                continue
            try:
                if cmd == "toggle":
                    await fan.toggle()
                elif cmd == "status":
                    print(f"fan={'on' if fan.fan else 'off'}  speed={fan.speed}  sweep={'on' if fan.sweep else 'off'}")
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
                elif cmd == "sleep":
                    if len(args) != 1:
                        print("usage: sleep <minutes|off>")
                    elif args[0] == "off":
                        if _cancel_sleep():
                            print("sleep timer cancelled")
                        else:
                            print("no active sleep timer")
                    elif args[0].isdigit() and 1 <= int(args[0]) <= 1440:
                        _cancel_sleep()
                        minutes = int(args[0])
                        _sleep_task = asyncio.create_task(_sleep_worker(minutes))
                        print(f"sleep timer → {minutes} min")
                    else:
                        print("usage: sleep <1-1440|off>")
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

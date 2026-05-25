# pywilliwaw

A Python library and interactive CLI to control the **Williwaw** fan over Bluetooth Low Energy (BLE).

The Williwaw is an exceptional fan — whisper-quiet, efficient, and a genuine step up from traditional fans. If you're curious about the hardware, visit the official website: [williwaw.eu](https://www.williwaw.eu/en/).

> **Disclaimer:** This project is an independent effort based on reverse-engineered BLE traffic. It is **not affiliated with, endorsed by, or supported by Williwaw** in any way. Use it at your own risk. The authors cannot be held responsible for any damage to your fan, device, or related equipment resulting from use of this software.

---

## Requirements

- Python 3.10 or later
- A Bluetooth adapter supported by [bleak](https://github.com/hbldh/bleak)
- macOS, Linux, or Windows (platform support follows bleak)

---

## Installation

Clone the repository and install the package in a virtual environment:

```bash
git clone <repo-url>
cd williwaw

python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

pip install -e .
```

This installs the `pywilliwaw` Python package and the `williwaw-cli` command.

---

## Library usage

```python
import asyncio
from pywilliwaw import Williwaw, find_by_name

async def main():
    device = await find_by_name("Williwaw")
    fan = Williwaw(device)
    await fan.connect()

    await fan.set_speed(7)       # speed 1–15
    await fan.toggle()           # toggle fan on/off
    await fan.set_sweep(True)    # enable oscillation
    await fan.set_sleep_timer(30)  # turn off after 30 minutes

    print(f"fan={'on' if fan.fan else 'off'}  speed={fan.speed}  sweep={fan.sweep}")
    await fan.disconnect()

asyncio.run(main())
```

### Discovering nearby fans

```python
from pywilliwaw import discover

async def scan():
    devices = await discover(timeout=5.0)
    for d in devices:
        print(d.name, d.address)
```

### `Williwaw` class reference

| Method | Description |
|---|---|
| `await fan.connect()` | Connect and seed state from device |
| `await fan.disconnect()` | Disconnect cleanly |
| `await fan.toggle()` | Toggle fan ON↔OFF |
| `await fan.set_speed(speed)` | Set speed (1–15) |
| `await fan.set_sweep(enable)` | Enable/disable oscillation |
| `await fan.set_sleep_timer(minutes)` | Sleep timer in minutes (0 cancels, max 1440) |

State is updated automatically from BLE notifications:

| Attribute | Type | Description |
|---|---|---|
| `fan.fan` | `int` | 1 = on, 0 = off |
| `fan.speed` | `int` | Current speed (1–15) |
| `fan.sweep` | `int` | 1 = oscillating, 0 = fixed |

---

## CLI usage

Start the interactive REPL:

```bash
williwaw-cli
```

You will see a prompt:

```
Williwaw REPL. Type 'help' for commands.

williwaw>
```

Once connected, the prompt includes the device address:

```
williwaw@EC:92:6D:A1:2E:7F>
```

### Supported commands

#### Always available

| Command | Description |
|---|---|
| `devices` | Scan for nearby BLE devices and list them with an index |
| `connect <name\|#>` | Connect by device name or scan-list index (e.g. `connect Williwaw` or `connect 0`) |
| `help` | Show command reference |
| `quit` | Exit the CLI |

#### When connected

| Command | Description |
|---|---|
| `disconnect` | Disconnect from the current device |
| `status` | Show current fan state (on/off, speed, sweep) |
| `fan` | Toggle the fan on or off |
| `speed <1-15>` | Set fan speed |
| `sweep <0\|1>` | Disable (`0`) or enable (`1`) oscillation |
| `sleep <minutes\|off>` | Set a sleep timer (1–1440 min); `sleep off` cancels it |

### Example session

```
williwaw> devices
Scanning for 5 seconds…
  [0]  Williwaw                        EC:92:6D:A1:2E:7F

williwaw> connect 0
Connecting to Williwaw (EC:92:6D:A1:2E:7F)…
Connected.  fan=on  speed=3  sweep=off

williwaw@EC:92:6D:A1:2E:7F> speed 7
speed → 7

williwaw@EC:92:6D:A1:2E:7F> sweep 1
sweep → on

williwaw@EC:92:6D:A1:2E:7F> sleep 30
sleep timer → 30 min

williwaw@EC:92:6D:A1:2E:7F> status
fan=on  speed=7  sweep=on

williwaw@EC:92:6D:A1:2E:7F> fan
williwaw@EC:92:6D:A1:2E:7F> status
fan=off  speed=7  sweep=on

williwaw@EC:92:6D:A1:2E:7F> quit
Disconnected.
```

---

## Project structure

```
src/pywilliwaw/
    __init__.py     public API
    protocol.py     BLE packet builders and constants
    fan.py          Williwaw class (BLE connection + state)
    cli.py          interactive REPL (williwaw-cli entry point)
```

---

## Limitations

- **Thermal probe integration is not supported** — closing the loop with temperature sensors to drive fan speed automatically is not yet implemented.

---

## License

MIT

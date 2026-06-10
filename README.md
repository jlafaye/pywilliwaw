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

    await fan.set_speed(7)           # speed 1–15
    await fan.toggle()               # toggle fan on/off
    await fan.set_oscillation(True)  # enable oscillation
    await fan.set_sleep_timer(30)    # turn off after 30 minutes

    print(f"fan={'on' if fan.fan else 'off'}  speed={fan.speed}  oscillation={fan.oscillation}")
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
| `await fan.set_oscillation(enable)` | Enable/disable oscillation |
| `await fan.set_oscillation_speed(speed)` | Set oscillation speed (1=Low, 2=Medium, 3=High) |
| `await fan.center_oscillation()` | Return sweep head to center position |
| `await fan.set_sleep_timer(minutes)` | Hardware sleep timer: fan turns itself off after N minutes (0 cancels, max 1440) |
| `await fan.set_thermostat(threshold_c)` | Auto-mode: run fan while temperature ≥ threshold °C (requires paired sensor) |
| `await fan.set_temp_diff_mode(delta_c)` | Auto-mode: run fan while (sensorA − sensorB) ≥ delta °C (requires two sensors) |
| `await fan.clear_auto_mode()` | Disable thermostat / temp-differential auto-mode |
| `await fan.calibrate_sensors()` | Calibrate paired temperature sensors |
| `await fan.remove_sensors()` | Unpair all temperature sensors |

State is updated automatically from BLE notifications:

| Attribute | Type | Description |
|---|---|---|
| `fan.fan` | `int` | 1 = on, 0 = off |
| `fan.speed` | `int` | Current speed (1–15) |
| `fan.oscillation` | `int` | 1 = oscillating, 0 = fixed |
| `fan.oscillation_speed` | `int` | Oscillation speed: 1=Low, 2=Medium, 3=High |
| `fan.sched_timer_type` | `int` | Active timer: 0=none, 1=scheduled-start, 2=scheduled-stop |
| `fan.sched_remaining_s` | `int` | Seconds remaining on active timer |
| `fan.sensors` | `list[TemperatureSensor]` | Paired temperature sensor readings |

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
| `status` | Show current fan state (on/off, speed, oscillation, oscillation speed) |
| `fan [0\|off\|1\|on]` | Toggle the fan on or off, or set explicitly |
| `speed <1-15>` | Set fan speed |
| `oscillation [0\|off\|1\|on]` | Disable (`0`/`off`) or enable (`1`/`on`) oscillation, or toggle |
| `ospeed <1\|2\|3>` | Set oscillation speed (1=Low, 2=Medium, 3=High) |
| `center` | Return sweep head to center position |
| `sleep <minutes\|off>` | Hardware sleep timer (1–1440 min); `sleep off` cancels it |
| `thermostat <15-27\|off>` | Auto-mode: run while temperature ≥ °C; requires a paired sensor |
| `sensors` | Show paired temperature sensor readings |

### Example session

```
williwaw> devices
Scanning for 5 seconds…
  [0]  Williwaw                        EC:92:6D:A1:2E:7F

williwaw> connect 0
Connecting to Williwaw (EC:92:6D:A1:2E:7F)…
Connected.  fan=on  speed=3  oscillation=off

williwaw@EC:92:6D:A1:2E:7F> speed 7
speed → 7

williwaw@EC:92:6D:A1:2E:7F> oscillation 1
oscillation → on

williwaw@EC:92:6D:A1:2E:7F> sleep 30
sleep timer → 30 min

williwaw@EC:92:6D:A1:2E:7F> status
fan=on  speed=7  oscillation=on

williwaw@EC:92:6D:A1:2E:7F> fan off
fan → off

williwaw@EC:92:6D:A1:2E:7F> status
fan=off  speed=7  oscillation=on

williwaw@EC:92:6D:A1:2E:7F> quit
Disconnected.
```

---

## Home Assistant integration

A custom integration is included in `custom_components/williwaw/`. It exposes
the fan as a **fan entity** (on/off, speed, oscillation), any paired
temperature sensors as **sensor entities** (temperature + battery), and the
hardware sleep timer as a **number entity**.

### Installation via HACS (recommended)

1. In Home Assistant, open **HACS → Integrations**.
2. Click the three-dot menu (⋮) in the top-right corner and choose **Custom repositories**.
3. Paste `https://github.com/jlafaye/pywilliwaw` and set the category to **Integration**, then click **Add**.
4. Search for *Williwaw* in HACS, click **Download**, and confirm.
5. Restart Home Assistant.

HACS will install the `pywilliwaw` Python library automatically — no manual `pip` step needed.

### Manual installation

1. Copy the `custom_components/williwaw/` folder into your Home Assistant
   `config/custom_components/` directory.
2. Restart Home Assistant — the `pywilliwaw` dependency is declared in
   `manifest.json` and will be installed automatically from PyPI.

### Adding the device

- **Auto-discovery:** If your Williwaw fan is powered on and in Bluetooth
  range, Home Assistant will detect it automatically and show a discovery
  notification. Accept it to add the integration.
- **Manual setup:** Go to **Settings → Devices & Services → Add Integration**,
  search for *Williwaw*, and enter the Bluetooth MAC address of your fan
  (visible in the Williwaw app under device settings).

### Entities

| Entity | Platform | Description |
|--------|----------|-------------|
| Fan | `fan` | On/off, speed (1–15 as 1–100 %), oscillation toggle |
| W Sensor XXYY Temperature | `sensor` | Temperature in °C for each paired sensor |
| W Sensor XXYY Battery | `sensor` | Battery level (%) for each paired sensor |
| Sleep Timer | `number` | Hardware sleep timer in minutes (0 = cancel, max 1440) |

Temperature sensors are added dynamically as they are discovered via BLE
notifications — they appear in HA shortly after the fan connects.

---

## Project structure

```
src/pywilliwaw/
    __init__.py     public API
    protocol.py     BLE packet builders and constants
    fan.py          Williwaw class (BLE connection + state)
    cli.py          interactive REPL (williwaw-cli entry point)

custom_components/williwaw/
    __init__.py     integration setup / teardown
    manifest.json   HA integration metadata
    config_flow.py  UI setup flow (auto-discovery + manual)
    coordinator.py  BLE connection manager, state fan-out
    fan.py          fan entity
    sensor.py       temperature + battery sensor entities
    number.py       sleep timer entity
```

---

## Temperature sensors

The Williwaw fan can be paired with up to two Williwaw Bluetooth temperature sensors (small wireless thermometers sold separately). Once paired via the official app:

- The `thermostat` CLI command (or `set_thermostat()` API) lets the fan run automatically whenever the measured temperature reaches a set threshold.
- The `set_temp_diff_mode()` API enables two-sensor differential mode: the fan runs when the temperature difference between sensor A and sensor B exceeds a configurable delta.

Sensor readings are delivered via BLE notifications on the `SENSORLIST_CHAR` characteristic and are available in `fan.sensors`.

---

## License

MIT

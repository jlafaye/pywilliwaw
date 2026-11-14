# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

`pywilliwaw` is an async Python library (built on `bleak`) plus an interactive REPL (`williwaw-cli`) for controlling the Williwaw fan over BLE. The protocol is reverse-engineered from captured Bluetooth traffic; `PROTOCOL.md` is the reference for packet layouts, GATT handles and characteristic semantics. It is unaffiliated with the vendor.

## Commands

```bash
python3 -m venv venv && source venv/bin/activate
pip install -e .          # installs the package and the `williwaw-cli` entry point
williwaw-cli              # interactive REPL (needs a real BLE adapter and fan)
python -m build           # build sdist/wheel (what the release workflow runs)
```

There is no test suite, linter config or formatter config in the repo. Most behaviour can only be verified against real hardware.

Versioning comes from git tags via `setuptools-scm` (no version field in `pyproject.toml`). Pushing a `vX.Y.Z` tag triggers `.github/workflows/publish.yml`, which builds and publishes to PyPI.

## Architecture

- `src/pywilliwaw/protocol.py` — GATT UUIDs (vendor base `0bc7xxxx-ac91-4a15-ae2d-4fad27e55276`), limits, 1-byte command opcodes for `COMMAND_CHAR`, and the `FanControlPacket` dataclass (the 19-byte struct on `FANCONTROL_CHAR`).
- `src/pywilliwaw/fan.py` — `Williwaw` class wrapping a `BleakClient`, plus `discover` / `find_by_name` / `find_by_address`.
- `src/pywilliwaw/cli.py` — REPL on top of the `Williwaw` class.
- `src/pywilliwaw/__init__.py` — public API; new public names must be added both to the imports and to `__all__`.

Key design points that span files:

- **Two write styles.** Simple actions (fan toggle, oscillation toggle, center, calibrate) write a 1-byte opcode to `COMMAND_CHAR`. All settings (speed, oscillation speed, sleep/wake timers, thermostat, temp-diff mode) are done by read-modify-write of the whole `FanControlPacket`: `Williwaw` keeps the last packet received in `_control_packet`, derives a new one with an immutable `with_*()` helper, and writes it back to `FANCONTROL_CHAR`. A new setting normally means a new field and `with_*` method in `protocol.py` and a method in `fan.py`.
- **State comes from notifications.** `connect()` reads `FANCONTROL_CHAR` once, then subscribes to `FANCONTROL_CHAR`, `FANSTATE_CHAR` (power + scheduled-timer state) and `SENSORLIST_CHAR` (temperature sensors). The `_apply_*` methods update the public attributes (`fan`, `speed`, `oscillation`, `sched_*`, `sensors`, ...) and fire the `on_update` callback. Setters do not update attributes locally; they wait for the device to notify. Toggles are guarded accordingly (e.g. `set_oscillation` is a no-op if state already matches, since the device only exposes a toggle).
- `FANSTATE_CHAR` and `SENSORLIST_CHAR` are optional: failure to subscribe is logged and tolerated.
- `Williwaw` takes `on_update` and `on_disconnect` callbacks so that embedders (e.g. Home Assistant) can react to state changes and drops.

## `custom_components/williwaw/`

A Home Assistant custom integration (fan, sensor and number entities, a `WilliwawCoordinator` that owns the connection and auto-reconnects every 30 s). It is a leftover: the README states the integration was moved to the separate `jlafaye/williwaw-ha` repo. It depends on the PyPI release (`pywilliwaw>=1.2.0` in `manifest.json`), not on `src/`. Treat it as legacy and confirm before editing it; library API changes there must stay compatible.

## Other

- `firmwares/` holds vendor Android app packages (APK/XAPK) used for reverse engineering; don't modify them.

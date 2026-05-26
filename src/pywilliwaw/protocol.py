"""Williwaw BLE protocol constants and packet helpers."""

import struct

DEVICE_NAME = "Williwaw"

# ── GATT service (Williwaw proprietary) ───────────────────────────────────────
WILLIWAW_SVC = "0bc70000-ac91-4a15-ae2d-4fad27e55276"

# Characteristics within WILLIWAW_SVC
COMMAND_CHAR  = "0bc70001-ac91-4a15-ae2d-4fad27e55276"  # write — 1-byte commands
FANCONTROL_CHAR = "0bc70002-ac91-4a15-ae2d-4fad27e55276"  # read/write/notify — 19-byte status
SENSORS_CHAR  = "0bc70003-ac91-4a15-ae2d-4fad27e55276"  # read/write/notify — sensor MAC addresses
SENSORLIST_CHAR = "0bc70004-ac91-4a15-ae2d-4fad27e55276"  # notify — sensor readings
ONLINETIME_CHAR = "0bc70005-ac91-4a15-ae2d-4fad27e55276"  # (unknown use)
FANSTATE_CHAR = "0bc70006-ac91-4a15-ae2d-4fad27e55276"  # read/notify — 6-byte power+timer state
DEVICENAME_CHAR = "0bc70007-ac91-4a15-ae2d-4fad27e55276"  # read/write/notify — UTF-8 name

# ── Standard GATT (Device Information Service) ────────────────────────────────
DEVICE_INFO_SVC = "0000180a-0000-1000-8000-00805f9b34fb"
FIRMWARE_REV_CHAR = "00002a26-0000-1000-8000-00805f9b34fb"

# Backward-compatible aliases
SWEEP_CHAR = COMMAND_CHAR
SPEED_CHAR = FANCONTROL_CHAR

# ── Fan limits ────────────────────────────────────────────────────────────────
SPEED_MIN = 1
SPEED_MAX = 15

OSCILLATION_SPEED_LOW    = 1
OSCILLATION_SPEED_MEDIUM = 2
OSCILLATION_SPEED_HIGH   = 3

SLEEP_MAX_MIN = 1440  # 24 h

# ── COMMAND characteristic — 1-byte opcodes ───────────────────────────────────
CMD_FAN_TOGGLE   = bytes([0x02])  # toggle power ON↔OFF
CMD_SWEEP_TOGGLE = bytes([0x03])  # toggle oscillation ON↔OFF
CMD_CENTER       = bytes([0x00])  # return sweep head to center position
CMD_CALIBRATE    = bytes([0x04])  # calibrate paired temperature sensors


def make_fan_toggle_cmd() -> bytes:
    return CMD_FAN_TOGGLE


def make_sweep_toggle_cmd() -> bytes:
    return CMD_SWEEP_TOGGLE


def make_center_cmd() -> bytes:
    """Return sweep head to center."""
    return CMD_CENTER


def make_calibrate_sensors_cmd() -> bytes:
    """Calibrate paired temperature sensors."""
    return CMD_CALIBRATE


# ── FANCONTROL characteristic — 19-byte packet helpers ────────────────────────
#
# Byte layout (confirmed from decompiled app source):
#   [0]    mode: 0 = idle/scheduled-start, 1 = running
#   [1]    speed (1–15)
#   [2]    oscillation: 0 = off, 1 = on
#   [3]    oscillation speed: 1 = Low, 2 = Medium, 3 = High
#   [4:12] device-internal fields (preserve as-is from device read)
#   [12]   auto-mode: 0 = none, 1 = thermostat, 2 = temp-differential
#   [13]   auto-mode param: threshold °C (thermostat) or delta °C (temp-diff)
#   [14]   reserved
#   [15:17] scheduled-start: minutes until start (LE uint16; 0 = none)
#   [17:19] scheduled-stop: minutes until stop  (LE uint16; 0 = none)

def _default_status() -> bytearray:
    """Default 19-byte FANCONTROL packet (fan on, speed 1, no sweep, medium osc speed)."""
    b = bytearray(19)
    b[0] = 0x01   # running
    b[1] = 0x01   # speed 1
    b[2] = 0x00   # oscillation off
    b[3] = 0x02   # oscillation speed medium
    b[8] = 0x02   # device-internal (observed from captures)
    b[13] = 0x01  # auto-mode param default (observed from captures)
    return b


def make_speed_cmd(speed: int, sweep: int = 0) -> bytes:
    """19-byte FANCONTROL packet — set speed (and optionally oscillation state).
    Prefer status_with_speed() when you have the current device status."""
    b = _default_status()
    b[1] = speed
    b[2] = int(bool(sweep))
    return bytes(b)


def status_with_speed(status: bytes | bytearray, speed: int) -> bytes:
    b = bytearray(status)
    b[1] = speed
    return bytes(b)


def status_with_sweep(status: bytes | bytearray, enable: bool) -> bytes:
    b = bytearray(status)
    b[2] = 1 if enable else 0
    return bytes(b)


def status_with_oscillation_speed(status: bytes | bytearray, osc_speed: int) -> bytes:
    """osc_speed: 1=Low, 2=Medium, 3=High."""
    b = bytearray(status)
    b[3] = osc_speed
    return bytes(b)


def status_with_thermostat(status: bytes | bytearray, threshold_c: int) -> bytes:
    """Enable thermostat auto-mode: fan runs when temp >= threshold_c."""
    b = bytearray(status)
    b[0] = 1
    b[12] = 1
    b[13] = threshold_c & 0xFF
    return bytes(b)


def status_with_temp_diff(status: bytes | bytearray, delta_c: int) -> bytes:
    """Enable temperature-differential mode: fan runs when (sensorA - sensorB) >= delta_c."""
    b = bytearray(status)
    b[0] = 1
    b[12] = 2
    b[13] = delta_c & 0xFF
    return bytes(b)


def status_clear_auto_mode(status: bytes | bytearray) -> bytes:
    """Clear thermostat / temp-differential auto-mode."""
    b = bytearray(status)
    b[0] = 0
    b[12] = 0
    b[13] = 19  # app default when clearing
    return bytes(b)


def status_with_scheduled_stop(status: bytes | bytearray, minutes: int) -> bytes:
    """Set scheduled-stop timer (0 cancels)."""
    b = bytearray(status)
    b[17] = minutes & 0xFF
    b[18] = (minutes >> 8) & 0xFF
    return bytes(b)


def make_wake_timer_cmd(speed: int, sweep: int, minutes: int) -> bytes:
    """Scheduled-start: turns fan OFF and restarts it after N minutes (0 cancels).
    Deprecated: use status_* helpers with the live device status instead."""
    b = _default_status()
    b[0] = 0x00  # fan off until timer fires
    b[1] = speed
    b[2] = int(bool(sweep))
    b[15] = minutes & 0xFF
    b[16] = (minutes >> 8) & 0xFF
    return bytes(b)

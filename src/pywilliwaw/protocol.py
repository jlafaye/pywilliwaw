"""Williwaw BLE protocol constants and packet helpers."""

import struct

DEVICE_NAME = "Williwaw"

# GATT characteristic UUIDs (Williwaw control service 0bc70000-…)
SPEED_CHAR = "0bc70002-ac91-4a15-ae2d-4fad27e55276"  # handle 0x001b — read/write/notify
SWEEP_CHAR = "0bc70001-ac91-4a15-ae2d-4fad27e55276"  # handle 0x0014 — write (toggle)

SPEED_MIN = 1
SPEED_MAX = 15
SLEEP_MAX_MIN = 1440  # 24 h

_TAIL = bytes([
    0x02, 0x00, 0x00, 0x00, 0x00,
    0x02, 0x00, 0x00, 0x00, 0x00,
    0x01, 0x00, 0x00, 0x00, 0x00, 0x00,
])


def make_fan_toggle_cmd() -> bytes:
    """1-byte command for SWEEP_CHAR — toggles fan ON↔OFF."""
    return bytes([0x02])


def make_sweep_toggle_cmd() -> bytes:
    """1-byte command for SWEEP_CHAR — toggles sweep ON↔OFF."""
    return bytes([0x03])


def make_speed_cmd(speed: int, sweep: int = 0) -> bytes:
    """19-byte command for SPEED_CHAR — sets fan speed."""
    return bytes([0x01, speed, sweep]) + _TAIL


def make_wake_timer_cmd(speed: int, sweep: int, minutes: int) -> bytes:
    """19-byte command for SPEED_CHAR — delayed start: turns fan OFF, restarts after N minutes (0 cancels)."""
    return (bytes([0x00, speed, sweep])
            + _TAIL[:12]
            + struct.pack("<H", minutes)
            + bytes([0x00, 0x00]))

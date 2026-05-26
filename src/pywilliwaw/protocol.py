"""Williwaw BLE protocol constants and packet helpers."""

import struct
from dataclasses import dataclass, field, replace

from bleak.uuids import normalize_uuid_16

DEVICE_NAME = "Williwaw"


def _vendor_uuid_16(short: int) -> str:
    # Expands a 16-bit offset into the Williwaw vendor UUID space (base 0bc7xxxx-ac91-4a15-ae2d-4fad27e55276)
    return f"0bc7{short:04x}-ac91-4a15-ae2d-4fad27e55276"


# ── GATT service (Williwaw proprietary) ───────────────────────────────────────
WILLIWAW_SVC    = _vendor_uuid_16(0x0000)

# Characteristics within WILLIWAW_SVC
COMMAND_CHAR    = _vendor_uuid_16(0x0001)  # write — 1-byte commands
FANCONTROL_CHAR = _vendor_uuid_16(0x0002)  # read/write/notify — 19-byte status
SENSORS_CHAR    = _vendor_uuid_16(0x0003)  # read/write/notify — sensor MAC addresses
SENSORLIST_CHAR = _vendor_uuid_16(0x0004)  # notify — sensor readings
ONLINETIME_CHAR = _vendor_uuid_16(0x0005)  # (unknown use)
FANSTATE_CHAR   = _vendor_uuid_16(0x0006)  # read/notify — 6-byte power+timer state
DEVICENAME_CHAR = _vendor_uuid_16(0x0007)  # read/write/notify — UTF-8 name

# ── Standard GATT (Device Information Service) ────────────────────────────────
DEVICE_INFO_SVC   = normalize_uuid_16(0x180A)  # Device Information
FIRMWARE_REV_CHAR = normalize_uuid_16(0x2A26)  # Firmware Revision String


# ── Fan limits ────────────────────────────────────────────────────────────────
SPEED_MIN = 1
SPEED_MAX = 15

OSCILLATION_SPEED_LOW    = 1
OSCILLATION_SPEED_MEDIUM = 2
OSCILLATION_SPEED_HIGH   = 3

SLEEP_MAX_MIN = 1440  # 24 h

AUTO_MODE_PARAM_DEFAULT = 19  # app default written to byte[13] when clearing auto-mode

# ── COMMAND characteristic — 1-byte opcodes ───────────────────────────────────
CMD_FAN_TOGGLE   = bytes([0x02])  # toggle power ON↔OFF
CMD_OSCILLATION_TOGGLE = bytes([0x03])  # toggle oscillation ON↔OFF
CMD_CENTER       = bytes([0x00])  # return sweep head to center position
CMD_CALIBRATE    = bytes([0x04])  # calibrate paired temperature sensors


def make_fan_toggle_cmd() -> bytes:
    return CMD_FAN_TOGGLE


def make_oscillation_toggle_cmd() -> bytes:
    return CMD_OSCILLATION_TOGGLE


def make_center_cmd() -> bytes:
    """Return sweep head to center."""
    return CMD_CENTER


def make_calibrate_sensors_cmd() -> bytes:
    """Calibrate paired temperature sensors."""
    return CMD_CALIBRATE


# ── FANCONTROL characteristic — 19-byte packet ────────────────────────────────

@dataclass
class FanControlPacket:
    """19-byte FANCONTROL characteristic packet.

    Byte layout (confirmed from decompiled app source):
      [0]     mode: 0=idle/scheduled-start, 1=running
      [1]     speed (1–15)
      [2]     oscillation: 0=off, 1=on
      [3]     oscillation speed: 1=Low, 2=Medium, 3=High
      [4:12]  device-internal fields (round-tripped as-is from device)
      [12]    auto-mode: 0=none, 1=thermostat, 2=temp-differential
      [13]    auto-mode param: threshold °C (thermostat) or delta °C (temp-diff)
      [14]    reserved
      [15:17] scheduled-start: minutes until start (LE uint16; 0=none)
      [17:19] scheduled-stop: minutes until stop (LE uint16; 0=none)
    """
    mode: int = 1
    speed: int = 1
    oscillation: int = 0
    oscillation_speed: int = OSCILLATION_SPEED_MEDIUM
    _internal: bytes = field(default_factory=lambda: bytes([0, 0, 0, 0, 0x02, 0, 0, 0]))
    auto_mode: int = 0
    auto_mode_param: int = 1
    scheduled_start_min: int = 0
    scheduled_stop_min: int = 0

    @classmethod
    def from_bytes(cls, data: bytes | bytearray) -> "FanControlPacket":
        return cls(
            mode=data[0],
            speed=data[1],
            oscillation=data[2],
            oscillation_speed=data[3] or OSCILLATION_SPEED_MEDIUM,
            _internal=bytes(data[4:12]),
            auto_mode=data[12],
            auto_mode_param=data[13],
            scheduled_start_min=struct.unpack_from("<H", data, 15)[0],
            scheduled_stop_min=struct.unpack_from("<H", data, 17)[0],
        )

    def with_speed(self, speed: int) -> "FanControlPacket":
        return replace(self, speed=speed)

    def with_oscillation_speed(self, osc_speed: int) -> "FanControlPacket":
        return replace(self, oscillation_speed=osc_speed)

    def with_scheduled_stop(self, minutes: int) -> "FanControlPacket":
        return replace(self, scheduled_stop_min=minutes)

    def with_scheduled_start(self, minutes: int) -> "FanControlPacket":
        return replace(self, mode=0, scheduled_start_min=minutes)

    def with_thermostat(self, threshold_c: int) -> "FanControlPacket":
        return replace(self, mode=1, auto_mode=1, auto_mode_param=threshold_c & 0xFF)

    def with_temp_diff(self, delta_c: int) -> "FanControlPacket":
        return replace(self, mode=1, auto_mode=2, auto_mode_param=delta_c & 0xFF)

    def with_auto_mode_cleared(self) -> "FanControlPacket":
        return replace(self, mode=0, auto_mode=0, auto_mode_param=AUTO_MODE_PARAM_DEFAULT)

    def to_bytes(self) -> bytes:
        b = bytearray(19)
        b[0] = self.mode
        b[1] = self.speed
        b[2] = self.oscillation
        b[3] = self.oscillation_speed
        b[4:12] = self._internal
        b[12] = self.auto_mode
        b[13] = self.auto_mode_param
        struct.pack_into("<H", b, 15, self.scheduled_start_min)
        struct.pack_into("<H", b, 17, self.scheduled_stop_min)
        return bytes(b)

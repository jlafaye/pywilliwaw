"""High-level Williwaw fan controller."""

import struct

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

from pywilliwaw.protocol import (
    COMMAND_CHAR,
    FANCONTROL_CHAR,
    FANSTATE_CHAR,
    SENSORS_CHAR,
    SENSORLIST_CHAR,
    DEVICENAME_CHAR,
    OSCILLATION_SPEED_LOW,
    OSCILLATION_SPEED_MEDIUM,
    OSCILLATION_SPEED_HIGH,
    SLEEP_MAX_MIN,
    SPEED_MAX,
    SPEED_MIN,
    CMD_FAN_TOGGLE,
    CMD_SWEEP_TOGGLE,
    CMD_CENTER,
    CMD_CALIBRATE,
    make_speed_cmd,
    status_with_speed,
    status_with_sweep,
    status_with_oscillation_speed,
    status_with_thermostat,
    status_with_temp_diff,
    status_clear_auto_mode,
    status_with_scheduled_stop,
)


class TemperatureSensor:
    """A paired Williwaw temperature sensor (Bluetooth thermometer)."""

    def __init__(self, address: bytes, rssi: int, battery: int, temperature: float):
        self.address = address            # 6-byte MAC address
        self.rssi = rssi
        self.battery = battery            # 0–100 %
        self.temperature = temperature    # °C

    @property
    def name(self) -> str:
        return f"W Sensor {self.address[1]:02X}{self.address[0]:02X}"

    def __repr__(self) -> str:
        return f"TemperatureSensor({self.name}, {self.temperature:.1f}°C, bat={self.battery}%)"

    @classmethod
    def _from_10bytes(cls, data: bytes) -> "TemperatureSensor":
        """Parse one 10-byte sensor entry from a FANSTATE or SENSORLIST packet."""
        address = data[:6]
        rssi = data[6]
        battery = data[7]
        temp_raw = struct.unpack_from("<h", data, 8)[0]   # signed 16-bit LE, unit = 0.01 °C
        temperature = round(temp_raw / 100.0, 1)
        return cls(address, rssi, battery, temperature)


class Williwaw:
    """BLE-backed controller for a Williwaw fan."""

    def __init__(self, device: BLEDevice):
        self._device = device
        self._client = BleakClient(device)
        self._status: bytearray = bytearray(19)  # live FANCONTROL packet

        # FANCONTROL-derived state
        self.fan: int = 0          # 1 = on, 0 = off  (from FANSTATE)
        self.speed: int = 0        # 1–15
        self.sweep: int = 0        # 1 = oscillating, 0 = fixed
        self.oscillation_speed: int = OSCILLATION_SPEED_MEDIUM  # 1/2/3

        # FANSTATE-derived state
        self.sched_timer_type: int = 0    # 0=none, 1=sched_start, 2=sched_stop
        self.sched_remaining_s: int = 0   # seconds remaining on active timer

        # Temperature sensors (populated from SENSORLIST notifications)
        self.sensors: list[TemperatureSensor] = []

        # Device name
        self.device_name: str = ""

    @property
    def name(self) -> str:
        return self._device.name or "(unknown)"

    @property
    def address(self) -> str:
        return self._device.address

    @property
    def is_connected(self) -> bool:
        return self._client.is_connected

    async def connect(self) -> None:
        await self._client.connect()
        raw = await self._client.read_gatt_char(FANCONTROL_CHAR)
        self._apply_fancontrol(raw)
        await self._client.start_notify(FANCONTROL_CHAR, self._on_fancontrol)
        try:
            state = await self._client.read_gatt_char(FANSTATE_CHAR)
            self._apply_fanstate(state)
            await self._client.start_notify(FANSTATE_CHAR, self._on_fanstate)
        except Exception:
            pass
        try:
            await self._client.start_notify(SENSORLIST_CHAR, self._on_sensorlist)
        except Exception:
            pass

    async def disconnect(self) -> None:
        try:
            await self._client.stop_notify(FANCONTROL_CHAR)
        except Exception:
            pass
        try:
            await self._client.stop_notify(FANSTATE_CHAR)
        except Exception:
            pass
        try:
            await self._client.stop_notify(SENSORLIST_CHAR)
        except Exception:
            pass
        await self._client.disconnect()

    # ── fan power ──────────────────────────────────────────────────────────────

    async def toggle(self) -> None:
        """Toggle fan ON↔OFF."""
        await self._client.write_gatt_char(COMMAND_CHAR, CMD_FAN_TOGGLE, response=True)

    # ── speed ──────────────────────────────────────────────────────────────────

    async def set_speed(self, speed: int) -> None:
        if not SPEED_MIN <= speed <= SPEED_MAX:
            raise ValueError(f"speed must be {SPEED_MIN}–{SPEED_MAX}")
        payload = status_with_speed(self._status, speed) if any(self._status) else make_speed_cmd(speed, self.sweep)
        await self._client.write_gatt_char(FANCONTROL_CHAR, payload, response=True)

    # ── oscillation ────────────────────────────────────────────────────────────

    async def set_sweep(self, enable: bool) -> None:
        """Toggle oscillation on/off."""
        if bool(self.sweep) == bool(enable):
            return
        await self._client.write_gatt_char(COMMAND_CHAR, CMD_SWEEP_TOGGLE, response=True)

    async def set_oscillation_speed(self, osc_speed: int) -> None:
        """Set oscillation speed: 1=Low, 2=Medium, 3=High."""
        if osc_speed not in (OSCILLATION_SPEED_LOW, OSCILLATION_SPEED_MEDIUM, OSCILLATION_SPEED_HIGH):
            raise ValueError("oscillation speed must be 1 (Low), 2 (Medium), or 3 (High)")
        payload = status_with_oscillation_speed(self._status, osc_speed)
        await self._client.write_gatt_char(FANCONTROL_CHAR, payload, response=True)

    async def center_oscillation(self) -> None:
        """Return sweep head to center position."""
        await self._client.write_gatt_char(COMMAND_CHAR, CMD_CENTER, response=True)

    # ── hardware scheduled stop (sleep timer) ─────────────────────────────────

    async def set_sleep_timer(self, minutes: int) -> None:
        """Hardware sleep timer: fan turns itself off after N minutes (0 cancels, max 1440)."""
        if not 0 <= minutes <= SLEEP_MAX_MIN:
            raise ValueError(f"minutes must be 0 (cancel) or 1–{SLEEP_MAX_MIN}")
        payload = status_with_scheduled_stop(self._status, minutes)
        await self._client.write_gatt_char(FANCONTROL_CHAR, payload, response=True)

    # ── auto-mode (requires paired temperature sensors) ────────────────────────

    async def set_thermostat(self, threshold_c: int) -> None:
        """Turn on thermostat mode: fan runs while temperature >= threshold_c (°C, 15–27)."""
        payload = status_with_thermostat(self._status, threshold_c)
        await self._client.write_gatt_char(FANCONTROL_CHAR, payload, response=True)

    async def set_temp_diff_mode(self, delta_c: int) -> None:
        """Turn on temp-differential mode: fan runs while (sensorA − sensorB) >= delta_c."""
        payload = status_with_temp_diff(self._status, delta_c)
        await self._client.write_gatt_char(FANCONTROL_CHAR, payload, response=True)

    async def clear_auto_mode(self) -> None:
        """Disable thermostat / temp-differential auto-mode."""
        payload = status_clear_auto_mode(self._status)
        await self._client.write_gatt_char(FANCONTROL_CHAR, payload, response=True)

    # ── temperature sensors ────────────────────────────────────────────────────

    async def calibrate_sensors(self) -> None:
        """Calibrate the paired temperature sensors."""
        await self._client.write_gatt_char(COMMAND_CHAR, CMD_CALIBRATE, response=True)

    async def remove_sensors(self) -> None:
        """Unpair all temperature sensors from the fan."""
        await self._client.write_gatt_char(SENSORS_CHAR, bytes(16), response=True)

    # ── legacy hardware wake timer ─────────────────────────────────────────────

    async def set_wake_timer(self, minutes: int) -> None:
        """Delayed start: turns fan OFF and restarts it after N minutes (0 cancels).
        Use set_sleep_timer() for a sleep timer instead."""
        from pywilliwaw.protocol import status_with_scheduled_stop, _default_status
        b = bytearray(self._status) if any(self._status) else _default_status()
        b[0] = 0x00  # fan off until timer fires
        b[15] = minutes & 0xFF
        b[16] = (minutes >> 8) & 0xFF
        await self._client.write_gatt_char(FANCONTROL_CHAR, bytes(b), response=True)

    # ── notification handlers ──────────────────────────────────────────────────

    def _on_fancontrol(self, _char, data: bytearray) -> None:
        self._apply_fancontrol(data)

    def _on_fanstate(self, _char, data: bytearray) -> None:
        self._apply_fanstate(data)

    def _on_sensorlist(self, _char, data: bytearray) -> None:
        self._apply_sensorlist(data)

    def _apply_fancontrol(self, data: bytearray) -> None:
        """Parse 19-byte FANCONTROL characteristic."""
        if len(data) < 3:
            return
        self._status = bytearray(data)
        self.speed = data[1]
        self.sweep = data[2]
        if len(data) > 3:
            self.oscillation_speed = data[3] or OSCILLATION_SPEED_MEDIUM

    def _apply_fanstate(self, data: bytearray) -> None:
        """Parse 6-byte FANSTATE characteristic: power + active timer."""
        if len(data) < 6:
            return
        self.fan = data[0]   # 0=off, 1=on
        self.sched_timer_type = data[1]
        self.sched_remaining_s = struct.unpack_from("<I", data, 2)[0]

    def _apply_sensorlist(self, data: bytearray) -> None:
        """Parse temperature sensor readings (10 bytes per sensor)."""
        sensors = []
        for i in range(0, len(data) - 9, 10):
            try:
                s = TemperatureSensor._from_10bytes(data[i:i + 10])
                if any(s.address):
                    sensors.append(s)
            except Exception:
                pass
        if sensors:
            self.sensors = sensors

    # ── backward-compat alias ──────────────────────────────────────────────────

    def _apply(self, data: bytearray) -> None:
        self._apply_fancontrol(data)


async def discover(timeout: float = 5.0) -> list[BLEDevice]:
    return await BleakScanner.discover(timeout=timeout)


async def find_by_name(name: str, timeout: float = 10.0) -> BLEDevice | None:
    return await BleakScanner.find_device_by_name(name, timeout=timeout)


async def find_by_address(address: str, timeout: float = 10.0) -> BLEDevice | None:
    return await BleakScanner.find_device_by_address(address, timeout=timeout)

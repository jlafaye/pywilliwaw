"""High-level Williwaw fan controller."""

import logging
import struct
from collections.abc import Callable

_log = logging.getLogger(__name__)

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

from pywilliwaw.protocol import (
    COMMAND_CHAR,
    FANCONTROL_CHAR,
    FANSTATE_CHAR,
    FIRMWARE_REV_CHAR,
    SENSORS_CHAR,
    SENSORLIST_CHAR,
    DEVICENAME_CHAR,
    OSCILLATION_SPEED_LOW,
    OSCILLATION_SPEED_MEDIUM,
    OSCILLATION_SPEED_HIGH,
    SLEEP_MAX_MIN,
    SPEED_MAX,
    SPEED_MIN,
    AUTO_MODE_PARAM_DEFAULT,
    CMD_FAN_TOGGLE,
    CMD_OSCILLATION_TOGGLE,
    CMD_CENTER,
    CMD_CALIBRATE,
    FanControlPacket,
)


class TemperatureSensor:
    """A paired Williwaw temperature sensor (Bluetooth thermometer)."""

    def __init__(self, address: bytes, rssi: int, battery: int, temperature: float):
        self.address = address  # 6-byte MAC address
        self.rssi = rssi
        self.battery = battery  # 0–100 %
        self.temperature = temperature  # °C

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
        temp_raw = struct.unpack_from("<h", data, 8)[
            0
        ]  # signed 16-bit LE, unit = 0.01 °C
        temperature = round(temp_raw / 100.0, 1)
        return cls(address, rssi, battery, temperature)


class Williwaw:
    """BLE-backed controller for a Williwaw fan."""

    def __init__(
        self,
        device: BLEDevice,
        on_update: Callable[[], None] | None = None,
        on_disconnect: Callable[[], None] | None = None,
    ):
        self._device = device
        self._on_disconnect = on_disconnect
        self._client = BleakClient(device, disconnected_callback=self._on_disconnected)
        self._control_packet: FanControlPacket = FanControlPacket()
        self._on_update = on_update

        # FANCONTROL-derived state
        self.fan: int = 0  # 1 = on, 0 = off  (from FANSTATE)
        self.speed: int = 0  # 1–15
        self.oscillation: int = 0  # 1 = oscillating, 0 = fixed
        self.oscillation_speed: int = OSCILLATION_SPEED_MEDIUM  # 1/2/3
        self.sleep_timer_min: int = 0  # scheduled-stop minutes (0 = none)

        # FANSTATE-derived state
        self.sched_timer_type: int = 0  # 0=none, 1=sched_start, 2=sched_stop
        self.sched_remaining_s: int = 0  # seconds remaining on active timer

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
        try:
            fw = await self._client.read_gatt_char(FIRMWARE_REV_CHAR)
            _log.info("Connected to %s — firmware: %s", self.name, fw.decode())
        except Exception:
            _log.info("Connected to %s — firmware version unavailable", self.name)
        raw = await self._client.read_gatt_char(FANCONTROL_CHAR)
        self._apply_fancontrol(raw)
        await self._client.start_notify(FANCONTROL_CHAR, self._on_fancontrol)
        try:
            state = await self._client.read_gatt_char(FANSTATE_CHAR)
            self._apply_fanstate(state)
            await self._client.start_notify(FANSTATE_CHAR, self._on_fanstate)
        except Exception:
            _log.warning(
                "FANSTATE_CHAR not available — power/timer state will not be tracked",
                exc_info=True,
            )
        try:
            await self._client.start_notify(SENSORLIST_CHAR, self._on_sensorlist)
        except Exception:
            _log.warning(
                "SENSORLIST_CHAR not available — sensor readings will not be tracked",
                exc_info=True,
            )

    async def disconnect(self) -> None:
        try:
            await self._client.stop_notify(FANCONTROL_CHAR)
        except Exception:
            _log.warning("Failed to unsubscribe from FANCONTROL_CHAR", exc_info=True)
        try:
            await self._client.stop_notify(FANSTATE_CHAR)
        except Exception:
            _log.warning("Failed to unsubscribe from FANSTATE_CHAR", exc_info=True)
        try:
            await self._client.stop_notify(SENSORLIST_CHAR)
        except Exception:
            _log.warning("Failed to unsubscribe from SENSORLIST_CHAR", exc_info=True)
        await self._client.disconnect()

    # ── fan power ──────────────────────────────────────────────────────────────

    async def toggle(self) -> None:
        """Toggle fan ON↔OFF."""
        await self._client.write_gatt_char(COMMAND_CHAR, CMD_FAN_TOGGLE, response=True)

    # ── speed ──────────────────────────────────────────────────────────────────

    async def set_speed(self, speed: int) -> None:
        if not SPEED_MIN <= speed <= SPEED_MAX:
            raise ValueError(f"speed must be {SPEED_MIN}–{SPEED_MAX}")
        await self._client.write_gatt_char(
            FANCONTROL_CHAR,
            self._control_packet.with_speed(speed).to_bytes(),
            response=True,
        )

    # ── oscillation ────────────────────────────────────────────────────────────

    async def set_oscillation(self, enable: bool) -> None:
        """Toggle oscillation on/off."""
        if bool(self.oscillation) == bool(enable):
            return
        await self._client.write_gatt_char(
            COMMAND_CHAR, CMD_OSCILLATION_TOGGLE, response=True
        )

    async def set_oscillation_speed(self, osc_speed: int) -> None:
        """Set oscillation speed: 1=Low, 2=Medium, 3=High."""
        if osc_speed not in (
            OSCILLATION_SPEED_LOW,
            OSCILLATION_SPEED_MEDIUM,
            OSCILLATION_SPEED_HIGH,
        ):
            raise ValueError(
                "oscillation speed must be 1 (Low), 2 (Medium), or 3 (High)"
            )
        await self._client.write_gatt_char(
            FANCONTROL_CHAR,
            self._control_packet.with_oscillation_speed(osc_speed).to_bytes(),
            response=True,
        )

    async def center_oscillation(self) -> None:
        """Return sweep head to center position."""
        await self._client.write_gatt_char(COMMAND_CHAR, CMD_CENTER, response=True)

    # ── hardware scheduled stop (sleep timer) ─────────────────────────────────

    async def set_sleep_timer(self, minutes: int) -> None:
        """Hardware sleep timer: fan turns itself off after N minutes (0 cancels, max 1440)."""
        if not 0 <= minutes <= SLEEP_MAX_MIN:
            raise ValueError(f"minutes must be 0 (cancel) or 1–{SLEEP_MAX_MIN}")
        await self._client.write_gatt_char(
            FANCONTROL_CHAR,
            self._control_packet.with_scheduled_stop(minutes).to_bytes(),
            response=True,
        )

    # ── auto-mode (requires paired temperature sensors) ────────────────────────

    async def set_thermostat(self, threshold_c: int) -> None:
        """Turn on thermostat mode: fan runs while temperature >= threshold_c (°C, 15–27)."""
        await self._client.write_gatt_char(
            FANCONTROL_CHAR,
            self._control_packet.with_thermostat(threshold_c).to_bytes(),
            response=True,
        )

    async def set_temp_diff_mode(self, delta_c: int) -> None:
        """Turn on temp-differential mode: fan runs while (sensorA − sensorB) >= delta_c."""
        await self._client.write_gatt_char(
            FANCONTROL_CHAR,
            self._control_packet.with_temp_diff(delta_c).to_bytes(),
            response=True,
        )

    async def clear_auto_mode(self) -> None:
        """Disable thermostat / temp-differential auto-mode."""
        await self._client.write_gatt_char(
            FANCONTROL_CHAR,
            self._control_packet.with_auto_mode_cleared().to_bytes(),
            response=True,
        )

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
        await self._client.write_gatt_char(
            FANCONTROL_CHAR,
            self._control_packet.with_scheduled_start(minutes).to_bytes(),
            response=True,
        )

    # ── connection callbacks ───────────────────────────────────────────────────

    def _on_disconnected(self, _client: BleakClient) -> None:
        if self._on_disconnect is not None:
            self._on_disconnect()

    # ── notification handlers ──────────────────────────────────────────────────

    def _on_fancontrol(self, _char, data: bytearray) -> None:
        self._apply_fancontrol(data)

    def _on_fanstate(self, _char, data: bytearray) -> None:
        self._apply_fanstate(data)

    def _on_sensorlist(self, _char, data: bytearray) -> None:
        self._apply_sensorlist(data)

    def _apply_fancontrol(self, data: bytearray) -> None:
        """Parse 19-byte FANCONTROL characteristic."""
        if len(data) < 19:
            _log.warning(
                "FANCONTROL packet too short (%d bytes, expected 19) — ignoring",
                len(data),
            )
            return
        self._control_packet = FanControlPacket.from_bytes(data)
        self.speed = self._control_packet.speed
        self.oscillation = self._control_packet.oscillation
        self.oscillation_speed = self._control_packet.oscillation_speed
        self.sleep_timer_min = self._control_packet.scheduled_stop_min
        if self._on_update is not None:
            self._on_update()

    def _apply_fanstate(self, data: bytearray) -> None:
        """Parse 6-byte FANSTATE characteristic: power + active timer."""
        if len(data) < 6:
            return
        self.fan = data[0]  # 0=off, 1=on
        self.sched_timer_type = data[1]
        self.sched_remaining_s = struct.unpack_from("<I", data, 2)[0]
        if self._on_update is not None:
            self._on_update()

    def _apply_sensorlist(self, data: bytearray) -> None:
        """Parse temperature sensor readings (10 bytes per sensor)."""
        sensors = []
        for i in range(0, len(data), 10):
            if i + 10 > len(data):
                break
            try:
                s = TemperatureSensor._from_10bytes(data[i : i + 10])
                if any(s.address):
                    sensors.append(s)
            except Exception:
                _log.warning(
                    "Failed to parse sensor entry at offset %d", i, exc_info=True
                )
        self.sensors = sensors
        if self._on_update is not None:
            self._on_update()

async def discover(timeout: float = 5.0) -> list[BLEDevice]:
    return await BleakScanner.discover(timeout=timeout)


async def find_by_name(name: str, timeout: float = 10.0) -> BLEDevice | None:
    return await BleakScanner.find_device_by_name(name, timeout=timeout)


async def find_by_address(address: str, timeout: float = 10.0) -> BLEDevice | None:
    return await BleakScanner.find_device_by_address(address, timeout=timeout)

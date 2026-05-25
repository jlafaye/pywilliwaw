"""High-level Williwaw fan controller."""

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

from pywilliwaw.protocol import (
    SLEEP_MAX_MIN,
    SPEED_CHAR,
    SPEED_MAX,
    SPEED_MIN,
    SWEEP_CHAR,
    make_fan_toggle_cmd,
    make_speed_cmd,
    make_sweep_toggle_cmd,
    make_wake_timer_cmd,
)


class Williwaw:
    """BLE-backed controller for a Williwaw fan."""

    def __init__(self, device: BLEDevice):
        self._device = device
        self._client = BleakClient(device)
        self.fan: int = 0
        self.speed: int = 0
        self.sweep: int = 0

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
        self._apply(await self._client.read_gatt_char(SPEED_CHAR))
        await self._client.start_notify(SPEED_CHAR, self._on_notification)

    async def disconnect(self) -> None:
        await self._client.stop_notify(SPEED_CHAR)
        await self._client.disconnect()

    async def toggle(self) -> None:
        await self._client.write_gatt_char(SWEEP_CHAR, make_fan_toggle_cmd(), response=True)

    async def set_speed(self, speed: int) -> None:
        if not SPEED_MIN <= speed <= SPEED_MAX:
            raise ValueError(f"speed must be between {SPEED_MIN} and {SPEED_MAX}")
        await self._client.write_gatt_char(SPEED_CHAR, make_speed_cmd(speed, self.sweep), response=True)

    async def set_sweep(self, enable: bool) -> None:
        if bool(self.sweep) == bool(enable):
            return
        await self._client.write_gatt_char(SWEEP_CHAR, make_sweep_toggle_cmd(), response=True)

    async def set_wake_timer(self, minutes: int) -> None:
        """Delayed start: turns fan OFF and restarts it after N minutes (0 cancels)."""
        if not 0 <= minutes <= SLEEP_MAX_MIN:
            raise ValueError(f"minutes must be 0 (cancel) or 1–{SLEEP_MAX_MIN}")
        await self._client.write_gatt_char(SPEED_CHAR, make_wake_timer_cmd(self.speed, self.sweep, minutes), response=True)

    def _on_notification(self, _char, data: bytearray) -> None:
        self._apply(data)

    def _apply(self, data: bytearray) -> None:
        self.fan = data[0]
        self.speed = data[1]
        self.sweep = data[2]


async def discover(timeout: float = 5.0) -> list[BLEDevice]:
    return await BleakScanner.discover(timeout=timeout)


async def find_by_name(name: str, timeout: float = 10.0) -> BLEDevice | None:
    return await BleakScanner.find_device_by_name(name, timeout=timeout)


async def find_by_address(address: str, timeout: float = 10.0) -> BLEDevice | None:
    return await BleakScanner.find_device_by_address(address, timeout=timeout)

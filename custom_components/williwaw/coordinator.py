"""WilliwawCoordinator: manages the BLE connection and fans out state updates."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from homeassistant.components.bluetooth import async_ble_device_from_address
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from pywilliwaw import Williwaw
from pywilliwaw.fan import TemperatureSensor

_LOGGER = logging.getLogger(__name__)

SIGNAL_NEW_SENSOR = "williwaw_new_sensor"
_RECONNECT_INTERVAL = 30  # seconds between reconnect attempts


class WilliwawCoordinator:
    """Owns the Williwaw BLE connection and notifies HA entities on state change."""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        self.hass = hass
        self.address = address
        self.fan: Williwaw | None = None
        self._listeners: list[Callable[[], None]] = []
        self._known_sensor_addresses: set[bytes] = set()
        self._reconnect_task: asyncio.Task | None = None
        self._shutting_down: bool = False

    # ── listener API (used by FanEntity / NumberEntity) ───────────────────────

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register *listener* to be called on every device update.

        Returns an unsubscribe callable suitable for ``async_on_remove``.
        """
        self._listeners.append(listener)

        def _remove() -> None:
            self._listeners.remove(listener)

        return _remove

    # ── BLE connection lifecycle ───────────────────────────────────────────────

    async def async_connect(self) -> None:
        """Find the BLE device and open a GATT connection."""
        if self._reconnect_task is not None:
            self._reconnect_task.cancel()
            self._reconnect_task = None
        ble_device = async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if ble_device is None:
            raise RuntimeError(
                f"Williwaw at {self.address} not found. "
                "Make sure it is powered on and in range."
            )
        self.fan = Williwaw(
            ble_device,
            on_update=self._on_device_update,
            on_disconnect=self._on_device_disconnected,
        )
        await self.fan.connect()
        _LOGGER.debug("Connected to %s", self.address)

    async def async_disconnect(self) -> None:
        """Close the GATT connection cleanly."""
        self._shutting_down = True
        if self._reconnect_task is not None:
            self._reconnect_task.cancel()
            self._reconnect_task = None
        if self.fan is not None:
            try:
                await self.fan.disconnect()
            except Exception:
                _LOGGER.debug("Error during disconnect from %s", self.address, exc_info=True)
            finally:
                self.fan = None

    # ── disconnect / reconnect ─────────────────────────────────────────────────

    @callback
    def _on_device_disconnected(self) -> None:
        if self._shutting_down:
            return
        _LOGGER.warning(
            "Lost connection to %s — retrying every %ds", self.address, _RECONNECT_INTERVAL
        )
        self.fan = None
        for listener in list(self._listeners):
            listener()
        if self._reconnect_task is None or self._reconnect_task.done():
            self._reconnect_task = self.hass.async_create_task(
                self._async_reconnect_loop()
            )

    async def _async_reconnect_loop(self) -> None:
        while True:
            await asyncio.sleep(_RECONNECT_INTERVAL)
            try:
                await self.async_connect()
            except Exception:
                _LOGGER.debug("Reconnect to %s failed, will retry", self.address, exc_info=True)
                continue
            _LOGGER.info("Reconnected to %s", self.address)
            for listener in list(self._listeners):
                listener()
            return

    # ── internal device-update callback ───────────────────────────────────────

    @callback
    def _on_device_update(self) -> None:
        """Called synchronously by pywilliwaw inside every BLE notification handler.

        Runs in the asyncio event loop — safe to call HA state-machine methods
        directly without ``call_soon_threadsafe``.
        """
        # Discover newly-paired temperature sensors and signal the sensor platform.
        if self.fan is not None:
            for sensor in self.fan.sensors:
                key = bytes(sensor.address)
                if key not in self._known_sensor_addresses:
                    self._known_sensor_addresses.add(key)
                    _LOGGER.debug("New sensor discovered: %s", sensor.name)
                    async_dispatcher_send(self.hass, SIGNAL_NEW_SENSOR, sensor, self)

        # Notify all registered entity listeners so they can push new state to HA.
        for listener in list(self._listeners):
            listener()

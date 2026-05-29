"""Williwaw temperature and battery sensor entities."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from pywilliwaw.fan import TemperatureSensor

from .const import DOMAIN
from .coordinator import SIGNAL_NEW_SENSOR, WilliwawCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Williwaw sensor entities.

    Sensor entities are created dynamically: one temperature + one battery entity
    per paired Williwaw temperature sensor, added as SENSORLIST notifications arrive.
    """
    coordinator: WilliwawCoordinator = hass.data[DOMAIN][entry.entry_id]

    def _add_sensor_entities(sensor: TemperatureSensor) -> None:
        async_add_entities(
            [
                WilliwawTemperatureSensor(coordinator, sensor, entry),
                WilliwawBatterySensor(coordinator, sensor, entry),
            ]
        )

    # Listen for sensors discovered after setup (normal runtime path).
    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            SIGNAL_NEW_SENSOR,
            lambda sensor, coord: (
                _add_sensor_entities(sensor) if coord is coordinator else None
            ),
        )
    )

    # Register sensors already known at setup time (e.g. after HA restart
    # when the fan reconnects before sensor.py's async_setup_entry runs).
    if coordinator.fan is not None:
        for sensor in coordinator.fan.sensors:
            coordinator._known_sensor_addresses.add(bytes(sensor.address))
            _add_sensor_entities(sensor)


# ── shared base class ─────────────────────────────────────────────────────────


class _WilliwawSensorBase(SensorEntity):
    """Shared base for temperature and battery sensor entities."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: WilliwawCoordinator,
        sensor: TemperatureSensor,
        entry: ConfigEntry,
    ) -> None:
        self._coordinator = coordinator
        self._sensor_address = bytes(sensor.address)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            name=entry.title,
            manufacturer="Williwaw",
        )

    @property
    def available(self) -> bool:
        return (
            self._coordinator.fan is not None
            and self._coordinator.fan.is_connected
        )

    def _current_sensor(self) -> TemperatureSensor | None:
        """Look up this sensor by address in the latest SENSORLIST data."""
        if self._coordinator.fan is None:
            return None
        for s in self._coordinator.fan.sensors:
            if bytes(s.address) == self._sensor_address:
                return s
        return None

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self._coordinator.async_add_listener(self._handle_coordinator_update)
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


# ── concrete entities ─────────────────────────────────────────────────────────


class WilliwawTemperatureSensor(_WilliwawSensorBase):
    """Temperature reading from a paired Williwaw sensor."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(
        self,
        coordinator: WilliwawCoordinator,
        sensor: TemperatureSensor,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, sensor, entry)
        self._attr_unique_id = f"{entry.entry_id}_{sensor.name}_temperature"
        self._attr_name = f"{sensor.name} Temperature"

    @property
    def native_value(self) -> float | None:
        s = self._current_sensor()
        return s.temperature if s is not None else None


class WilliwawBatterySensor(_WilliwawSensorBase):
    """Battery level of a paired Williwaw temperature sensor."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_entity_category = None  # show in main device card, not a diagnostic

    def __init__(
        self,
        coordinator: WilliwawCoordinator,
        sensor: TemperatureSensor,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, sensor, entry)
        self._attr_unique_id = f"{entry.entry_id}_{sensor.name}_battery"
        self._attr_name = f"{sensor.name} Battery"

    @property
    def native_value(self) -> int | None:
        s = self._current_sensor()
        return s.battery if s is not None else None

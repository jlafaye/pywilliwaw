"""Williwaw fan entity."""

from __future__ import annotations

import logging

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.percentage import (
    percentage_to_ranged_value,
    ranged_value_to_percentage,
)

from .const import DOMAIN, SPEED_RANGE
from .coordinator import WilliwawCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Williwaw fan entity."""
    coordinator: WilliwawCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([WilliwawFanEntity(coordinator, entry)])


class WilliwawFanEntity(FanEntity):
    """Represents the Williwaw fan as a Home Assistant fan entity.

    Supports:
    - Turn on / turn off (via BLE toggle command)
    - Speed as a percentage (maps device range 1–15 to 1–100 %)
    - Oscillation on/off
    """

    _attr_has_entity_name = True
    _attr_name = None  # entity name == device name
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED
        | FanEntityFeature.OSCILLATE
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )

    def __init__(
        self, coordinator: WilliwawCoordinator, entry: ConfigEntry
    ) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            name=entry.title,
            manufacturer="Williwaw",
        )

    # ── availability ──────────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        return (
            self._coordinator.fan is not None
            and self._coordinator.fan.is_connected
        )

    # ── state properties ──────────────────────────────────────────────────────

    @property
    def is_on(self) -> bool | None:
        if not self.available:
            return None
        return bool(self._coordinator.fan.fan)

    @property
    def percentage(self) -> int | None:
        """Current speed as a percentage (0–100), or None when unavailable."""
        if not self.available or self._coordinator.fan.speed == 0:
            return None
        return ranged_value_to_percentage(SPEED_RANGE, self._coordinator.fan.speed)

    @property
    def speed_count(self) -> int:
        """Number of discrete speed steps the device supports."""
        return SPEED_RANGE[1] - SPEED_RANGE[0] + 1  # 15

    @property
    def oscillating(self) -> bool | None:
        if not self.available:
            return None
        return bool(self._coordinator.fan.oscillation)

    # ── commands ──────────────────────────────────────────────────────────────

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs,
    ) -> None:
        if not self._coordinator.fan.fan:
            await self._coordinator.fan.toggle()
        if percentage is not None:
            await self._async_set_speed(percentage)

    async def async_turn_off(self, **kwargs) -> None:
        if self._coordinator.fan.fan:
            await self._coordinator.fan.toggle()

    async def async_set_percentage(self, percentage: int) -> None:
        await self._async_set_speed(percentage)

    async def async_oscillate(self, oscillating: bool) -> None:
        await self._coordinator.fan.set_oscillation(oscillating)

    async def _async_set_speed(self, percentage: int) -> None:
        speed = round(percentage_to_ranged_value(SPEED_RANGE, percentage))
        speed = max(SPEED_RANGE[0], min(SPEED_RANGE[1], speed))
        await self._coordinator.fan.set_speed(speed)

    # ── HA lifecycle ──────────────────────────────────────────────────────────

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self._coordinator.async_add_listener(self._handle_coordinator_update)
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

"""Williwaw sleep timer entity."""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SLEEP_TIMER_MAX, SLEEP_TIMER_MIN
from .coordinator import WilliwawCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Williwaw sleep timer number entity."""
    coordinator: WilliwawCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([WilliwawSleepTimerNumber(coordinator, entry)])


class WilliwawSleepTimerNumber(NumberEntity):
    """Hardware sleep timer: fan turns itself off after N minutes.

    Set to 0 to cancel an active timer.
    Range: 0 (cancel) to 1440 minutes (24 h).
    """

    _attr_has_entity_name = True
    _attr_name = "Sleep Timer"
    _attr_native_min_value = SLEEP_TIMER_MIN
    _attr_native_max_value = SLEEP_TIMER_MAX
    _attr_native_step = 1.0
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_mode = NumberMode.BOX

    def __init__(
        self, coordinator: WilliwawCoordinator, entry: ConfigEntry
    ) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_sleep_timer"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            name=entry.title,
            manufacturer="Williwaw",
        )

    # ── state ─────────────────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        return (
            self._coordinator.fan is not None
            and self._coordinator.fan.is_connected
        )

    @property
    def native_value(self) -> float:
        """Reflect the scheduled-stop minutes from the last FANCONTROL packet."""
        if not self.available:
            return 0.0
        return float(self._coordinator.fan.sleep_timer_min)

    # ── command ───────────────────────────────────────────────────────────────

    async def async_set_native_value(self, value: float) -> None:
        """Set the sleep timer. Value 0 cancels any active timer."""
        await self._coordinator.fan.set_sleep_timer(int(value))

    # ── HA lifecycle ──────────────────────────────────────────────────────────

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self._coordinator.async_add_listener(self._handle_coordinator_update)
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

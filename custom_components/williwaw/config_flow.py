"""Config flow for the Williwaw integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.selector import TextSelector

from .const import CONF_ADDRESS, DOMAIN


class WilliwawConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Williwaw."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery_info: BluetoothServiceInfoBleak | None = None

    # ── Bluetooth auto-discovery path ─────────────────────────────────────────

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Called by HA when a matching BLE advertisement is seen."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {"name": discovery_info.name}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Ask the user to confirm the discovered device."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._discovery_info.name,
                data={CONF_ADDRESS: self._discovery_info.address},
            )
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": self._discovery_info.name},
        )

    # ── Manual setup path ─────────────────────────────────────────────────────

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Handle manual setup via the UI (Settings → Integrations → Add)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS].strip().upper()
            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()
            name = f"Williwaw {address[-5:]}"
            return self.async_create_entry(
                title=name,
                data={CONF_ADDRESS: address},
            )

        # Pre-fill address if a Williwaw device is already visible via BLE.
        discovered = [
            info
            for info in async_discovered_service_info(self.hass, connectable=True)
            if info.name and info.name.startswith("Williwaw")
        ]
        suggestion = discovered[0].address if discovered else ""

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS, default=suggestion): TextSelector(),
                }
            ),
            errors=errors,
        )

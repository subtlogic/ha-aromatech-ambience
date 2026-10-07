"""Config flow for the AromaTech Ambience.

Discovery matches on the local name, because the Ambience carries no
manufacturer data in its advertisement - only in the scan response, which
ESPHome Bluetooth proxies do not forward. Matching on manufacturer id would
therefore never fire through a proxy, which is how this device reaches Home
Assistant here.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import bluetooth
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_ADDRESS

from homeassistant.core import callback

from .const import (
    CONF_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    SCAN_INTERVAL_SECONDS,
)

NAME_PREFIX = "Ambience"


def _is_ambience(name: str | None) -> bool:
    return bool(name) and name.startswith(NAME_PREFIX)


class AmbienceConfigFlow(ConfigFlow, domain=DOMAIN):
    """Adopt an Ambience, by discovery or by picking it from a list."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> AmbienceOptionsFlow:
        return AmbienceOptionsFlow()

    def __init__(self) -> None:
        self._discovered: bluetooth.BluetoothServiceInfoBleak | None = None

    async def async_step_bluetooth(
        self, discovery_info: bluetooth.BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        if not _is_ambience(discovery_info.name):
            return self.async_abort(reason="not_supported")
        self._discovered = discovery_info
        self.context["title_placeholders"] = {"name": discovery_info.name}
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._discovered is not None
        if user_input is not None:
            return self.async_create_entry(
                title=self._discovered.name or "Ambience",
                data={CONF_ADDRESS: self._discovered.address},
            )
        self._set_confirm_only()
        return self.async_show_form(
            step_id="confirm",
            description_placeholders={
                "name": self._discovered.name or "",
                "address": self._discovered.address,
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="Ambience", data={CONF_ADDRESS: address})

        current = self._async_current_ids()
        devices = {
            info.address: f"{info.name} ({info.address})"
            for info in bluetooth.async_discovered_service_info(self.hass)
            if info.address not in current and _is_ambience(info.name)
        }
        if not devices:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): vol.In(devices)}),
        )


class AmbienceOptionsFlow(OptionsFlow):
    """Tune the heartbeat.

    Each poll connects, writes a time sync and disconnects, and the device
    replies with its whole state - so this interval decides how quickly a
    change made in the vendor app, or at the unit itself, shows up here. It
    also decides how often one of the proxy's three connection slots is in
    use, which matters when that proxy also serves other devices.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, SCAN_INTERVAL_SECONDS
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                ),
            }),
        )

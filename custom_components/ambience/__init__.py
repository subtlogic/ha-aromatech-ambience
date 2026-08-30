"""AromaTech Ambience — local BLE control.

The vendor's own integration (`ttrushin/ha-aromatech-scent-diffuser`) does not
work with this model: it writes to characteristic `fff6`, which the Ambience
does not implement. This is a separate integration for the `EE01` protocol
family rather than a fork, so a HACS update to that one cannot revert it.
"""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant

from .const import CONF_SCAN_INTERVAL, DOMAIN, SCAN_INTERVAL_SECONDS
from .coordinator import AmbienceCoordinator

PLATFORMS: list[Platform] = [
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TIME,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = AmbienceCoordinator(
        hass,
        entry.data[CONF_ADDRESS],
        entry.options.get(CONF_SCAN_INTERVAL, SCAN_INTERVAL_SECONDS),
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Options changed - rebuild so a new heartbeat interval takes effect."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded

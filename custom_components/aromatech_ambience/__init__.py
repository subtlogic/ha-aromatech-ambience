"""AromaTech Ambience — local BLE control.

The existing community integration for AromaTech diffusers
(`ttrushin/ha-aromatech-scent-diffuser`) does not work with this model: it
writes to characteristic `fff6`, which the Ambience does not implement. This is
a separate integration for the `EE01` protocol family rather than a fork,
because the two protocols share no service, characteristic or framing.
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
    # Deliberately NOT async_config_entry_first_refresh. That raises
    # ConfigEntryNotReady when the first connect fails, which takes the whole
    # integration down - and this device is documented as advertising
    # intermittently, so a miss at boot is expected rather than exceptional.
    # On a cold start the ESPHome proxies are coming up at the same moment, so
    # the first attempt is the one most likely to miss.
    #
    # async_refresh does not raise. Setup succeeds, the entities exist, and
    # CoordinatorEntity reports them unavailable until the first successful
    # poll fills them in - honest about the state instead of pretending the
    # integration is not installed. Recovery costs one scan interval.
    await coordinator.async_refresh()

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

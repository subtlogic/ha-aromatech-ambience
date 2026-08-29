"""Light mode selector for the AromaTech Ambience."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import protocol as p
from .const import DOMAIN
from .coordinator import AmbienceCoordinator
from .entity import AmbienceEntity

# Displayed labels, in protocol order. Chosen over a translation key so the
# options cannot fall back to raw identifiers if a translation lookup fails -
# which is exactly what happened to the entity names on the first install.
OPTIONS = ["Off", "Warm", "Cool", "Flow", "Custom"]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: AmbienceCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([AmbienceLight(coordinator)])


class AmbienceLight(AmbienceEntity, SelectEntity):
    """The five-position light control, matching the vendor app exactly.

    Not a `light` entity: the device exposes discrete modes rather than
    brightness and colour as Home Assistant models them, and `flow` is an
    animation with no equivalent. A select says what this actually is.
    """

    _attr_name = "Light"
    _attr_options = list(OPTIONS)

    def __init__(self, coordinator: AmbienceCoordinator) -> None:
        super().__init__(coordinator, "light")

    @property
    def current_option(self) -> str | None:
        state = self.coordinator.data
        if state is None or state.light_mode is None:
            return None
        if not 0 <= state.light_mode < len(OPTIONS):
            return None
        return OPTIONS[state.light_mode]

    @property
    def icon(self) -> str:
        """A different glyph per mode, so the tile reads at a glance."""
        return {
            "Off": "mdi:lightbulb-off",
            "Warm": "mdi:lightbulb-on",
            "Cool": "mdi:lightbulb-on-outline",
            "Flow": "mdi:lightbulb-multiple",
            "Custom": "mdi:palette",
        }.get(self.current_option or "", "mdi:lightbulb-question")

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_light(OPTIONS.index(option))

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


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: AmbienceCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([AmbienceLight(coordinator)])


class AmbienceLight(AmbienceEntity, SelectEntity):
    """The five-position light control, matching the vendor app exactly.

    Not a `light` entity: the device exposes discrete modes rather than
    brightness and colour as Home Assistant models them. `flow` in particular
    is an animation with no equivalent. A select says what this actually is.
    """

    _attr_translation_key = "light"
    _attr_icon = "mdi:lightbulb"
    _attr_options = list(p.LIGHT_MODES)

    def __init__(self, coordinator: AmbienceCoordinator) -> None:
        super().__init__(coordinator, "light")

    @property
    def current_option(self) -> str | None:
        return self.coordinator.data.light_mode_name if self.coordinator.data else None

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_light(p.LIGHT_MODES.index(option))

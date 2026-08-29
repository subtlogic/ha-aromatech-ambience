"""Power and sound switches for the AromaTech Ambience."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AmbienceCoordinator
from .entity import AmbienceEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: AmbienceCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([AmbiencePower(coordinator), AmbienceSound(coordinator)])


class AmbiencePower(AmbienceEntity, SwitchEntity):
    """The diffuser itself."""

    _attr_name = "Diffuser"
    _attr_icon = "mdi:air-filter"

    def __init__(self, coordinator: AmbienceCoordinator) -> None:
        super().__init__(coordinator, "power")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.power if self.coordinator.data else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_power(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_power(False)


class AmbienceSound(AmbienceEntity, SwitchEntity):
    """The unit's audible feedback, not the diffuser."""

    _attr_name = "Sound"
    _attr_icon = "mdi:volume-high"

    def __init__(self, coordinator: AmbienceCoordinator) -> None:
        super().__init__(coordinator, "sound")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.sound if self.coordinator.data else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_sound(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_sound(False)

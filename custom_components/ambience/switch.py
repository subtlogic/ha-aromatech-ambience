"""Power and sound switches for the AromaTech Ambience."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AmbienceCoordinator
from .entity import AmbienceEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: AmbienceCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        AmbiencePower(coordinator),
        AmbienceSound(coordinator),
        AmbienceScheduleEnabled(coordinator),
    ])


class AmbiencePower(AmbienceEntity, SwitchEntity):
    """The diffuser itself."""

    _attr_name = "Diffuser"

    def __init__(self, coordinator: AmbienceCoordinator) -> None:
        super().__init__(coordinator, "power")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.power if self.coordinator.data else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_power(True)

    @property
    def icon(self) -> str:
        # mdi:scent is the diffuser glyph - vapour rising from a bottle. The
        # previous mdi:air-filter is an HVAC filter, which is a different
        # appliance entirely.
        if self.is_on is None:
            return "mdi:scent-off"
        return "mdi:scent" if self.is_on else "mdi:scent-off"

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_power(False)


class AmbienceSound(AmbienceEntity, SwitchEntity):
    """The unit's audible feedback, not the diffuser."""

    _attr_name = "Sound"

    def __init__(self, coordinator: AmbienceCoordinator) -> None:
        super().__init__(coordinator, "sound")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.sound if self.coordinator.data else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_sound(True)

    @property
    def icon(self) -> str:
        # Showing volume-high while muted was actively misleading.
        if self.is_on is None:
            return "mdi:volume-variant-off"
        return "mdi:volume-high" if self.is_on else "mdi:volume-off"

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_sound(False)


class AmbienceScheduleEnabled(AmbienceEntity, SwitchEntity):
    """Whether the stored schedule is active.

    This is bit 7 of the schedule's day mask. That reading is inference from
    three observed masks rather than proof, so this switch flips only that bit
    and leaves every other byte of the frame untouched.
    """

    _attr_name = "Schedule enabled"

    def __init__(self, coordinator: AmbienceCoordinator) -> None:
        super().__init__(coordinator, "schedule_enabled")

    @property
    def is_on(self) -> bool | None:
        state = self.coordinator.data
        return None if state is None else state.schedule_enabled

    @property
    def icon(self) -> str:
        if self.is_on is None:
            return "mdi:calendar-question"
        return "mdi:calendar-check" if self.is_on else "mdi:calendar-remove"

    async def _set(self, enabled: bool) -> None:
        state = self.coordinator.data
        if state is None or state.days_mask is None:
            raise HomeAssistantError("no schedule read from the device yet")
        mask = (state.days_mask | 0x80) if enabled else (state.days_mask & 0x7F)
        await self.coordinator.async_set_schedule(days_mask=mask)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)

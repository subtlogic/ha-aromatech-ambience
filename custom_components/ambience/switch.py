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

# Bit position in the schedule day mask -> (ordering index, short label).
#
# Bit 0 = Sunday is INFERRED, not proven. It is the only assignment consistent
# with the three masks ever observed - 0x7f and 0xff for all days, 0x82 while
# the vendor app showed Monday alone - but a single Monday-only sample cannot
# rule out an off-by-one. Toggling one day and reading the schedule sensor back
# settles it in one action.
#
# Names carry an index because Home Assistant sorts entities alphabetically,
# which would otherwise list these as Fri, Mon, Sat, Sun, Thu, Tue, Wed.
DAY_BITS = {
    1: (1, "Mon"),
    2: (2, "Tue"),
    3: (3, "Wed"),
    4: (4, "Thu"),
    5: (5, "Fri"),
    6: (6, "Sat"),
    0: (7, "Sun"),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: AmbienceCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SwitchEntity] = [
        AmbiencePower(coordinator),
        AmbienceSound(coordinator),
        AmbienceScheduleEnabled(coordinator),
    ]
    entities += [AmbienceDay(coordinator, bit) for bit in DAY_BITS]
    async_add_entities(entities)


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


class AmbienceDay(AmbienceEntity, SwitchEntity):
    """One weekday of the schedule - a single bit of the day mask.

    Flips only its own bit and hands the whole mask back, so the other days and
    the enable flag in bit 7 are preserved regardless of what they were.
    """

    def __init__(self, coordinator: AmbienceCoordinator, bit: int) -> None:
        order, label = DAY_BITS[bit]
        super().__init__(coordinator, f"day_{label.lower()}")
        self._bit = bit
        self._attr_name = f"Schedule {order} {label}"
        self._attr_entity_registry_enabled_default = True

    @property
    def is_on(self) -> bool | None:
        state = self.coordinator.data
        if state is None or state.days_mask is None:
            return None
        return bool(state.days_mask & (1 << self._bit))

    @property
    def icon(self) -> str:
        if self.is_on is None:
            return "mdi:calendar-question"
        return "mdi:calendar-check" if self.is_on else "mdi:calendar-blank"

    async def _set(self, on: bool) -> None:
        state = self.coordinator.data
        if state is None or state.days_mask is None:
            raise HomeAssistantError("no schedule read from the device yet")
        mask = state.days_mask
        mask = (mask | (1 << self._bit)) if on else (mask & ~(1 << self._bit))
        await self.coordinator.async_set_schedule(days_mask=mask & 0xFF)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)

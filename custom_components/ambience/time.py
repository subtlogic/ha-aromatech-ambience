"""Schedule start and end times for the AromaTech Ambience.

The device stores whole hours only - the frame carries `06 00` and `14 00`,
little-endian 16-bit hour values, with no minutes field anywhere. Minutes set
here are therefore discarded, and the entity reports :00 back so the UI does
not imply a precision the hardware does not have.
"""
from __future__ import annotations

from datetime import time as dt_time

from homeassistant.components.time import TimeEntity
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
    async_add_entities([
        AmbienceScheduleTime(coordinator, "start"),
        AmbienceScheduleTime(coordinator, "end"),
    ])


class AmbienceScheduleTime(AmbienceEntity, TimeEntity):
    """One end of the schedule window."""

    def __init__(self, coordinator: AmbienceCoordinator, which: str) -> None:
        super().__init__(coordinator, f"schedule_{which}")
        self._which = which
        self._attr_name = "Schedule start" if which == "start" else "Schedule end"
        self._attr_icon = (
            "mdi:clock-start" if which == "start" else "mdi:clock-end"
        )

    @property
    def native_value(self) -> dt_time | None:
        state = self.coordinator.data
        if state is None:
            return None
        hour = state.start_hour if self._which == "start" else state.end_hour
        if hour is None or not 0 <= hour <= 23:
            return None
        return dt_time(hour=hour)

    async def async_set_value(self, value: dt_time) -> None:
        # Minutes are dropped: the device has no field for them.
        if self._which == "start":
            await self.coordinator.async_set_schedule(start_hour=value.hour)
        else:
            await self.coordinator.async_set_schedule(end_hour=value.hour)

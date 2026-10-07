"""Schedule sensor for the AromaTech Ambience.

Read-only summary of the schedule frame. The writable pieces - days, window
and intensity - are separate switch, time and number entities.

The frame trace used while debugging silent writes lives in the diagnostics
download rather than here: as a state attribute it would be written to the
recorder on every poll.
"""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import protocol as _p
from .const import DOMAIN
from .coordinator import AmbienceCoordinator
from .entity import AmbienceEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: AmbienceCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([AmbienceSchedule(coordinator)])


class AmbienceSchedule(AmbienceEntity, SensorEntity):
    """The active schedule, as the device reports it."""

    _attr_name = "Schedule"

    def __init__(self, coordinator: AmbienceCoordinator) -> None:
        super().__init__(coordinator, "schedule")

    @property
    def icon(self) -> str:
        state = self.coordinator.data
        if state is None or state.schedule_enabled is None:
            return "mdi:calendar-question"
        return "mdi:calendar-clock" if state.schedule_enabled else "mdi:calendar-remove"

    @property
    def native_value(self) -> str | None:
        s = self.coordinator.data
        if s is None or s.start_hour is None:
            return None
        if not s.schedule_enabled:
            return "disabled"
        days = ",".join(s.days) if s.days else "no days"
        return f"{days} {s.start_hour:02d}:00-{s.end_hour:02d}:00"

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        s = self.coordinator.data
        if s is None:
            return {}
        raw = s.raw.get(_p.CMD_POWER)
        return {
            "enabled": s.schedule_enabled,
            "days": s.days,
            "days_mask": s.days_mask,
            "start_hour": s.start_hour,
            "end_hour": s.end_hour,
            "intensity": s.intensity,
            "light_rgb": s.rgb,
            "light_brightness": s.brightness,
            "firmware": s.firmware,
            "raw_schedule": raw.hex(" ") if raw else None,
        }

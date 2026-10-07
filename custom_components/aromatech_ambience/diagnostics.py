"""Diagnostics download for the AromaTech Ambience.

A write the device silently ignores looks exactly like a write that was never
sent, unless you can see the bytes. The frame trace is the evidence for that
kind of report, so it is offered here, where a user can attach it to an issue.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import AmbienceCoordinator

TO_REDACT = {CONF_ADDRESS}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coordinator: AmbienceCoordinator = hass.data[DOMAIN][entry.entry_id]
    state = coordinator.data
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "last_update_success": coordinator.last_update_success,
        "state": None if state is None else {
            "power": state.power,
            "light_mode": state.light_mode_name,
            "rgb": state.rgb,
            "brightness": state.brightness,
            "sound": state.sound,
            "days_mask": state.days_mask,
            "start_hour": state.start_hour,
            "end_hour": state.end_hour,
            "intensity": state.intensity,
            "firmware": state.firmware,
            "raw": {f"{cmd:#06x}": payload.hex(" ") for cmd, payload in state.raw.items()},
        },
        "trace": list(coordinator.trace),
    }

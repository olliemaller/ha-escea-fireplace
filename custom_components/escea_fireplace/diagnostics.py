"""Diagnostics download for the Escea Fireplace integration."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import CONF_MAC, CONF_PIN, CONF_SERIAL
from .coordinator import EsceaConfigEntry

TO_REDACT = {
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_PIN,
    CONF_SERIAL,
    CONF_MAC,
    "serial",
    "serial_number",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: EsceaConfigEntry
) -> dict[str, Any]:
    """Return the entry's settings and the latest readings, with secrets removed."""
    coordinator = entry.runtime_data
    data = coordinator.data
    return {
        "title": "**REDACTED**",
        "generation": coordinator.generation,
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "web": {
            "enabled": coordinator.web_enabled,
            "has_login": coordinator.has_web_login,
        },
        "state": {
            "status": async_redact_data(asdict(data.status), TO_REDACT),
            "mode": data.mode.value,
            "busy_remaining": data.busy_remaining,
            "pending": {k: str(v) for k, v in data.pending.items()},
            "web_fresh": data.web_fresh,
            "home_page": asdict(data.home_page) if data.home_page else None,
            "diagnostics": asdict(data.diagnostics) if data.diagnostics else None,
        },
    }

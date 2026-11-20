"""The Escea Fireplace integration."""

from __future__ import annotations

from aioescea import EsceaPortInUseError

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN, PLATFORMS
from .coordinator import EsceaConfigEntry, EsceaCoordinator
from .transport import async_close_transport_if_unused

#: Other integrations that also bind UDP 3300 and so can't run alongside.
CONFLICTING_DOMAINS = ("escea",)


async def async_setup_entry(hass: HomeAssistant, entry: EsceaConfigEntry) -> bool:
    """Set up an Escea fireplace from a config entry."""
    _check_conflicts(hass)
    try:
        coordinator = await EsceaCoordinator.async_create(hass, entry)
    except EsceaPortInUseError as err:
        ir.async_create_issue(
            hass,
            DOMAIN,
            "port_in_use",
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key="port_in_use",
        )
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN, translation_key="port_in_use"
        ) from err
    ir.async_delete_issue(hass, DOMAIN, "port_in_use")

    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(coordinator.async_shutdown_timers)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EsceaConfigEntry) -> bool:
    """Unload a config entry, closing the UDP socket if nothing else uses it."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        others = [
            e
            for e in hass.config_entries.async_entries(DOMAIN)
            if e.entry_id != entry.entry_id and e.state is ConfigEntryState.LOADED
        ]
        await async_close_transport_if_unused(hass, bool(others))
    return unloaded


def _check_conflicts(hass: HomeAssistant) -> None:
    """Warn if another Escea integration is also using UDP 3300."""
    for domain in CONFLICTING_DOMAINS:
        issue_id = f"conflict_{domain}"
        if (
            hass.config_entries.async_entries(domain)
            or domain in hass.config.components
        ):
            ir.async_create_issue(
                hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="conflict",
                translation_placeholders={"domain": domain},
            )
        else:
            ir.async_delete_issue(hass, DOMAIN, issue_id)

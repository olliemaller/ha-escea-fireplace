"""Keeps one fireplace's state up to date."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import datetime, time, timedelta
from typing import Any

from aioescea import (
    MAX_TEMPERATURE,
    MIN_TEMPERATURE,
    NCAPI_MAX_TEMPERATURE,
    NCAPI_MIN_TEMPERATURE,
    Diagnostics,
    EsceaAuthError,
    EsceaBusyError,
    EsceaConnectionError,
    EsceaError,
    EsceaFireplace,
    EsceaNcapiClient,
    EsceaStateError,
    EsceaWebClient,
    FireMode,
    HomePage,
    NcapiStatus,
    Status,
    Timer,
    async_find,
    mode_from_status,
    round_half_up,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CLOCK_DRIFT_MINUTES,
    CONF_GENERATION,
    CONF_SERIAL,
    CONF_WEB_ENABLED,
    CONF_WEB_INTERVAL,
    DEFAULT_WEB_INTERVAL_MINUTES,
    DOMAIN,
    GEN2,
    GEN3,
    LOGGER,
    REDISCOVER_AFTER_FAILURES,
    UPDATE_INTERVAL,
    WEB_MAX_BACKOFF,
    WEB_STALE_AFTER,
)
from .transport import async_broadcast_addresses, async_get_transport

type EsceaConfigEntry = ConfigEntry[EsceaCoordinator | EsceaG3Coordinator]


@dataclass(frozen=True, slots=True)
class EsceaData:
    """Everything known about the fire after an update."""

    status: Status | NcapiStatus
    busy_remaining: float
    home_page: HomePage | None = None
    diagnostics: Diagnostics | None = None
    web_fresh: bool = False
    pending: dict[str, Any] = field(default_factory=dict)

    @property
    def mode(self) -> FireMode:
        """Return normal, boost or flame effect."""
        return mode_from_status(self.status)  # type: ignore[arg-type]


class EsceaCoordinator(DataUpdateCoordinator[EsceaData]):
    """Reads the fire over UDP every 30 s and its web page every few minutes.

    UDP is the source of truth for live state. The web page (timers, clock,
    diagnostics) is best effort: if it fails, UDP control carries on and the
    web entities go unavailable.

    Commands sent while the fire is lighting (the first 66 s after it's
    turned on) are held and sent once it's ready, but only temperature and
    mode, only while the fire is still on, and never POWER_ON. Any power
    change, from here or the remote, drops them.
    """

    config_entry: EsceaConfigEntry
    generation = GEN2
    min_temp = MIN_TEMPERATURE
    max_temp = MAX_TEMPERATURE
    temp_step = 1.0
    supports_modes = True

    def __init__(
        self,
        hass: HomeAssistant,
        entry: EsceaConfigEntry,
        fireplace: EsceaFireplace,
        web: EsceaWebClient,
    ) -> None:
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.data[CONF_SERIAL]}",
            update_interval=UPDATE_INTERVAL,
            always_update=False,
        )
        self.fireplace = fireplace
        self.web = web
        self.serial: int = entry.data[CONF_SERIAL]
        self._failures = 0
        self._home_page: HomePage | None = None
        self._diagnostics: Diagnostics | None = None
        self._web_last_ok: datetime | None = None
        self._web_next: datetime = dt_util.utcnow()
        self._web_failures = 0
        self._web_auth_failed = False
        self._pending: dict[str, Any] = {}
        self._pending_power: bool | None = None
        self._ready_unsub: CALLBACK_TYPE | None = None
        self._web_running = False

    @classmethod
    async def async_create(
        cls, hass: HomeAssistant, entry: EsceaConfigEntry
    ) -> EsceaCoordinator:
        """Build the coordinator with the shared transport."""
        transport = await async_get_transport(hass)
        fireplace = EsceaFireplace(
            entry.data[CONF_HOST], transport, serial=entry.data[CONF_SERIAL]
        )
        web = EsceaWebClient(
            async_get_clientsession(hass),
            entry.data[CONF_HOST],
            username=entry.data.get(CONF_USERNAME),
            password=entry.data.get(CONF_PASSWORD),
        )
        return cls(hass, entry, fireplace, web)

    @property
    def web_enabled(self) -> bool:
        """Return True if the web page should be read."""
        return bool(self.config_entry.options.get(CONF_WEB_ENABLED, True))

    @property
    def web_interval(self) -> timedelta:
        """Return how often the web page is read."""
        return timedelta(
            minutes=self.config_entry.options.get(
                CONF_WEB_INTERVAL, DEFAULT_WEB_INTERVAL_MINUTES
            )
        )

    @property
    def has_web_login(self) -> bool:
        """Return True if the web page login is set."""
        return self.web.has_credentials

    @property
    def can_write_web(self) -> bool:
        """Return True if timers can be changed."""
        return self.web_enabled and self.web.has_credentials

    async def _async_update_data(self) -> EsceaData:
        try:
            status = await self.fireplace.async_get_status()
        except EsceaConnectionError as err:
            self._failures += 1
            if self._failures >= REDISCOVER_AFTER_FAILURES:
                await self._async_rediscover()
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="unreachable",
                translation_placeholders={"host": self.fireplace.host},
            ) from err
        self._failures = 0

        prev = self.data.status if self.data else None
        if prev is not None and prev.is_on != status.is_on:
            if self._pending_power is None or self._pending_power != status.is_on:
                # Someone else (remote, app, timer) changed the power: drop
                # anything held for the old state.
                self._pending.clear()
            self._pending_power = None
        if not status.is_on:
            self._pending.clear()

        if self._pending and self.fireplace.busy_remaining == 0:
            await self._async_send_pending()
            status = self.fireplace.last_status or status

        if self.web_enabled and dt_util.utcnow() >= self._web_next:
            if self.data is None:
                # First refresh: read it now so the web entities start filled.
                await self._async_update_web()
            elif not self._web_running:
                # Afterwards, read it in the background. The page can take
                # 10 s or more to answer, and a command's refresh shouldn't
                # wait for it.
                self._web_running = True
                self.config_entry.async_create_background_task(
                    self.hass,
                    self._async_update_web_and_publish(),
                    f"{DOMAIN} {self.serial} web page",
                )

        web_fresh = self._web_is_fresh()
        return EsceaData(
            status=status,
            busy_remaining=self.fireplace.busy_remaining,
            home_page=self._home_page,
            diagnostics=self._diagnostics,
            web_fresh=web_fresh,
            pending=dict(self._pending),
        )

    async def _async_rediscover(self) -> None:
        """Look for the fire by serial number in case its address changed."""
        try:
            found = await async_find(
                self.fireplace.transport,
                self.serial,
                await async_broadcast_addresses(self.hass),
            )
        except EsceaError as err:
            LOGGER.debug("Rediscovery failed: %s", err)
            return
        if found is None or found.host == self.fireplace.host:
            return
        LOGGER.info(
            "Escea %s moved from %s to %s", self.serial, self.fireplace.host, found.host
        )
        self.async_set_host(found.host)

    @callback
    def async_set_host(self, host: str) -> None:
        """Point at a new IP address and save it."""
        self.fireplace.host = host
        self.web.host = host
        self.hass.config_entries.async_update_entry(
            self.config_entry, data={**self.config_entry.data, CONF_HOST: host}
        )

    def _web_is_fresh(self) -> bool:
        return (
            self._web_last_ok is not None
            and dt_util.utcnow() - self._web_last_ok < WEB_STALE_AFTER
        )

    async def _async_update_web_and_publish(self) -> None:
        """Read the web page, then update the entities with what was read."""
        try:
            await self._async_update_web()
        finally:
            self._web_running = False
        if self.data is not None:
            self.async_set_updated_data(
                replace(
                    self.data,
                    home_page=self._home_page,
                    diagnostics=self._diagnostics,
                    web_fresh=self._web_is_fresh(),
                )
            )

    async def _async_update_web(self) -> None:
        """Read the web page, backing off hard if it struggles."""
        ok = True
        try:
            self._home_page = await self.web.async_get_home_page()
            self._check_clock(self._home_page.clock)
            if self.web.has_credentials and not self._web_auth_failed:
                try:
                    self._diagnostics = await self.web.async_get_diagnostics()
                except EsceaAuthError:
                    self._web_auth_failed = True
                    self._diagnostics = None
                    self.config_entry.async_start_reauth(self.hass)
        except EsceaError as err:
            LOGGER.debug("Web page read failed: %s", err)
            ok = False
        now = dt_util.utcnow()
        if ok:
            self._web_failures = 0
            self._web_last_ok = now
            self._web_next = now + self.web_interval
        else:
            self._web_failures += 1
            backoff = min(self.web_interval * 2**self._web_failures, WEB_MAX_BACKOFF)
            self._web_next = now + backoff

    @callback
    def _check_clock(self, clock: time | None) -> None:
        """Raise a Repairs issue if the fire's clock is out by minutes."""
        issue_id = f"clock_drift_{self.serial}"
        drift = clock_drift_minutes(clock, dt_util.now())
        if drift is not None and abs(drift) >= CLOCK_DRIFT_MINUTES:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="clock_drift",
                translation_placeholders={
                    "name": self.config_entry.title,
                    "minutes": str(abs(drift)),
                    "direction": "ahead" if drift > 0 else "behind",
                },
            )
        else:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    # Commands ---------------------------------------------------------------

    async def _async_command(self, action: Callable[[], Awaitable[None]]) -> None:
        try:
            await action()
        except EsceaStateError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_state",
                translation_placeholders={"error": str(err)},
            ) from err
        except EsceaConnectionError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="unreachable",
                translation_placeholders={"host": self.fireplace.host},
            ) from err

    def _schedule_ready_refresh(self) -> None:
        """Refresh just after the 66 s lighting window, to send held commands."""
        if self._ready_unsub:
            self._ready_unsub()

        @callback
        def _ready(_: datetime) -> None:
            self._ready_unsub = None
            self.hass.async_create_task(self.async_refresh())

        self._ready_unsub = async_call_later(
            self.hass, self.fireplace.busy_remaining + 2, _ready
        )

    async def async_turn_on(self) -> None:
        """Light the fire."""
        try:
            await self._async_command(self.fireplace.async_turn_on)
        except EsceaBusyError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="busy",
                translation_placeholders={"seconds": f"{err.remaining:.0f}"},
            ) from err
        self._pending_power = True
        if self.fireplace.busy_remaining:
            self._schedule_ready_refresh()
        await self.async_refresh()

    async def async_turn_off(self) -> None:
        """Turn the fire off. Always allowed."""
        self._pending.clear()
        await self._async_command(self.fireplace.async_turn_off)
        self._pending_power = False
        self._schedule_ready_refresh()
        await self.async_refresh()

    async def async_set_temperature(self, temperature: float) -> None:
        """Set the target temperature, holding it if the fire is lighting."""
        try:
            await self._async_command(
                lambda: self.fireplace.async_set_temperature(temperature)
            )
        except EsceaBusyError:
            self._hold("temperature", round_half_up(temperature))
            return
        await self.async_refresh()

    async def async_set_mode(self, mode: FireMode) -> None:
        """Set normal, boost or flame effect, holding it if the fire is lighting.

        Refused while the fire is off, because the fire would light.
        """
        status = self.data.status if self.data else None
        if status is not None and not status.is_on and mode is not FireMode.NORMAL:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="mode_while_off"
            )
        try:
            await self._async_command(lambda: self.fireplace.async_set_mode(mode))
        except EsceaBusyError:
            self._hold("mode", mode)
            return
        await self.async_refresh()

    def _hold(self, key: str, value: Any) -> None:
        LOGGER.debug("Fire is busy; holding %s=%s until it's ready", key, value)
        self._pending[key] = value
        self._schedule_ready_refresh()
        if self.data:
            self.async_set_updated_data(replace(self.data, pending=dict(self._pending)))

    async def _async_send_pending(self) -> None:
        pending, self._pending = self._pending, {}
        try:
            if "temperature" in pending:
                await self.fireplace.async_set_temperature(pending["temperature"])
            if "mode" in pending:
                await self.fireplace.async_set_mode(pending["mode"])
            await self.fireplace.async_get_status()
        except EsceaError as err:
            LOGGER.warning("Couldn't send the held commands: %s", err)

    async def async_set_timer(self, timer: Timer) -> None:
        """Change one of the fire's timers through its web page."""
        if not self.can_write_web or self._home_page is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="web_unavailable"
            )
        status = await self.fireplace.async_get_status()
        try:
            self._home_page = await self.web.async_set_timer(
                timer, fire_is_on=status.is_on, current=self._home_page.timers
            )
        except EsceaAuthError as err:
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="web_login_failed"
            ) from err
        except EsceaError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="timer_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        self._web_last_ok = dt_util.utcnow()
        if self.data:
            self.async_set_updated_data(
                replace(self.data, home_page=self._home_page, web_fresh=True)
            )

    @callback
    def async_shutdown_timers(self) -> None:
        """Cancel the lighting-window callback."""
        if self._ready_unsub:
            self._ready_unsub()
            self._ready_unsub = None


class EsceaG3Coordinator(DataUpdateCoordinator[EsceaData]):
    """Reads a Generation 3 (Wi-Fi) fire through Escea's NCAPI every 30 s.

    No lighting window or held commands: the fire accepts requests in any
    state and reports what it's doing itself.
    """

    config_entry: EsceaConfigEntry
    generation = GEN3
    min_temp = NCAPI_MIN_TEMPERATURE
    max_temp = NCAPI_MAX_TEMPERATURE
    temp_step = 0.5
    web_enabled = False
    can_write_web = False
    has_web_login = False

    def __init__(self, hass: HomeAssistant, entry: EsceaConfigEntry) -> None:
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.data[CONF_SERIAL]}",
            update_interval=UPDATE_INTERVAL,
            always_update=False,
        )
        self.serial = entry.data[CONF_SERIAL]
        self.client = EsceaNcapiClient(
            async_get_clientsession(hass), entry.data[CONF_HOST]
        )

    @property
    def supports_modes(self) -> bool:
        """Fan boost and flame effect are on gas fires only."""
        return self.data is None or self.data.status.is_gas  # type: ignore[union-attr]

    async def _async_update_data(self) -> EsceaData:
        try:
            status = await self.client.async_get_status()
        except EsceaError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="unreachable",
                translation_placeholders={"host": self.client.host},
            ) from err
        return EsceaData(status=status, busy_remaining=0.0)

    async def _async_set(self, **kwargs: Any) -> None:
        try:
            await self.client.async_set(**kwargs)
        except EsceaError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="ncapi_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        await self.async_refresh()

    async def async_turn_on(self) -> None:
        """Light the fire."""
        await self._async_set(on=True)

    async def async_turn_off(self) -> None:
        """Turn the fire off."""
        await self._async_set(on=False)

    async def async_set_temperature(self, temperature: float) -> None:
        """Set the target temperature."""
        await self._async_set(target_temperature=temperature)

    async def async_set_mode(self, mode: FireMode) -> None:
        """Set normal, boost or flame effect. Refused while off."""
        if self.data and not self.data.status.is_on and mode is not FireMode.NORMAL:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="mode_while_off"
            )
        if mode is FireMode.BOOST:
            await self._async_set(fan_boost=True)
        elif mode is FireMode.FLAME_EFFECT:
            await self._async_set(flame_effect=True)
        else:
            await self._async_set(fan_boost=False, flame_effect=False)

    async def async_set_timer(self, timer: Timer) -> None:
        """Generation 3 fires have no timers through the API."""
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="web_unavailable"
        )

    @callback
    def async_shutdown_timers(self) -> None:
        """Nothing to cancel."""


def clock_drift_minutes(clock: time | None, now: datetime) -> int | None:
    """Return how many minutes the fire's clock is ahead (+) or behind (-).

    The page shows hours and minutes only, so anything under a minute is
    noise. Handles midnight wrap.
    """
    if clock is None:
        return None
    fire = clock.hour * 60 + clock.minute
    real = now.hour * 60 + now.minute
    diff = (fire - real) % 1440
    return diff - 1440 if diff > 720 else diff


__all__ = [
    "CONF_GENERATION",
    "EsceaConfigEntry",
    "EsceaCoordinator",
    "EsceaData",
    "EsceaG3Coordinator",
    "clock_drift_minutes",
]

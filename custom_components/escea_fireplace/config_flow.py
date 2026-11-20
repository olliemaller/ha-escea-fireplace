"""Config flow for the Escea Fireplace integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aioescea import (
    DiscoveredFireplace,
    EsceaAuthError,
    EsceaConnectionError,
    EsceaError,
    EsceaPortInUseError,
    EsceaWebClient,
    NcapiStatus,
    async_probe,
)
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from .const import (
    CONF_GENERATION,
    CONF_MAC,
    CONF_PIN,
    CONF_SERIAL,
    CONF_WEB_ENABLED,
    CONF_WEB_INTERVAL,
    DEFAULT_WEB_INTERVAL_MINUTES,
    DOMAIN,
    GEN2,
    GEN3,
    LOGGER,
    MAX_WEB_INTERVAL_MINUTES,
    MIN_WEB_INTERVAL_MINUTES,
    NCAPI_PROBE_TIMEOUT,
)
from .coordinator import EsceaConfigEntry
from .transport import async_discover_fireplaces, async_identify

CONF_FIREPLACE = "fireplace"


def _title(serial: int) -> str:
    return f"Escea {serial}"


class EsceaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add an Escea fireplace."""

    VERSION = 1

    def __init__(self) -> None:
        self._found: dict[str, DiscoveredFireplace] = {}
        self._fire: DiscoveredFireplace | None = None
        self._g3: tuple[str, NcapiStatus] | None = None
        self._mac: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(entry: EsceaConfigEntry) -> EsceaOptionsFlow:
        """Return the options flow."""
        return EsceaOptionsFlow()

    @classmethod
    @callback
    def async_supports_options_flow(cls, entry: EsceaConfigEntry) -> bool:
        """Only Ethernet fires have a web page to configure."""
        return entry.data.get(CONF_GENERATION, GEN2) == GEN2

    # Adding by hand -------------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Search the network, or take an address."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = (user_input.get(CONF_HOST) or "").strip()
            if host and (g3 := await self._async_probe_g3(host)) is not None:
                return await self._async_create_g3(host, g3)
            try:
                if host:
                    return await self._async_found(
                        await async_identify(self.hass, host)
                    )
                fires = await async_discover_fireplaces(self.hass)
            except EsceaPortInUseError:
                errors["base"] = "port_in_use"
            except EsceaConnectionError:
                errors["base"] = "cannot_connect"
            except EsceaError:
                LOGGER.exception("Unexpected error finding the fireplace")
                errors["base"] = "unknown"
            else:
                configured = {
                    entry.unique_id for entry in self._async_current_entries()
                }
                new = [fire for fire in fires if str(fire.serial) not in configured]
                if not new:
                    errors["base"] = "no_fireplaces"
                elif len(new) == 1:
                    return await self._async_found(new[0])
                else:
                    self._found = {str(fire.serial): fire for fire in new}
                    return await self.async_step_pick()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Optional(CONF_HOST, default=""): str}),
            errors=errors,
        )

    async def _async_probe_g3(self, host: str) -> NcapiStatus | None:
        """Return the status if the address is a Generation 3 (Wi-Fi) fire."""
        status = await async_probe(
            async_get_clientsession(self.hass), host, timeout=NCAPI_PROBE_TIMEOUT
        )
        if status is None or not status.serial:
            return None
        return status

    async def _async_create_g3(
        self, host: str, status: NcapiStatus
    ) -> ConfigFlowResult:
        """Add a Generation 3 fire. No web page login is needed."""
        await self.async_set_unique_id(status.serial)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        serial: int | str = (
            int(status.serial) if status.serial.isdigit() else status.serial
        )
        data: dict[str, Any] = {
            CONF_HOST: host,
            CONF_SERIAL: serial,
            CONF_GENERATION: GEN3,
        }
        if self._mac:
            data[CONF_MAC] = self._mac
        return self.async_create_entry(title=f"Escea {serial}", data=data)

    async def async_step_pick(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose one of several fireplaces."""
        if user_input is not None:
            return await self._async_found(self._found[user_input[CONF_FIREPLACE]])
        options = [
            selector.SelectOptionDict(
                value=serial, label=f"{_title(fire.serial)} ({fire.host})"
            )
            for serial, fire in self._found.items()
        ]
        return self.async_show_form(
            step_id="pick",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_FIREPLACE): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=options)
                    )
                }
            ),
        )

    async def _async_found(self, fire: DiscoveredFireplace) -> ConfigFlowResult:
        await self.async_set_unique_id(str(fire.serial))
        self._abort_if_unique_id_configured(updates={CONF_HOST: fire.host})
        self._fire = fire
        return await self.async_step_web()

    # Found on the network by its MAC address -------------------------------

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> ConfigFlowResult:
        """A device with an Escea MAC address joined the network.

        Wi-Fi fires answer the NCAPI; Ethernet fires answer UDP.
        """
        self._mac = format_mac(discovery_info.macaddress)
        if (g3 := await self._async_probe_g3(discovery_info.ip)) is not None:
            await self.async_set_unique_id(g3.serial)
            self._abort_if_unique_id_configured(
                updates={CONF_HOST: discovery_info.ip, CONF_MAC: self._mac}
            )
            self._g3 = (discovery_info.ip, g3)
            self.context["title_placeholders"] = {"name": f"Escea {g3.serial}"}
            return await self.async_step_confirm()
        try:
            fire = await async_identify(self.hass, discovery_info.ip)
        except EsceaError:
            return self.async_abort(reason="not_escea")
        await self.async_set_unique_id(str(fire.serial))
        self._abort_if_unique_id_configured(
            updates={CONF_HOST: fire.host, CONF_MAC: self._mac}
        )
        self._fire = fire
        self.context["title_placeholders"] = {"name": _title(fire.serial)}
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a discovered fireplace."""
        if self._g3 is not None:
            host, status = self._g3
            if user_input is not None:
                return await self._async_create_g3(host, status)
            name, shown_host = f"Escea {status.serial}", host
        else:
            assert self._fire is not None
            if user_input is not None:
                return await self.async_step_web()
            name, shown_host = _title(self._fire.serial), self._fire.host
        self._set_confirm_only()
        return self.async_show_form(
            step_id="confirm",
            description_placeholders={"name": name, "host": shown_host},
        )

    # Web page login ---------------------------------------------------------

    async def _async_check_login(
        self, host: str, username: str, password: str
    ) -> str | None:
        """Return an error key, or None if the login works."""
        web = EsceaWebClient(
            async_get_clientsession(self.hass),
            host,
            username=username,
            password=password,
        )
        try:
            await web.async_validate_login()
        except EsceaAuthError:
            return "invalid_auth"
        except EsceaError:
            return "web_unreachable"
        return None

    async def async_step_web(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Log in to the fire's web page, for timers and diagnostics.

        The serial number and PIN are tried first, since that's the login on
        most fires. If they don't work, ask, and allow skipping.
        """
        fire = self._fire
        assert fire is not None
        errors: dict[str, str] = {}

        if user_input is None:
            if (
                await self._async_check_login(
                    fire.host, str(fire.serial), str(fire.pin)
                )
                is None
            ):
                return self._async_create(str(fire.serial), str(fire.pin))
        elif not user_input.get(CONF_USERNAME) and not user_input.get(CONF_PASSWORD):
            return self._async_create(None, None)
        else:
            error = await self._async_check_login(
                fire.host, user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
            if error is None:
                return self._async_create(
                    user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="web",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_USERNAME, default=str(fire.serial)): str,
                    vol.Optional(CONF_PASSWORD): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders={"host": fire.host},
        )

    @callback
    def _async_create(
        self, username: str | None, password: str | None
    ) -> ConfigFlowResult:
        fire = self._fire
        assert fire is not None
        data: dict[str, Any] = {
            CONF_HOST: fire.host,
            CONF_SERIAL: fire.serial,
            CONF_PIN: fire.pin,
        }
        if username and password:
            data[CONF_USERNAME] = username
            data[CONF_PASSWORD] = password
        if self._mac:
            data[CONF_MAC] = self._mac
        return self.async_create_entry(title=_title(fire.serial), data=data)

    # Change the address -----------------------------------------------------

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the fireplace's address."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None and entry.data.get(CONF_GENERATION) == GEN3:
            host = user_input[CONF_HOST].strip()
            status = await self._async_probe_g3(host)
            if status is None:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(status.serial)
                self._abort_if_unique_id_mismatch(reason="wrong_fireplace")
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_HOST: host}
                )
        elif user_input is not None:
            try:
                fire = await async_identify(self.hass, user_input[CONF_HOST].strip())
            except EsceaPortInUseError:
                errors["base"] = "port_in_use"
            except EsceaError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(str(fire.serial))
                self._abort_if_unique_id_mismatch(reason="wrong_fireplace")
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_HOST: fire.host}
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {vol.Required(CONF_HOST, default=entry.data[CONF_HOST]): str}
            ),
            errors=errors,
        )

    # Fix the web login ------------------------------------------------------

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """The web page stopped accepting the login."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the web login again."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            error = await self._async_check_login(
                entry.data[CONF_HOST],
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
            )
            if error is None:
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME,
                        default=entry.data.get(
                            CONF_USERNAME, str(entry.data[CONF_SERIAL])
                        ),
                    ): str,
                    vol.Required(CONF_PASSWORD): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                }
            ),
            errors=errors,
        )


class EsceaOptionsFlow(OptionsFlowWithReload):
    """Choose whether and how often to read the fire's web page."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_WEB_ENABLED, default=options.get(CONF_WEB_ENABLED, True)
                    ): bool,
                    vol.Required(
                        CONF_WEB_INTERVAL,
                        default=options.get(
                            CONF_WEB_INTERVAL, DEFAULT_WEB_INTERVAL_MINUTES
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=MIN_WEB_INTERVAL_MINUTES,
                            max=MAX_WEB_INTERVAL_MINUTES,
                            step=1,
                            unit_of_measurement="min",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                }
            ),
        )

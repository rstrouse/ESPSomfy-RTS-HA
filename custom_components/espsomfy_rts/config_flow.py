"""Config flow for ESPSomfy RTS."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import zeroconf
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PIN,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.util.network import is_host_valid

from .const import DOMAIN
from .controller import (
    DiscoveryError,
    ESPSomfyAPI,
    ESPSomfyController,
    InvalidHost,
    LoginError,
)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, "Server Address"): TextSelector(
            TextSelectorConfig(type=TextSelectorType.URL)
        )
    }
)

_LOGGER = logging.getLogger(__name__)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""

    session = aiohttp_client.async_get_clientsession(hass)
    async with session.get(f'http://{data["host"]}/discovery') as resp:
        if resp.status == 200:
            pass
        else:
            raise DiscoveryError(f"{await resp.text()}")
    return {"title": "ESPSomfy RTS", "server_id": "A1"}


# The ConfigFlow is only accessed when first setting up the integration.  This simply
# collects the initial data from the user to determine whether the integration can
# be installed.
class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configuration flow for ESPSomfyController."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        self.controller: ESPSomfyController
        self.zero_conf: zeroconf.ZeroconfServiceInfo
        self.server_id = None
        self.host = None

    @callback
    def _show_setup_form(
        self,
        user_input: dict[str, Any] | None = None,
        errors: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Show the setup form to the user."""
        host = user_input.get(CONF_HOST, self.host) if user_input else ""
        return self.async_show_form(
            step_id="user",
            data_schema=_get_data_schema(self.hass, data=user_input, host=host),
            errors=errors,
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the flow initialized by the user."""

        errors = {}
        if user_input is not None:
            try:
                if not is_host_valid(user_input.get(CONF_HOST, "")):
                    raise InvalidHost
                self.host = user_input.get(CONF_HOST, "")
                api = ESPSomfyAPI(self.hass, 0, user_input)
                await api.discover()
                await self.async_set_unique_id(f"espsomfy_{api.server_id}")
                self._abort_if_unique_id_configured(updates={CONF_HOST: self.host})
                await api.login(
                    {
                        "username": user_input.get(CONF_USERNAME, ""),
                        "password": user_input.get(CONF_PASSWORD, ""),
                        "pin": user_input.get(CONF_PIN, ""),
                    }
                )
                return self.async_create_entry(
                    title=api.deviceName,
                    description=f"ESPSomfy RTS {api.server_id}",
                    data=user_input,
                )
            except InvalidHost:
                errors[CONF_HOST] = "wrong_host"
            except ConnectionError:
                errors["base"] = "cannot_connect"
            except DiscoveryError:
                errors[CONF_HOST] = "discovery_error"
            except LoginError as ex:
                errors[ex.args[0]] = ex.args[1]
        return self._show_setup_form(user_input=user_input, errors=errors)

    async def async_step_zeroconf(
        self, discovery_info: zeroconf.ZeroconfServiceInfo
    ) -> FlowResult:
        """Handle zeroconf discovery."""
        self.zero_conf = discovery_info

        # Check if already configured
        self.server_id = discovery_info.properties.get("serverId", "")
        # This was part of PR#54 and was incorrect the server id is simply the chip id of the ESP32 but could
        # be replicated by other items.  If this server id is already configured then we do not want
        # to add the device again.  Since the unique id contains the server id this will always be the same
        # as identified by the chip id on the ESP32.
        # await self.async_set_unique_id(f"{self.server_id}")
        self.host = discovery_info.host
        await self.async_set_unique_id(f"espsomfy_{self.server_id}")

        self._abort_if_unique_id_configured(
            updates={CONF_HOST: discovery_info.host}, reload_on_update=True
        )
        self.context.update(
            {
                "title_placeholders": {
                    CONF_NAME: discovery_info.hostname,
                    CONF_HOST: discovery_info.host,
                    "model": discovery_info.properties.get("model", ""),
                    "configuration_url": f"http://{discovery_info.host}",
                },
            }
        )
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle a flow initiated by zeroconf."""
        if user_input is not None:
            return self.async_create_entry(
                title=self.zero_conf.hostname,
                data={
                    CONF_HOST: self.zero_conf.host,
                },
            )

        return self.async_show_form(
            step_id="zeroconf_confirm",
            description_placeholders={
                CONF_NAME: self.zero_conf.hostname,
                "model": self.zero_conf.properties.get("model", ""),
                "server_id": self.server_id,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for espsomfy_rts."""
        return ESPSomfyOptionsFlowHandler(config_entry)


class ESPSomfyOptionsFlowHandler(config_entries.OptionsFlow):
    """Options flow for espsomfy_rts component."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize the OptionsFlow."""
        self._config_entry = config_entry
        self._errors: dict[str, Any] = {}
        self._host = (
            config_entry.data.get(CONF_HOST, "")
            if config_entry and config_entry.data
            else ""
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure options for espsomfy_rts."""
        errors = {}
        if user_input is not None:
            try:
                if not is_host_valid(user_input[CONF_HOST]):
                    raise InvalidHost
                api = ESPSomfyAPI(self.hass, 0, user_input)
                await api.discover()
                await api.login(
                    {
                        "username": user_input.get(CONF_USERNAME, ""),
                        "password": user_input.get(CONF_PASSWORD, ""),
                        "pin": user_input.get(CONF_PIN, ""),
                    }
                )
                # Update config entry with data from user input
                self.hass.config_entries.async_update_entry(
                    self._config_entry, title=api.deviceName, data=user_input
                )
                return self.async_create_entry(
                    title=api.deviceName,
                    data=user_input,
                )
            except InvalidHost:
                errors[CONF_HOST] = "wrong_host"
            except ConnectionError:
                errors["base"] = "cannot_connect"
            except DiscoveryError:
                errors[CONF_HOST] = "discovery_error"
            except LoginError as ex:
                errors[ex.args[0]] = ex.args[1]

        return self.async_show_form(
            step_id="init",
            data_schema=_get_data_schema(
                self.hass, data=self._config_entry.data, host=self._host
            ),
            errors=errors,
        )


def _get_data_schema(
    hass: HomeAssistant,
    data: dict[str, Any] | None = None,
    host: str = "",
) -> vol.Schema:
    """Get a schema with default values."""
    # If tracking home or no config entry is passed in, default value come from Home location
    if data is None or data.get(CONF_HOST, host) == "":
        return vol.Schema(
            {
                vol.Required(CONF_HOST, default=host): str,
                vol.Optional(CONF_USERNAME, description={"suggested_value": ""}): str,
                vol.Optional(CONF_PASSWORD, description={"suggested_value": ""}): str,
                vol.Optional(CONF_PIN, description={"suggested_value": ""}): str,
            }
        )
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=data.get(CONF_HOST)): str,
            vol.Optional(
                CONF_USERNAME,
                description={"suggested_value": data.get(CONF_USERNAME, None)},
            ): str,
            vol.Optional(
                CONF_PASSWORD,
                description={"suggested_value": data.get(CONF_PASSWORD, None)},
            ): str,
            vol.Optional(
                CONF_PIN,
                description={"suggested_value": data.get(CONF_PIN, None)},
            ): str,
        }
    )

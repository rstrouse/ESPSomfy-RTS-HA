"""Config flow for ESPSomfy RTS."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import zeroconf
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD, CONF_PIN
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


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.
    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    print("validate_input")
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
    """Configuration flow for ESPSomfyController"""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        self.controller: ESPSomfyController = None
        self.zero_conf = None
        self.server_id = None
        self.host = None

    @callback
    def _show_setup_form(
        self,
        user_input: dict[str, Any] | None = None,
        errors: dict[str, Any] = None,
    ) -> FlowResult:
        """Show the setup form to the user."""
        host = user_input.get(CONF_HOST, self.host) if user_input else ""
        return self.async_show_form(
            step_id="user",
            data_schema=_get_data_schema(self.hass, data=user_input, host=host),
            errors=errors,
        )

    async def async_step_user(self, user_input: dict[str, Any] = None) -> FlowResult:
        """Handle the flow initialized by the user."""

        errors = {}
        print("async_step_user")
        if user_input is not None:
            try:
                print(user_input)
                if not is_host_valid(user_input.get(CONF_HOST, "")):
                    raise InvalidHost()
                else:
                    self.host = user_input.get(CONF_HOST, "")

                api = ESPSomfyAPI(self.hass, user_input)
                await api.discover()
                await self.async_set_unique_id(api.server_id)
                self._abort_if_unique_id_configured()
                await api.login(
                    {
                        "username": user_input.get(CONF_USERNAME, ""),
                        "password": user_input.get(CONF_PASSWORD, ""),
                        "pin": user_input.get(CONF_PIN, ""),
                    }
                )
                return self.async_create_entry(
                    title=f"ESPSomfy RTS {api.server_id}",
                    description=api.deviceName,
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
        # Do not probe the device if the host is already configured
        self._async_abort_entries_match({CONF_HOST: discovery_info.host})

        # Check if already configured
        self.server_id = discovery_info.properties.get("serverId", "")
        await self.async_set_unique_id(f"espsomfy_{self.server_id}")
        self.host = discovery_info.host
        self._abort_if_unique_id_configured()
        self.context.update(
            {
                "title_placeholders": {
                    "name": f"Device: {self.server_id}",
                    "server_id": self.server_id,
                    "model": discovery_info.properties.get("model", ""),
                },
            }
        )
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] = None
    ) -> FlowResult:
        """Handle a flow initiated by zeroconf."""
        errors = {}
        data = {
            "server_id": self.server_id,
            CONF_HOST: self.zero_conf.host,
            "model": self.zero_conf.properties.get("model", ""),
        }

        if user_input is not None:
            server_id = self.zero_conf.properties.get("serverId", "")
            try:
                api = ESPSomfyAPI(self.hass, user_input)
                await api.discover()

                await self.async_set_unique_id(api.server_id)
                self._abort_if_unique_id_configured()
                await api.login(
                    {
                        "username": user_input.get(CONF_USERNAME, ""),
                        "password": user_input.get(CONF_PASSWORD, ""),
                        "pin": user_input.get(CONF_PIN, ""),
                    }
                )
                return self.async_create_entry(
                    title=f"ESP Somfy RTS {api.server_id}",
                    description=api.deviceName,
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

            return self.async_create_entry(
                title=f"ESP Somfy RTS {server_id}", data=data
            )
        return self.async_show_form(
            step_id="zeroconf_confirm",
            data_schema=_get_data_schema(
                self.hass, data=data, host=self.zero_conf.host
            ),
            description_placeholders={
                "server_id": self.zero_conf.properties.get("serverId", ""),
                "model": self.zero_conf.properties.get("model", ""),
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
                    raise InvalidHost()
                api = ESPSomfyAPI(self.hass, user_input)
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
                    title=f"ESPSomfy RTS {api.server_id}",
                    description=api.deviceName,
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

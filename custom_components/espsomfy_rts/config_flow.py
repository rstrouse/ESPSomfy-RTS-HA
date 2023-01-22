"""Config flow for ESPSomfy RTS."""
from __future__ import annotations

from .controller import ESPSomfyAPI, ESPSomfyController, DiscoveryError, InvalidHost
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.const import CONF_HOST
from homeassistant.util.network import is_host_valid
from homeassistant.components import zeroconf

from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorType,
    TextSelectorConfig,
)

import voluptuous as vol


from .const import DOMAIN

from typing import Any

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
    session = aiohttp_client.async_get_clientsession(hass)
    async with session.get(f'http://{data["host"]}/discovery') as resp:
        if resp.status == 200:
            pass
        else:
            raise DiscoveryError(f"{await resp.text()}")
    return {"title": "ESPSomfy RTS", "server_id": "A1"}


# The ConfigFlow is only accessed when first setting up the integration.  This simply
# collects the initial data from the user to determine whether the integration can
# be installed.  Since I cannot seem to make the zero conf stuff start, I am simply
# allowing the user to enter the IP address at this point.
class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configuration flow for ESPSomfyController"""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        self.controller: ESPSomfyController = None
        self.zero_conf = None

    async def async_step_user(self, user_input: dict[str, Any] = None) -> FlowResult:
        """Handle the flow initialized by the user."""

        errors = {}

        if user_input is not None:
            try:
                if not is_host_valid(user_input[CONF_HOST]):
                    raise InvalidHost()

                api = ESPSomfyAPI(self.hass, user_input)
                await api.discover()
                await self.async_set_unique_id(api.server_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"ESP Somfy RTS {api.server_id}", data=user_input
                )
            except InvalidHost:
                errors[CONF_HOST] = "wrong_host"
            except ConnectionError:
                errors["base"] = "cannot_connect"
            except DiscoveryError as err:
                errors[CONF_HOST] = f"Discovery: {str(err)}"
        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )

    async def async_step_zeroconf(
        self, discovery_info: zeroconf.ZeroconfServiceInfo
    ) -> FlowResult:
        """Handle zeroconf discovery."""
        self.zero_conf = discovery_info
        # Do not probe the device if the host is already configured
        self._async_abort_entries_match({CONF_HOST: discovery_info.host})

        # Check if already configured
        await self.async_set_unique_id(discovery_info.properties["serverId"])
        self._abort_if_unique_id_configured()

        self.context.update(
            {
                "title_placeholders": {
                    "server_id": discovery_info.properties["serverId"],
                    "model": discovery_info.properties["model"],
                }
            }
        )
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] = None
    ) -> FlowResult:
        """Handle a flow initiated by zeroconf."""
        if user_input is not None:
            title = f"{self.controller.model} {self.controller.server_id}"
            return self.async_create_entry(
                title=title,
                data={
                    CONF_HOST: self.zero_conf.host,
                    "server_id": self.zero_conf.properties["serverId"],
                },
            )
        return self.async_show_form(
            step_id="zeroconf_confirm",
            data_schema=vol.Schema({}),
            description_placeholders={
                "server_id": self.zero_conf.properties["serverId"],
                "model": self.zero_conf.properties["model"],
            },
        )

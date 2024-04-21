"""Provides device actions for ESPSomfy RTS."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.components.device_automation import (
    async_get_entity_registry_entry_or_raise,
    async_validate_entity_schema,
    toggle_entity,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_MODE,
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_ENTITY_ID,
    CONF_TYPE,
)
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import get_capability
from homeassistant.helpers.typing import ConfigType, TemplateVarsType

from .const import API_RESTORE, ATTR_RESTOREFILE, DOMAIN, ATTR_AVAILABLE_MODES

RESTORE_SCHEMA = cv.DEVICE_ACTION_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): "restore",
        vol.Required(CONF_ENTITY_ID): cv.entity_id_or_uuid,
        vol.Required(ATTR_RESTOREFILE): vol.Coerce(int),
    }
)


ONOFF_SCHEMA = toggle_entity.ACTION_SCHEMA.extend({vol.Required(CONF_DOMAIN): DOMAIN})

_ACTION_SCHEMA = cv.DEVICE_ACTION_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): vol.In({"Reboot", "Backup"}),
        vol.Required(CONF_ENTITY_ID): cv.entity_id_or_uuid,
    }
)


async def async_validate_action_config(
    hass: HomeAssistant, config: ConfigType
) -> ConfigType:
    """Validate config."""
    return async_validate_entity_schema(hass, config, _ACTION_SCHEMA)


async def async_get_actions(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, str]]:
    """List device actions for ESPSomfy RTS devices."""
    print("Getting ESPSomfy RTS Actions")
    actions = await toggle_entity.async_get_actions(hass, device_id, DOMAIN)
    registry = er.async_get(hass)
    for entry in er.async_entries_for_device(registry, device_id):
        if entry.entity_id.startswith("button.reboot"):
            actions.append({CONF_DEVICE_ID: device_id,
                            CONF_DOMAIN: DOMAIN,
                            CONF_ENTITY_ID: entry.entity_id,
                            CONF_TYPE: "Reboot"
                            })
        elif entry.entity_id.startswith("button.backup"):
            print(entry)
            actions.append({CONF_DEVICE_ID: device_id,
                            CONF_DOMAIN: DOMAIN,
                            CONF_ENTITY_ID: entry.entity_id,
                            CONF_TYPE: "Backup"
                            })

    return actions


async def async_call_action_from_config(
    hass: HomeAssistant,
    config: ConfigType,
    variables: TemplateVarsType,
    context: Context | None,
) -> None:
    """Execute a device action."""
    service_data = {ATTR_ENTITY_ID: config[CONF_ENTITY_ID]}
    # print(context)
    # print(service_data)
    # print(config)
    if config[CONF_TYPE] == "restore":
        service = API_RESTORE
    elif config[CONF_TYPE] == "Backup":
        await hass.services.async_call(
                DOMAIN,
                "backup",
                {
                    ATTR_ENTITY_ID: config[CONF_ENTITY_ID],
                },
                blocking=True,
                context=context,
            )
        return

    elif config[CONF_TYPE] == "Reboot":
        await hass.services.async_call(
                DOMAIN,
                "reboot",
                {
                    ATTR_ENTITY_ID: config[CONF_ENTITY_ID],
                },
                blocking=True,
                context=context,
            )
        return
    else:
        return await toggle_entity.async_call_action_from_config(
            hass, config, variables, context, DOMAIN
        )

    ## await hass.services.async_call(
    ##    DOMAIN, service, service_data, blocking=True, context=context
    ## )


async def async_get_action_capabilities(
    hass: HomeAssistant, config: ConfigType
) -> dict[str, vol.Schema]:
    """List action capabilities."""
    action_type = config[CONF_TYPE]
    fields = {}
    if action_type == "restore":
        fields[vol.Required(ATTR_RESTOREFILE)] = vol.Required()
    elif action_type == "backup":
        try:
            entry = async_get_entity_registry_entry_or_raise(
                hass, config[CONF_ENTITY_ID]
            )
            available_modes = (
                get_capability(hass, entry.entity_id, ATTR_AVAILABLE_MODES) or []
            )
        except HomeAssistantError:
            available_modes = []
        fields[vol.Required(ATTR_MODE)] = vol.In(available_modes)
    else:
        return {}

    return {"extra_fields": vol.Schema(fields)}

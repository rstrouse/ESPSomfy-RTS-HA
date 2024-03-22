"""The ESPSomfy RTS integration."""
from __future__ import annotations
from enum import IntFlag

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.device_registry import DeviceEntry

from .const import DOMAIN, PLATFORMS
from .controller import ESPSomfyAPI, ESPSomfyController


class ESPSomfyRTSEntityFeature(IntFlag):
    """Supported features of ESPSomfy Entities."""
    REBOOT = 1
    BACKUP = 2


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ESPSomfy RTS from a config entry."""
    api = ESPSomfyAPI(hass, entry.entry_id, entry.data)
    controller = ESPSomfyController(entry.entry_id, hass, api)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = controller
    await api.get_initial()
    if not api.is_configured:
        raise ConfigEntryNotReady(
            f"Could not find ESPSomfy RTS device with address {api.get_api_url()}"
        )
    entry.title = api.deviceName
    async def _async_ws_close(_: Event) -> None:
        await controller.ws_close()

    # If home assistant is unloaded gracefully then we need to stop the socket.
    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_ws_close)
    )
    # This does not occur until the socket connects.
    # await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await controller.ws_connect()

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    controller:ESPSomfyController = hass.data[DOMAIN].get(entry.entry_id)
    if controller is not None:
        await controller.ws_close()
        if(controller.api.is_configured):
            if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
                hass.data[DOMAIN].pop(entry.entry_id)
            return unload_ok
    return True


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry: DeviceEntry
) -> bool:
    """Remove a config entry from a device"""
    return True

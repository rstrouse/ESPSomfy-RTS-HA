"""The ESPSomfy RTS integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .const import DOMAIN
from .controller import ESPSomfyAPI, ESPSomfyController

# For your initial PR, limit it to 1 platform.
PLATFORMS: list[Platform] = [Platform.COVER]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ESPSomfy RTS from a config entry."""
    api = ESPSomfyAPI(hass, entry.data)
    controller = ESPSomfyController(entry.entry_id, hass, api)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = controller
    await api.get_initial()

    async def _async_ws_close(_: Event) -> None:
        await controller.ws_close()

    # If home assistant is unloaded gracefully then we need to stop the socket.
    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_ws_close)
    )

    hass.config_entries.async_setup_platforms(entry, PLATFORMS)
    await controller.ws_connect()

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        controller = hass.data[DOMAIN].pop(entry.entry_id)
        await controller.ws_close()

    return unload_ok


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry: DeviceEntry
) -> bool:
    """Remove a config entry from a device"""
    return True

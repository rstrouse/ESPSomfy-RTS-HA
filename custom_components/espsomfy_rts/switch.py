"""Switches related to ESPSomfy-RTS-HA"""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback


from .entity import ESPSomfyEntity
from .controller import ESPSomfyController
from .const import DOMAIN, EVT_SHADESTATE


from homeassistant.components.switch import SwitchEntity

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up shades for the shade controller."""
    controller = hass.data[DOMAIN][config_entry.entry_id]
    new_entities = []
    for shade in controller.api.shades:
        try:
            if "shadeType" in shade:
                match(shade["shadeType"]):
                    case 3:
                        new_entities.append(ESPSomfySunSwitch(controller, shade))

        except KeyError:
            pass
    if new_entities:
        async_add_entities(new_entities)


class ESPSomfySunSwitch(ESPSomfyEntity, SwitchEntity):
    """A sun flag switch for toggling sun mode"""

    def __init__(self, controller: ESPSomfyController, data):
        """Initialize a new SunSwitch"""
        super().__init__(controller=controller)
        self._controller = controller
        self._shade_id = data["shadeId"]
        self._attr_unique_id = f"{controller.unique_id}_{self._shade_id}"
        self._attr_name = data["name"]
        self._attr_has_entity_name = False
        self._available = True
        if "flags" in data:
            self._value = bool((int(data["flags"]) & 0x01) == 0x01)
        else:
            self._value = False

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if "shadeId" in self._controller.data:
            if self._controller.data["shadeId"] == self._shade_id:
                if (
                    self._controller.data["event"] == EVT_SHADESTATE
                    and "flags" in self._controller.data
                ):
                    self._value = bool((int(self._controller.data["flags"]) & 0x01) == 0x01)
                self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        await self.coordinator.api.sun_flag_on(self._shade_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        await self.coordinator.api.sun_flag_off(self._shade_id)

    @property
    def should_poll(self) -> bool:
        return False

    @property
    def available(self) -> bool:
        return self._available

    @property
    def name(self) -> str:
        return self._attr_name

    @property
    def is_on(self) -> bool:
        return self._value

    @property
    def icon(self) -> str:
        return "mdi:white-balance-sunny"

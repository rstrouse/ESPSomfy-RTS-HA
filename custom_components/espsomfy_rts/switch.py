"""Switches related to ESPSomfy-RTS-HA"""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback


from .entity import ESPSomfyEntity
from .controller import ESPSomfyController
from .const import DOMAIN, EVT_SHADESTATE, EVT_GROUPSTATE, EVT_CONNECTED


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
            if "shadeType" in shade and (int(shade["shadeType"]) == 9 or int(shade["shadeType"] == 10):
                new_entities.append(ESPSomfyBinarySwitch(controller=controller, data=shade))
            elif "sunSensor" in shade:
                if shade["sunSensor"] is True:
                    new_entities.append(ESPSomfySunSwitch(controller=controller, data=shade))
            elif "shadeType" in shade:
                match(shade["shadeType"]):
                    case 3:
                        new_entities.append(ESPSomfySunSwitch(controller=controller, data=shade))
        except KeyError:
            pass

    for group in controller.api.groups:
        try:
            if "sunSensor" in group:
                if group["sunSensor"] is True:
                    new_entities.append(ESPSomfySunSwitch(controller=controller, data=group))

        except KeyError:
            pass


    if new_entities:
        async_add_entities(new_entities)


class ESPSomfySunSwitch(ESPSomfyEntity, SwitchEntity):
    """A sun flag switch for toggling sun mode"""

    def __init__(self, controller: ESPSomfyController, data) -> None:
        """Initialize a new SunSwitch"""
        super().__init__(controller=controller, data=data)
        self._controller = controller
        self._shade_id = None
        self._group_id = None
        self._attr_icon = "mdi:white-balance-sunny"
        self._attr_name = data["name"]
        self._attr_has_entity_name = False
        self._sunswitch_type = None
        self._available = True
        if "groupId" in data:
            self._group_id = data["groupId"]
            self._attr_unique_id = f"sunswitch_group_{controller.unique_id}_{self._group_id}"
            self._sunswitch_type = "group"
        else:
            self._shade_id = data["shadeId"]
            self._attr_unique_id = f"sunswitch_{controller.unique_id}_{self._shade_id}"
            self._sunswitch_type = "motor"

        if "flags" in data:
            self._attr_is_on = bool((int(data["flags"]) & 0x01) == 0x01)
        else:
            self._attr_is_on = False

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if(self._controller.data["event"] == EVT_CONNECTED and "connected" in self._controller.data):
            self._available = bool(self._controller.data["connected"])
            self.async_write_ha_state()
        elif (self._sunswitch_type == "motor"
            and "shadeId" in self._controller.data
            and self._controller.data["shadeId"] == self._shade_id):
            if (
                self._controller.data["event"] == EVT_SHADESTATE
                and "flags" in self._controller.data
            ):
                self._attr_is_on = bool((int(self._controller.data["flags"]) & 0x01) == 0x01)
                self.async_write_ha_state()
        elif(self._sunswitch_type == "group"
             and "groupId" in self._controller.data
             and self._controller.data["groupId"] == self._group_id):
            if (
                self._controller.data["event"] == EVT_GROUPSTATE
                and "flags" in self._controller.data
            ):
                self._attr_is_on = bool((int(self._controller.data["flags"]) & 0x01) == 0x01)
                self.async_write_ha_state()


    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        if self._sunswitch_type == "motor":
            await self.coordinator.api.sun_flag_on(self._shade_id)
            return
        await self.coordinator.api.sun_flag_group_on(self._group_id)


    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        if self._sunswitch_type == "motor":
            await self.coordinator.api.sun_flag_off(self._shade_id)
            return
        await self.coordinator.api.sun_flag_group_off(self._group_id)

    @property
    def available(self) -> bool:
        """Indicates whether the shade is available"""
        return self._available


class ESPSomfyBinarySwitch(ESPSomfyEntity, SwitchEntity):
    """A binary switch for toggling a dry contact"""

    def __init__(self, controller: ESPSomfyController, data) -> None:
        """Initialize a new BinarySwitch"""
        super().__init__(controller=controller, data=data)
        self._controller = controller
        self._shade_id = None
        self._group_id = None
        self._attr_name = data["name"]
        self._attr_has_entity_name = False
        self._binaryswitch_type = data["shadeType"]
        self._shade_id = data["shadeId"]
        self._available = True
        self._attr_unique_id = f"binaryswitch_{controller.unique_id}_{self._shade_id}"
        if "position" in data:
            self._attr_is_on = bool((int(data["position"])) > 0)
        else:
            self._attr_is_on = False

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if(self._controller.data["event"] == EVT_CONNECTED and "connected" in self._controller.data):
            self._available = bool(self._controller.data["connected"])
            self.async_write_ha_state()
        elif("position" in self._controller.data and self._controller.data["shadeId"] == self._shade_id):
            self._attr_is_on = bool((int(self._controller.data["position"])) > 0)
            self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Indicates whether the shade is available"""
        return self._available

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        await self.coordinator.api.toggle_shade(self._shade_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        await self.coordinator.api.toggle_shade(self._shade_id)

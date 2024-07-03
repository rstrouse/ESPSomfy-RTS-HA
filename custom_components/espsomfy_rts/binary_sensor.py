"""Binary sensors related to ESPSomfy-RTS-HA."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, EVT_CONNECTED, EVT_GROUPSTATE, EVT_SHADESTATE
from .controller import ESPSomfyController
from .entity import ESPSomfyEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up shades for the shade controller."""
    controller = hass.data[DOMAIN][config_entry.entry_id]
    new_entities = []
    data = controller.api.get_config()
    if "serverId" in data:
        for shade in controller.api.shades:
            try:
                if "sunSensor" in shade:
                    if shade["sunSensor"] is True:
                        new_entities.append(ESPSomfySunSensor(controller, shade))
                        new_entities.append(ESPSomfyWindSensor(controller, shade))
                    elif "shadeType" in shade:
                        match shade["shadeType"]:
                            case 3:
                                new_entities.append(
                                    ESPSomfyWindSensor(controller, shade)
                                )

                elif "shadeType" in shade:
                    match shade["shadeType"]:
                        case 3:
                            new_entities.append(ESPSomfySunSensor(controller, shade))
                            new_entities.append(ESPSomfyWindSensor(controller, shade))
            except KeyError:
                pass
        for group in controller.api.groups:
            try:
                if "sunSensor" in group:
                    if group["sunSensor"] is True:
                        new_entities.append(ESPSomfySunSensor(controller, group))
                        new_entities.append(ESPSomfyWindSensor(controller, group))
            except KeyError:
                pass
    if new_entities:
        async_add_entities(new_entities)


class ESPSomfySunSensor(ESPSomfyEntity, BinarySensorEntity):
    """A sun flag sensor indicating whether there is sun."""

    def __init__(self, controller: ESPSomfyController, data) -> None:
        """Initialize a new SunSensor."""
        super().__init__(controller=controller, data=data)
        self._controller = controller
        self._shade_id = None
        self._group_id = None
        self._sensor_type = None
        self._available = True
        if "groupId" in data:
            self._group_id = data["groupId"]
            self._attr_unique_id = f"sun_group_{controller.unique_id}_{self._group_id}"
            self._sensor_type = "group"
        else:
            self._shade_id = data["shadeId"]
            self._attr_unique_id = f"sun_{controller.unique_id}_{self._shade_id}"
            self._sensor_type = "motor"
        self._attr_name = data["name"]
        self._attr_has_entity_name = False
        if "flags" in data:
            self._attr_is_on = bool((int(data["flags"]) & 0x20) == 0x20)
        else:
            self._attr_is_on = False

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if (
            self._controller.data["event"] == EVT_CONNECTED
            and "connected" in self._controller.data
        ):
            if self._available != bool(self._controller.data["connected"]):
                self._available = bool(self._controller.data["connected"])
                self.async_write_ha_state()
        elif (
            self._sensor_type == "motor"
            and "shadeId" in self._controller.data
            and self._controller.data["shadeId"] == self._shade_id
            and self._controller.data["event"] == EVT_SHADESTATE
            and "flags" in self._controller.data
        ):
            if self._attr_is_on != bool(
                (int(self._controller.data["flags"]) & 0x20) == 0x20
            ):
                self._attr_is_on = bool(
                    (int(self._controller.data["flags"]) & 0x20) == 0x20
                )
                self.async_write_ha_state()
        elif (
            self._sensor_type == "group"
            and "groupId" in self._controller.data
            and self._controller.data["groupId"] == self._group_id
            and self._controller.data["event"] == EVT_GROUPSTATE
            and "flags" in self._controller.data
        ):
            if self._attr_is_on != bool(
                (int(self._controller.data["flags"]) & 0x20) == 0x20
            ):
                self._attr_is_on = bool(
                    (int(self._controller.data["flags"]) & 0x20) == 0x20
                )
                self.async_write_ha_state()

    @property
    def icon(self) -> str:
        """The icon for the sun sensor."""
        if self.is_on:
            return "mdi:weather-sunny"
        return "mdi:weather-sunny-off"

    @property
    def available(self) -> bool:
        """Indicates whether the shade is available."""
        return self._available


class ESPSomfyWindSensor(ESPSomfyEntity, BinarySensorEntity):
    """A sun flag sensor indicating whether there is sun."""

    def __init__(self, controller: ESPSomfyController, data) -> None:
        """Initialize a new SunSensor."""
        super().__init__(controller=controller, data=data)
        self._controller = controller
        self._shade_id = None
        self._group_id = None
        self._sensor_type = None
        self._available = True
        if "groupId" in data:
            self._group_id = data["groupId"]
            self._attr_unique_id = f"wind_group_{controller.unique_id}_{self._group_id}"
            self._sensor_type = "group"
        else:
            self._shade_id = data["shadeId"]
            self._attr_unique_id = f"wind_{controller.unique_id}_{self._shade_id}"
            self._sensor_type = "motor"
        self._attr_name = data["name"]
        self._attr_has_entity_name = False
        if "flags" in data:
            self._attr_is_on = bool((int(data["flags"]) & 0x10) == 0x10)
        else:
            self._attr_is_on = False

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.registry_entry.disabled:
            return
        if (
            self._controller.data["event"] == EVT_CONNECTED
            and "connected" in self._controller.data
        ):
            if self._available != bool(self._controller.data["connected"]):
                self._available = bool(self._controller.data["connected"])
                self.async_write_ha_state()
        elif (
            self._sensor_type == "motor"
            and "shadeId" in self._controller.data
            and self._controller.data["shadeId"] == self._shade_id
            and self._controller.data["event"] == EVT_SHADESTATE
            and "flags" in self._controller.data
        ):
            if self._attr_is_on != bool(
                (int(self._controller.data["flags"]) & 0x10) == 0x10
            ):
                self._attr_is_on = bool(
                    (int(self._controller.data["flags"]) & 0x10) == 0x10
                )
                self.async_write_ha_state()
        elif (
            self._sensor_type == "group"
            and "groupId" in self._controller.data
            and self._controller.data["groupId"] == self._group_id
            and self._controller.data["event"] == EVT_GROUPSTATE
            and "flags" in self._controller.data
        ):
            if self._attr_is_on != bool(
                (int(self._controller.data["flags"]) & 0x10) == 0x10
            ):
                self._attr_is_on = bool(
                    (int(self._controller.data["flags"]) & 0x10) == 0x10
                )
                self.async_write_ha_state()

    @property
    def icon(self) -> str:
        if self.is_on:
            return "mdi:wind-power"
        return "mdi:wind-power-outline"

    @property
    def available(self) -> bool:
        """Indicates whether the shade is available."""
        return self._available

"""Sensors related to ESPSomfy-RTS-HA"""
from __future__ import annotations

from dataclasses import dataclass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory


from .entity import ESPSomfyEntity
from .controller import ESPSomfyController
from .const import DOMAIN, EVT_ETHERNET, EVT_WIFISTRENGTH, EVT_CONNECTED
from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
    SensorDeviceClass,
    SensorEntityDescription,
)
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfDataRate

)

@dataclass
class ESPSomfyDiagSensorDescription(SensorEntityDescription):
    """A base class descriptor for a sensor entity"""
    id: str | None = None
    events:dict | None = None
    native_value:any | None = None


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up shades for the shade controller."""

    controller = hass.data[DOMAIN][config_entry.entry_id]
    new_entities = []
    data = controller.api.get_config()
    if("chipModel" in data):
        chip_model = "ESP32"
        if(len(data["chipModel"])):
            chip_model += "-"
            chip_model += data["chipModel"]
        new_entities.append(ESPSomfyDiagSensor(controller=controller, cfg=ESPSomfyDiagSensorDescription(
            key="chip_model",
            entity_category=EntityCategory.DIAGNOSTIC,
            name="Chip Type",
            native_value=chip_model.upper(),
            events={},
            icon="mdi:cpu-32-bit"), data=data))
    if("connType" in data):
        new_entities.append(ESPSomfyDiagSensor(controller=controller, cfg=ESPSomfyDiagSensorDescription(
            key="conn_type",
            entity_category=EntityCategory.DIAGNOSTIC,
            name="Connection",
            events={},
            native_value=data["connType"],
            icon="mdi:connection"), data=data))
        if(data["connType"] == "Wifi"):
            new_entities.append(ESPSomfyWifiStrengthSensor(controller, data))
            new_entities.append(ESPSomfyDiagSensor(controller=controller, cfg=ESPSomfyDiagSensorDescription(
                key="wifi_ssid",
                entity_category=EntityCategory.DIAGNOSTIC,
                name="Wifi SSID",
                icon="mdi:wifi-cog",
                events={EVT_WIFISTRENGTH: "ssid"}),
                data=data))
            new_entities.append(ESPSomfyDiagSensor(controller=controller, cfg=ESPSomfyDiagSensorDescription(
                    key="wifi_channel",
                    entity_category=EntityCategory.DIAGNOSTIC,
                    state_class=SensorStateClass.MEASUREMENT,
                    name="Wifi Channel",
                    icon="mdi:radio-tower",
                    events={EVT_WIFISTRENGTH: "channel"}), data=data))
        elif(data["connType"] == "Ethernet"):
            new_entities.append(ESPSomfyDiagSensor(controller=controller, cfg=ESPSomfyDiagSensorDescription(
                key="eth_speed",
                entity_category=EntityCategory.DIAGNOSTIC,
                state_class=SensorStateClass.MEASUREMENT,
                unit_of_measurement=UnitOfDataRate.MEGABYTES_PER_SECOND,
                name="Connection Speed",
                icon="mdi:lan-connect",
                events={EVT_ETHERNET: "speed"}), data=data))
            new_entities.append(ESPSomfyDiagSensor(controller=controller, cfg=ESPSomfyDiagSensorDescription(
                key="eth_full_duplex",
                entity_category=EntityCategory.DIAGNOSTIC,
                name="Full Duplex",
                icon="mdi:sync",
                events={EVT_ETHERNET: "fullduplex"}), data=data))

    new_entities.append(ESPSomfyDiagSensor(controller=controller, cfg=ESPSomfyDiagSensorDescription(
            key="ip_addresss",
            entity_category=EntityCategory.DIAGNOSTIC,
            name="IP Address",
            icon="mdi:ip",
            events={},
            native_value=controller.api.get_data()["host"]), data=data))
    if new_entities:
        async_add_entities(new_entities)

class ESPSomfyDiagSensor(ESPSomfyEntity, SensorEntity):
    """A diagnostic entity for the hub"""
    def __init__(self, controller: ESPSomfyController, cfg: ESPSomfyDiagSensorDescription, data) -> None:
        super().__init__(controller=controller, data=data)
        self._controller = controller
        self._available = True
        self.events = {}

        self._attr_entity_category = cfg.entity_category
        self._attr_unique_id = f"{cfg.key}_{controller.unique_id}"
        self._attr_name = cfg.name
        self._attr_device_class = cfg.device_class
        self._attr_native_unit_of_measurement = cfg.unit_of_measurement
        self._attr_state_class = cfg.state_class
        self.events = cfg.events
        self._attr_icon = cfg.icon
        self._attr_native_value = cfg.native_value

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator"""
        if("event" in self._controller.data and self._controller.data["event"] in self.events):
            evt = self.events[self._controller.data["event"]]
            if(evt in self._controller.data):
                self._attr_native_value = self._controller.data[evt]
                self.async_write_ha_state()
        elif(self._controller.data["event"] == EVT_CONNECTED and "connected" in self._controller.data):
            self._available = bool(self._controller.data["connected"])
            self.async_write_ha_state()


    @property
    def available(self) -> bool:
        """Indicates whether the sensor is available"""
        return self._available

    @property
    def should_poll(self) -> bool:
        return False


class ESPSomfyWifiStrengthSensor(ESPSomfyDiagSensor):
    """A wifi strength sensor indicating the current connection strength"""

    def __init__(self, controller: ESPSomfyController, data) -> None:
        """Initialize a new SunSensor"""
        super().__init__(controller=controller, cfg=ESPSomfyDiagSensorDescription(
            key="wifi_sensor",
            device_class=SensorDeviceClass.SIGNAL_STRENGTH,
            entity_category=EntityCategory.DIAGNOSTIC,
            unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
            state_class=SensorStateClass.MEASUREMENT,
            name="Wifi Strength",
            icon="mdi:wifi",
            events={EVT_WIFISTRENGTH: "strength"}
        ), data=data)
        self._available = True

    @property
    def should_poll(self) -> bool:
        return False



"""Support for ESPSomfy RTS device actions."""
from __future__ import annotations
from typing import Any, cast
from dataclasses import dataclass
from collections.abc import Iterable

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, EVT_CONNECTED, API_REBOOT
from .controller import ESPSomfyController
from .__init__ import ESPSomfyRTSEntityFeature
from .entity import ESPSomfyEntity
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity import EntityCategory
from packaging.version import parse as version_parse

SVC_REBOOT = "reboot"
SVC_BACKUP = "backup"

@dataclass
class ESPSomfyButtonDescriptionMixin:
    """Mixin for entity description"""

@dataclass
class ESPSomfyButtonDescription(ButtonEntityDescription, ESPSomfyButtonDescriptionMixin):
    """A base class descriptor for a button entity"""
    id: str | None = None
    events:dict | None = None
    action:dict | None = None
    features: Iterable[int] | None = None


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ESPSomfy RTS update based on a config entry."""
    new_entities = []
    controller:ESPSomfyController = hass.data[DOMAIN][config_entry.entry_id]
    v = version_parse(controller.version)
    if(v.major >= 2 and v.minor >= 3 and v.micro >= 0):
        new_entities.append(ESPSomfyButton(controller=controller, cfg=ESPSomfyButtonDescription(
            key="reboot",
            entity_category=EntityCategory.CONFIG,
            name="Reboot ESP Device",
            device_class=ButtonDeviceClass.RESTART,
            events={},
            action={"service": API_REBOOT},
            features = 1,
            icon="mdi:restart")))
    if(v.major >= 1):
        new_entities.append(ESPSomfyButton(controller=controller, cfg=ESPSomfyButtonDescription(
        key="backup",
        entity_category=EntityCategory.CONFIG,
        name="Backup ESPSomfy RTS",
        device_class=ButtonDeviceClass.IDENTIFY,
        events={},
        action={"apimethod": "create_backup"},
        features=2,
        icon="mdi:download")))
    async_add_entities(new_entities)
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(name=SVC_REBOOT, schema={}, func="async_press", required_features=[ESPSomfyRTSEntityFeature.REBOOT])
    platform.async_register_entity_service(name=SVC_BACKUP, schema={}, func="async_press", required_features=[ESPSomfyRTSEntityFeature.BACKUP])



class ESPSomfyButton(ESPSomfyEntity, ButtonEntity):
    """Defines a reboot entity"""
    _attr_device_class = ButtonDeviceClass.RESTART
    def __init__(self, controller: ESPSomfyController, cfg:ESPSomfyButtonDescription) -> None:
        """Initialize the reboot entity."""
        self._controller = controller
        self._attr_device_class = cfg.device_class
        self._attr_name = cfg.name
        self._attr_unique_id = f"{cfg.key}_{controller.unique_id}"
        self._attr_entity_category = cfg.entity_category
        self._attr_icon = cfg.icon
        self._available = True
        self._action = cfg.action

        self._attr_supported_features = cfg.features
        super().__init__(controller=controller, data=None)

    async def async_press(self) -> None:
        """Process the reboot"""
        data = None
        if("data" in self._action):
            data = self._action["data"]
        if("service" in self._action):
            await self._controller.api.put_command(self._action["service"], data)
        elif("apimethod" in self._action):
            method = getattr(self._controller.api, self._action["apimethod"])
            await method()

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if(self._controller.data["event"] == EVT_CONNECTED and "connected" in self._controller.data):
            self._available = bool(self._controller.data["connected"])
            self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Indicates whether the shade is available"""
        return self._available

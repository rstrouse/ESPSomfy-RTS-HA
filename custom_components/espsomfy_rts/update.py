"""Support for ESPSomfy RTS updates."""
from __future__ import annotations
from typing import Any, cast

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, EVT_FWSTATUS, EVT_UPDPROGRESS
from .controller import ESPSomfyController
from .entity import ESPSomfyEntity



async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ESPSomfy RTS update based on a config entry."""
    controller:ESPSomfyController = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([ESPSomfyRTSUpdateEntity(controller)])


class ESPSomfyRTSUpdateEntity(ESPSomfyEntity, UpdateEntity):
    """Defines an ESPSomfy RTS update entity."""

    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_supported_features = UpdateEntityFeature.SPECIFIC_VERSION | UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS
    _attr_title = "ESPSomfy RTS"

    def __init__(self, controller: ESPSomfyController) -> None:
        """Initialize the update entity."""
        self._controller = controller
        self._attr_name = f"Firmware Update"
        self._attr_unique_id = f"update_{controller.unique_id}"
        self._update_status = 0
        self._fw_progress = 100
        self._app_progress = 100
        self._total_progress = 100
        if controller.can_update:
            self._attr_supported_features = (
                UpdateEntityFeature.INSTALL | UpdateEntityFeature.SPECIFIC_VERSION | UpdateEntityFeature.PROGRESS | UpdateEntityFeature.BACKUP
            )

        super().__init__(controller=controller, data=None)

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if(self._controller.data["event"] == EVT_FWSTATUS):
            if self._controller.can_update:
                self._attr_supported_features = (
                    UpdateEntityFeature.INSTALL | UpdateEntityFeature.SPECIFIC_VERSION | UpdateEntityFeature.PROGRESS | UpdateEntityFeature.BACKUP
                )
            else:
                self._attr_supported_features = UpdateEntityFeature.SPECIFIC_VERSION | UpdateEntityFeature.PROGRESS
            self.async_write_ha_state()
        elif(self.controller.data["event"] == EVT_UPDPROGRESS):
            d = self.controller.data
            if "part" in d:
                if int(d["part"]) == 0:
                    self._app_progress = 0
                    self._fw_progress = (int(d["loaded"])/int(d["total"])) * 100
                elif int(d["part"]) == 100:
                    self._fw_progress = 100
                    self._app_progress = (int(d["loaded"])/int(d["total"])) * 100
                self._total_progress = int((self._fw_progress + self._app_progress)/ 2)
                self.async_write_ha_state()
    @property
    def can_install(self) -> bool:
        """Indicates whether the current version supports firmware installation"""


    @property
    def installed_version(self) -> str | None:
        """Version currently installed and in use."""
        if (version := self.coordinator.version) is None:
            return None
        return str(version)

    @property
    def latest_version(self) -> str | None:
        """Latest version available for install."""
        if(latest := self.coordinator.latest_version) is None:
            return None
        return str(latest)

    @property
    def in_progress(self) -> bool | int | None:
        """Update installation progress."""
        if self._total_progress < 100:
            return self._total_progress
        return False

    @property
    def release_url(self) -> str | None:
        """URL to the full release notes of the latest version available."""
        if (version := self.latest_version) is None:
            return None
        return f"https://github.com/rstrouse/ESPSomfy-RTS/releases/tag/{version}"

    async def async_install(
        self, version: str | None, backup: bool, **kwargs: Any
    ) -> None:
        """Install an update."""
        success = True
        if backup:
            success = await self._controller.create_backup()
        if success:
            # We cast here, we know that the latest_version is supposed to be a string.
            version = cast(str, self.latest_version)
            if version is not None:
                await self.controller.update_firmware(version)

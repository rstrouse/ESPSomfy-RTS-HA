"""ESPSomfy parent entity class."""
from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo, Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .controller import ESPSomfyController


class ESPSomfyEntity(CoordinatorEntity[ESPSomfyController], Entity):
    """Base entitly for the ESPSomfy controller."""

    def __init__(self, *, data: any, controller: ESPSomfyController) -> None:
        """Initialize the entity."""
        super().__init__(controller)

        self.controller = controller

    @property
    def should_poll(self) -> bool:
        return False

    @property
    def device_info(self) -> DeviceInfo | None:
        """Device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.controller.unique_id)},
            name="ESPSomfy RTS",
            manufacturer=MANUFACTURER,
            model=self.controller.model,
            sw_version=self.controller.version,
        )

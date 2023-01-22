"""Support for ESPSomfy RTS Shades."""
from __future__ import annotations

from typing import Any
import voluptuous as vol


from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback


from .const import DOMAIN, EVT_CONNECTED, EVT_SHADEREMOVED, EVT_SHADESTATE
from .controller import ESPSomfyController
from .entity import ESPSomfyEntity

SVC_OPEN_SHADE = "open_shade"
SVC_CLOSE_SHADE = "close_shade"
SVC_STOP_SHADE = "stop_shade"
SVC_SET_SHADE_POS = "set_shade_position"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up shades for the shade controller."""
    controller = hass.data[DOMAIN][config_entry.entry_id]
    new_shades = []
    for shade in controller.api.shades:
        try:
            new_shades.append(ESPSomfyShade(controller, shade))
        except KeyError:
            pass
    if new_shades:
        async_add_entities(new_shades)

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SVC_SET_SHADE_POS,
        {vol.Required(ATTR_POSITION): cv.string},
        "async_set_cover_position",
    )
    platform.async_register_entity_service(SVC_OPEN_SHADE, {}, "async_open_cover")
    platform.async_register_entity_service(SVC_CLOSE_SHADE, {}, "async_close_cover")
    platform.async_register_entity_service(SVC_STOP_SHADE, {}, "async_stop_cover")


class ESPSomfyShade(ESPSomfyEntity, CoverEntity):
    """A shade that is associated with a controller"""

    def __init__(self, controller: ESPSomfyController, data):
        super().__init__(controller=controller)
        self._controller = controller
        self._shade_id = data["shadeId"]
        self._position = data["position"]
        self._attr_unique_id = f"{controller.unique_id}_{self._shade_id}"
        self._attr_name = data["name"]
        self._direction = 0
        self._available = True

        self._attr_device_class = CoverDeviceClass.SHADE
        self._attr_supported_features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.STOP
            | CoverEntityFeature.SET_POSITION
        )

        self._attr_is_closed: bool = False
        # print(f"Set up shade {self._attr_unique_id} - {self._attr_name}")

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if "shadeId" in self._controller.data:
            if self._controller.data["shadeId"] == self._shade_id:
                if self._controller.data["event"] == EVT_SHADESTATE:
                    if "position" in self._controller.data:
                        self._position = int(self._controller.data["position"])
                    if "direction" in self._controller.data:
                        self._direction = int(self._controller.data["direction"])
                    self._available = True
                elif self._controller.data["event"] == EVT_SHADEREMOVED:
                    self._available = False
                self.async_write_ha_state()
        elif (
            self._controller.data["event"] == EVT_CONNECTED
            and not self._controller.data["connected"]
        ):
            self._available = False
            self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Indicates whether the shade is available"""
        return self._available

    @property
    def should_poll(self) -> bool:
        """Indicates whether the shade should poll for information"""
        return False

    @property
    def current_cover_position(self) -> int:
        """Return the current position of the shade."""
        return 100 - self._position

    @property
    def is_opening(self) -> bool:
        """Return true if cover is opening."""
        return self._direction == -1

    @property
    def is_closing(self) -> bool:
        """Return true if cover is closing."""
        return self._direction == 1

    @property
    def is_closed(self) -> bool:
        """Return true if cover is closed."""
        return self._position == 100

    @property
    def is_open(self) -> bool:
        """Return true if cover is closed."""
        return self._position == 0

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Set the cover position."""
        await self._controller.api.position_shade(
            self._shade_id, 100 - kwargs[ATTR_POSITION]
        )

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        # print(f"Opening Cover id#{self._shade_id}")
        await self._controller.api.open_shade(self._shade_id)

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close cover."""
        # print(f"Closing Cover id#{self._shade_id}")
        await self._controller.api.close_shade(self._shade_id)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Hold cover."""
        # print(f"Stopping Cover id#{self._shade_id}")
        await self._controller.api.stop_shade(self._shade_id)

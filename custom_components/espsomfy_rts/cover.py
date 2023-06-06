"""Support for ESPSomfy RTS Shades and Blinds."""
from __future__ import annotations

from typing import Any, Final
import voluptuous as vol

from homeassistant.components.cover import (
    ATTR_POSITION,
    ATTR_TILT_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.config_validation import make_entity_service_schema
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback


from .const import DOMAIN, EVT_CONNECTED, EVT_SHADEREMOVED, EVT_SHADESTATE
from .controller import ESPSomfyController
from .entity import ESPSomfyEntity
from .switch import ESPSomfySunSwitch

SVC_OPEN_SHADE = "open_shade"
SVC_CLOSE_SHADE = "close_shade"
SVC_STOP_SHADE = "stop_shade"
SVC_SET_SHADE_POS = "set_shade_position"
SVC_TILT_OPEN = "tilt_open"
SVC_TILT_CLOSE = "tilt_close"
SVC_SET_TILT_POS = "set_tilt_position"

POSITION_SERVICE_SCHEMA: Final = make_entity_service_schema(
    {vol.Required(ATTR_POSITION): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=100)
            )}
)
TILT_POSITION_SERVICE_SCHEMA: Final = make_entity_service_schema(
    {vol.Required(ATTR_TILT_POSITION): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=100)
            )}
)



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
            if "shadeType" in shade:
                match(shade["shadeType"]):
                    case 3:
                        new_shades.append(ESPSomfySunSwitch(controller, shade))

        except KeyError:
            pass
    if new_shades:
        async_add_entities(new_shades)

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SVC_SET_SHADE_POS,
        POSITION_SERVICE_SCHEMA,
        "async_set_cover_position",
    )
    platform.async_register_entity_service(
        SVC_SET_TILT_POS,
        TILT_POSITION_SERVICE_SCHEMA,
        "async_set_cover_tilt_position",
    )
    platform.async_register_entity_service(SVC_OPEN_SHADE, {}, "async_open_cover")
    platform.async_register_entity_service(SVC_CLOSE_SHADE, {}, "async_close_cover")
    platform.async_register_entity_service(SVC_STOP_SHADE, {}, "async_stop_cover")
    platform.async_register_entity_service(SVC_TILT_OPEN, {}, "async_tilt_open")
    platform.async_register_entity_service(SVC_TILT_CLOSE, {}, "async_tilt_close")



class ESPSomfyShade(ESPSomfyEntity, CoverEntity):
    """A shade that is associated with a controller"""

    def __init__(self, controller: ESPSomfyController, data):
        super().__init__(controller=controller)
        self._controller = controller
        self._shade_id = data["shadeId"]
        self._position = data["position"]
        self._tilt_postition = 100
        self._tilt_direction = 0
        self._attr_unique_id = f"{controller.unique_id}_{self._shade_id}"
        self._attr_name = data["name"]
        self._direction = 0
        self._available = True
        self._has_tilt = False

        self._attr_device_class = CoverDeviceClass.SHADE
        self._attr_supported_features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.STOP
            | CoverEntityFeature.SET_POSITION
        )
        if "hasTilt" in data and data["hasTilt"] is True:
            self._attr_supported_features |= (
                CoverEntityFeature.OPEN_TILT
                | CoverEntityFeature.CLOSE_TILT
                | CoverEntityFeature.SET_TILT_POSITION
            )
            self._has_tilt = True
            self._tilt_postition = data["tiltPosition"] if "tiltPosition" in data else 100
            self._tilt_direction = data["tiltDirection"] if "tiltDirecion" in data else 0
        if "tiltType" in data:
            match int(data["tiltType"]):
                case 1 | 2 | 3:
                    self._has_tilt = True
                    self._attr_supported_features |= (
                        CoverEntityFeature.OPEN_TILT
                        | CoverEntityFeature.CLOSE_TILT
                        | CoverEntityFeature.SET_TILT_POSITION
                    )
        if "shadeType" in data:
            match int(data["shadeType"]):
                case 1:
                    self._attr_device_class = CoverDeviceClass.BLIND
                case 2:
                    self._attr_device_class = CoverDeviceClass.CURTAIN
                case 3:
                    self._attr_device_class = CoverDeviceClass.AWNING
                case _:
                    self._attr_device_class = CoverDeviceClass.SHADE


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
                    if "hasTilt" in self._controller.data:
                        self._has_tilt = self._controller.data["hasTilt"]
                    if "tiltType" in self._controller.data:
                        match int(self._controller.data["tiltType"]):
                            case 1 | 2 | 3:
                                self._has_tilt = True
                            case _:
                                self._has_tilt = False
                    if self._has_tilt is True:
                        if "tiltDirection" in self._controller.data:
                            self._tilt_direction = int(self._controller.data["tiltDirection"])
                        if "tiltPosition" in self._controller.data:
                            self._tilt_postition = int(self._controller.data["tiltPosition"])
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
    def icon(self) -> str:
        if hasattr(self, "_attr_icon"):
            return self._attr_icon
        if hasattr(self, "entity_description"):
            return self.entity_description.icon
        if self._attr_device_class == CoverDeviceClass.AWNING:
            if self.is_closed:
                return "mdi:storefront-outline"
            return "mdi:storefront"
        return None


    @property
    def current_cover_position(self) -> int | None:
        """Return the current position of the shade."""
        if self._attr_device_class == CoverDeviceClass.AWNING:
            return self._position
        return 100 - self._position

    @property
    def current_cover_tilt_position(self) -> int | None:
        """Return current position of cover tilt. 0 is closed, 100 is open."""
        if not self._has_tilt:
            return None
        return 100 - self._tilt_postition

    @property
    def is_opening(self) -> bool:
        """Return true if cover is opening."""
        if self._attr_device_class == CoverDeviceClass.AWNING:
            return self._direction == 1
        return self._direction == -1

    @property
    def is_closing(self) -> bool:
        """Return true if cover is closing."""
        if self._attr_device_class == CoverDeviceClass.AWNING:
            return self._direction == -1
        return self._direction == 1

    @property
    def is_closed(self) -> bool:
        """Return true if cover is closed."""
        if self._attr_device_class == CoverDeviceClass.AWNING:
            return self._position == 0
        return self._position == 100

    @property
    def is_open(self) -> bool:
        """Return true if cover is closed."""
        if self._attr_device_class == CoverDeviceClass.AWNING:
            return self._position == 100
        return self._position == 0

    async def async_set_cover_tilt_position(self, **kwargs: Any) -> None:
        """Set the tilt postion"""
        await self._controller.api.position_tilt(
            self._shade_id, 100 - int(kwargs[ATTR_TILT_POSITION])
        )
    async def async_open_cover_tilt(self, **kwargs: Any) -> None:
        """Open the tilt position"""
        await self._controller.api.tilt_open(self._shade_id)

    async def async_close_cover_tilt(self, **kwargs: Any) -> None:
        """Close the tilt position"""
        await self._controller.api.tilt_close(self._shade_id)

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Set the cover position."""
        if self._attr_device_class == CoverDeviceClass.AWNING:
            await self._controller.api.position_shade(
                self._shade_id, int(kwargs[ATTR_POSITION])
            )
        else:
            await self._controller.api.position_shade(
                self._shade_id, 100 - int(kwargs[ATTR_POSITION])
            )

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        # print(f"Opening Cover id#{self._shade_id}")
        # This is ridiculous in that we need to invert these
        # if the type is an awning.
        if self._attr_device_class == CoverDeviceClass.AWNING:
            await self._controller.api.close_shade(self._shade_id)
        else:
            await self._controller.api.open_shade(self._shade_id)

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close cover."""
        # print(f"Closing Cover id#{self._shade_id}")
        if self._attr_device_class == CoverDeviceClass.AWNING:
            await self._controller.api.open_shade(self._shade_id)
        else:
            await self._controller.api.close_shade(self._shade_id)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Hold cover."""
        # print(f"Stopping Cover id#{self._shade_id}")
        await self._controller.api.stop_shade(self._shade_id)

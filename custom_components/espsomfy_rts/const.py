"""Constants for the ESPSomfy RTS integration."""

from homeassistant.const import Platform


VERSION = "v2.4.2"
DOMAIN = "espsomfy_rts"
MANUFACTURER = "rstrouse"
API_CONTROLLER = "/controller"
API_SHADES = "/shades"
API_GROUPS = "/groups"
API_SHADECOMMAND = "/shadeCommand"
API_GROUPCOMMAND = "/groupCommand"
API_TILTCOMMAND = "/tiltCommand"
API_DISCOVERY = "/discovery"
API_LOGIN = "/login"
API_SETPOSITIONS = "/setPositions"
API_SETSENSOR = "/setSensor"
API_BACKUP = "/backup"
API_REBOOT = "/reboot"
API_RESTORE = "/restore"
EVT_CONTROLLER = "controller"
EVT_SHADESTATE = "shadeState"
EVT_GROUPSTATE = "groupState"
EVT_SHADECOMMAND = "shadeCommand"
EVT_SHADEADDED = "shadeAdded"
EVT_SHADEREMOVED = "shadeRemoved"
EVT_CONNECTED = "connected"
EVT_FWSTATUS = "fwStatus"
EVT_UPDPROGRESS = "updateProgress"
EVT_WIFISTRENGTH = "wifiStrength"
EVT_ETHERNET = "ethernet"

ATTR_RESTOREFILE = "Restore File"

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.COVER,
    Platform.SWITCH,
    Platform.UPDATE,
    Platform.SENSOR,
    Platform.BUTTON
]

"""Controller for all the devices"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from threading import Timer
from typing import Any

import aiohttp
import websocket


from homeassistant.components.cover import CoverDeviceClass, CoverEntityFeature
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import aiohttp_client, device_registry, entity_registry
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_registry import async_entries_for_config_entry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    API_DISCOVERY,
    API_SHADECOMMAND,
    API_TILTCOMMAND,
    API_SHADES,
    DOMAIN,
    EVT_CONNECTED,
    EVT_SHADEADDED,
    EVT_SHADEREMOVED,
    EVT_SHADESTATE,
)

_LOGGER = logging.getLogger(__name__)


class SocketListener(threading.Thread):
    """A listener of sockets."""

    def __init__(
        self, hass: HomeAssistant, url: str, onpacket, onopen, onclose, onerror
    ) -> None:
        """Initialize a new socket listener"""
        super().__init__()
        self.url = url
        self.onpacket = onpacket
        self.onopen = onopen
        self.onclose = onclose
        self.onerror = onerror
        self.connected = False
        self.main_loop = None
        self.ws_app = None
        self.hass = hass
        self._should_stop = False
        self.filter = None
        self.running_future = None
        self.reconnects = 0

    def __enter__(self):
        """Start the thread."""
        self.start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop and join the thread."""
        self.stop()

    def stop(self):
        """Cancel event stream and join the thread."""
        _LOGGER.debug("Stopping event thread")
        self._should_stop = True
        if self.ws_app and self.connected:
            self.ws_app.close()

        _LOGGER.debug("Joining event thread")
        if self.is_alive():
            self.join()
        _LOGGER.debug("Event thread joined")
        print("Event thread joined")

    async def connect(self):
        """Start up the web socket"""
        self.main_loop = asyncio.get_event_loop()
        self.ws_app = websocket.WebSocketApp(
            self.url,
            on_message=self.ws_onmessage,
            on_error=self.ws_onerror,
            on_close=self.ws_onclose,
            keep_running=True,
        )
        self.main_loop.run_in_executor(None, self.ws_begin)

    def reconnect(self):
        """Reconnect to the web socket"""
        self.reconnects = self.reconnects + 1
        self.main_loop = asyncio.get_event_loop()
        try:
            self.ws_app = websocket.WebSocketApp(
                self.url,
                on_message=self.ws_onmessage,
                on_error=self.ws_onerror,
                on_close=self.ws_onclose,
                keep_running=True,
            )
            self.main_loop.run_in_executor(None, self.ws_begin)
        except websocket.WebSocketAddressException:
            Timer(min(10 * self.reconnects / 2, 20), self.reconnect)

    def set_filter(self, arr: Any) -> None:
        """Sets the filter for the events"""
        self.filter = arr.copy()

    def close(self) -> None:
        """Synonym for stop."""
        self.stop()
    def ws_begin(self) -> None:
        """Begin running the thread"""
        self.running_future = self.ws_app.run_forever(ping_interval=25, ping_timeout=20)
        # print("Fell out of run_runforever")
        if not self._should_stop:
            self.hass.loop.call_soon_threadsafe(self.reconnect)
    def ws_onerror(self, wsapp, exception):
        """An error occurred on the socket connection"""
        # print(f"We have an error {exception}")
        self.hass.loop.call_soon_threadsafe(self.onerror, exception)

    def ws_onclose(self, wsapp, status, msg):
        """The socket has been closed"""
        # print(f"The socket was closed {status}")
        self.connected = False
        if not self._should_stop:
            self.hass.loop.call_soon_threadsafe(self.onclose)

    def ws_onmessage(self, wsapp, message: str):
        """Process the incoming message"""
        if message.startswith("42["):
            ndx = message.find(",")
            event = message[3:ndx]
            if not self.filter or event in self.filter:
                payload = message[ndx + 1 : -1]
                # print(f"Event:{event} Payload:{payload}")
                data = json.loads(payload)
                data["event"] = event
                self.hass.loop.call_soon_threadsafe(self.onpacket, data)
        else:
            if message.lower() == "connected":
                self.hass.loop.call_soon_threadsafe(self.onopen)
                self.reconnects = 0
                self.connected = True


class ESPSomfyController(DataUpdateCoordinator):
    """Data coordinator/controller for receiving from ESPSomfy_RTS."""

    def __init__(self, config_entry_id, hass: HomeAssistant, api: ESPSomfyAPI) -> None:
        """Initialize data coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name=DOMAIN,
        )
        self.config_entry_id = config_entry_id
        self.api = api
        self.ws_listener = None

    @property
    def server_id(self) -> str:
        """Gets the server id from the api"""
        return self.api.server_id

    @property
    def unique_id(self) -> str:
        """Gets a unique id for the controller"""
        return f"espsomfy_{self.server_id}"

    @property
    def model(self) -> str:
        """Gets the model for the controller"""
        return self.api.model

    @property
    def version(self) -> str:
        """Gets the current version for the controller"""
        return self.api.version

    async def ws_close(self) -> None:
        """Closes the tasks and sockets"""
        if not self.ws_listener is None:
            print("closing ESPSomfyRTS listener")
            self.ws_listener.close()
        return

    async def ws_connect(self):
        """Method to connect to WebSocket"""
        if not self.ws_listener is None:
            self.ws_listener.close()
        self.ws_listener = SocketListener(
            self.hass,
            self.api.get_sock_url(),
            self.ws_onpacket,
            self.ws_onopen,
            self.ws_onclose,
            self.ws_onerror,
        )
        self.ws_listener.set_filter(
            [EVT_CONNECTED, EVT_SHADEADDED, EVT_SHADEREMOVED, EVT_SHADESTATE]
        )
        await self.ws_listener.connect()

    def ensure_shade_configured(self, data):
        """Ensures the shade exists on Home Assistant"""
        uuid = f"{self.unique_id}_{data['shadeId']}"
        devices = device_registry.async_get(self.hass)
        device = devices.async_get_device({(DOMAIN, self.unique_id)})

        entities = entity_registry.async_get(self.hass)

        for entity in async_entries_for_config_entry(entities, self.config_entry_id):
            if entity.unique_id == uuid:
                return
        dev_features = (CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.STOP
            | CoverEntityFeature.SET_POSITION)

        dev_class = CoverDeviceClass.SHADE
        if "shadeType" in data:
            match int(data["shadeType"]):
                case 1:
                    dev_class = CoverDeviceClass.BLIND
                    if "tiltType" in data:
                        match int(data["tiltType"]):
                            case 1 | 2:
                                dev_features |= (CoverEntityFeature.OPEN_TILT | CoverEntityFeature.CLOSE_TILT | CoverEntityFeature.SET_TILT_POSITION)
                    else:
                        if "hasTilt" in data and data["hasTilt"] is True:
                            dev_features |= (CoverEntityFeature.OPEN_TILT | CoverEntityFeature.CLOSE_TILT | CoverEntityFeature.SET_TILT_POSITION)
                case 2:
                    dev_class = CoverDeviceClass.CURTAIN
                case _:
                    dev_class = CoverDeviceClass.SHADE


        # Reload all the shades
        # self.api.load_shades()
        # I have no idea whether this reloads the devices or not.
        entities.async_get_or_create(
            domain=DOMAIN,
            platform=Platform.COVER,
            original_device_class=dev_class,
            unique_id=uuid,
            device_id=device.id,
            original_name=data["name"],
            suggested_object_id=f"{str(data['name']).lower().replace(' ', '_')}",
            supported_features=dev_features,
        )
        print(f"Shade not found {uuid} and one was added")

    def ws_onpacket(self, data):
        """Packet from the websocket"""
        # Below doesn't work.  Near as I can tell there is no
        # real way of adding an entity on the fly.  All this
        # does is add an entity that is not really attached.
        # if data["event"] == EVT_SHADEADDED:
        #    self.ensure_shade_configured(data)
        self.async_set_updated_data(data=data)

    def ws_onopen(self):
        """Callback when the websocket is opened"""
        # print("Websocket is connected")
        data = {"event": EVT_CONNECTED, "connected": True}
        self.async_set_updated_data(data)

    def ws_onerror(self, exception):
        """An error occurred on the socket connection"""
        # print(exception)
        data = {"event": EVT_CONNECTED, "connected": False}
        self.async_set_updated_data(data)

    def ws_onclose(self):
        """The socket has been closed"""
        # print("Websocket closed")
        data = {"event": EVT_CONNECTED, "connected": False}
        self.async_set_updated_data(data)


class ESPSomfyAPI:
    """API for sending data to nodejs-PoolController"""

    def __init__(self, hass: HomeAssistant, data) -> None:
        self.hass = hass
        self.data = data
        self._host = data[CONF_HOST]
        self._sock_url = f"ws://{self._host}:8080"
        self._api_url = f"http://{self._host}:8081"
        self._config: Any = {}
        self._session = async_get_clientsession(self.hass, verify_ssl=False)

    @property
    def shades(self) -> Any:
        """Return the state attributes."""
        return self._config["shades"]

    @property
    def server_id(self) -> str:
        """Getter for the server id"""
        return self._config["serverId"]

    @property
    def version(self) -> str:
        """Getter for the api version"""
        return self._config["version"]

    @property
    def model(self) -> str:
        """Getter for the model number"""
        return self._config["model"]

    def get_sock_url(self):
        """Get the socket interface url"""
        return self._sock_url

    def get_api_url(self):
        """Get that url used for api reference"""
        return self._api_url

    def get_config(self):
        """Return the initial config"""
        return self._config

    async def discover(self) -> Any | None:
        """Discover the device on the network"""
        url = f"{self._api_url}{API_DISCOVERY}"
        async with self._session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                self._config["serverId"] = data["serverId"]
                self._config["version"] = data["version"]
                self._config["model"] = data["model"]
                self._config["shades"] = data["shades"]
                return await resp.json()
            _LOGGER.error(await resp.text())
            raise DiscoveryError(f"{url} - {await resp.text()}")

    async def load_shades(self) -> Any | None:
        """Loads all the shades from the controller"""
        async with self._session.get(f"{self._api_url}{API_SHADES}") as resp:
            if resp.status == 200:
                self._config["shades"] = await resp.json()
                return self._config["shades"]
            else:
                _LOGGER.error(await resp.text())

    async def tilt_open(self, shade_id: int):
        """Send the command to open the tilt"""
        await self.tilt_command({"shadeId": shade_id, "command": "up"})

    async def tilt_close(self, shade_id: int):
        """Send the command to close the tilt"""
        await self.tilt_command({"shadeId": shade_id, "command": "down"})

    async def position_tilt(self, shade_id: int, position: int):
        """Send the command to position the shade"""
        # print(f"Setting tilt position to {position}")
        await self.tilt_command({"shadeId": shade_id, "target": position})

    async def open_shade(self, shade_id: int):
        """Send the command to open the shade"""
        await self.shade_command({"shadeId": shade_id, "command": "up"})

    async def close_shade(self, shade_id: int):
        """Send the command to close the shade"""
        await self.shade_command({"shadeId": shade_id, "command": "down"})

    async def stop_shade(self, shade_id: int):
        """Send the command to stop the shade"""
        await self.shade_command({"shadeId": shade_id, "command": "my"})

    async def position_shade(self, shade_id: int, position: int):
        """Send the command to position the shade"""
        await self.shade_command({"shadeId": shade_id, "target": position})

    async def shade_command(self, data):
        """Send commands to ESPSomfyRTS via PUT request"""
        async with self._session.put(
            f"{self._api_url}{API_SHADECOMMAND}", json=data
        ) as resp:
            if resp.status == 200:
                pass
            else:
                _LOGGER.error(await resp.text())

    async def tilt_command(self, data):
        """Send commands to ESPSomfyRTS via PUT request"""
        async with self._session.put(
            f"{self._api_url}{API_TILTCOMMAND}", json=data
        ) as resp:
            if resp.status == 200:
                pass
            else:
                _LOGGER.error(await resp.text())

    async def get_initial(self):
        """Get the initial config from nodejs-PoolController."""
        try:
            self._session = aiohttp_client.async_get_clientsession(self.hass)
            async with self._session.get(f"{self._api_url}{API_DISCOVERY}") as resp:
                if resp.status == 200:
                    self._config = await resp.json()
                else:
                    _LOGGER.error(await resp.text())
        except aiohttp.ClientError:
            pass


class InvalidHost(HomeAssistantError):
    """Error to indicate that hostname/IP address is invalid."""


class DiscoveryError(HomeAssistantError):
    """Error that occurred during discovery"""

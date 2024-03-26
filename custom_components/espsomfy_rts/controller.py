"""Controller for all the devices"""
from __future__ import annotations

import asyncio
from enum import IntFlag
import json
import logging
import threading
import os
from datetime import datetime
from threading import Timer
from typing import Any

import aiohttp
import websocket
import re
from packaging.version import Version, parse as version_parse

from homeassistant.components.cover import CoverDeviceClass, CoverEntityFeature
from homeassistant.const import (
    CONF_HOST,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_PIN,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import aiohttp_client, device_registry, entity_registry
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_registry import async_entries_for_config_entry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    API_LOGIN,
    API_DISCOVERY,
    API_SHADECOMMAND,
    API_GROUPCOMMAND,
    API_TILTCOMMAND,
    API_SHADES,
    API_GROUPS,
    API_SETPOSITIONS,
    API_SETSENSOR,
    DOMAIN,
    EVT_CONNECTED,
    EVT_SHADEADDED,
    EVT_SHADEREMOVED,
    EVT_SHADESTATE,
    EVT_GROUPSTATE,
    EVT_SHADECOMMAND,
    EVT_FWSTATUS,
    EVT_UPDPROGRESS,
    EVT_WIFISTRENGTH,
    EVT_ETHERNET,
    PLATFORMS,

)

_LOGGER = logging.getLogger(__name__)
logging.getLogger("websocket").setLevel(logging.CRITICAL)

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
        self._connect_timer = None

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
        if self.ws_app: # and self.connected:
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
            on_open=self.ws_onopen,
            keep_running=True,
        )
        self.main_loop.run_in_executor(None, self.ws_begin)

    def reconnect(self):
        """Reconnect to the web socket"""
        if(self._connect_timer != None):
            self._connect_timer.cancel()
        self.reconnects = self.reconnects + 1
        self.main_loop = asyncio.get_event_loop()
        try:
            self.ws_app = websocket.WebSocketApp(
                self.url,
                on_message=self.ws_onmessage,
                on_error=self.ws_onerror,
                on_close=self.ws_onclose,
                on_open=self.ws_onopen,
                keep_running=True,
            )
            self.main_loop.run_in_executor(None, self.ws_begin)
            self._connect_timer = None
            self.connected = True

        except websocket.WebSocketAddressException:
            self._connect_timer = Timer(min(10 * self.reconnects / 2, 20), self.reconnect)
            self._connect_timer.start()
        except websocket.WebSocketTimeoutException:
            self._connect_timer = Timer(min(10 * self.reconnects / 2, 20), self.reconnect)
            self._connect_timer.start()
        except websocket.WebSocketConnectionClosedException:
            self._connect_timer = Timer(min(10 * self.reconnects / 2, 20), self.reconnect)
            self._connect_timer.start()

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
    def ws_onopen(self, wsapp):
        """The socket was opened"""
        self.connected = True
        self.hass.loop.call_soon_threadsafe(self.onopen)

    def ws_onmessage(self, wsapp, message: str):
        """Process the incoming message"""
        try:
            if message is None:
                _LOGGER.debug("Got an empty socket payload")
            elif message.startswith("42["):
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
                    self.reconnects = 0
                    self.connected = True
        except Exception as e:
            _LOGGER.debug(e.message)
            raise e


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
    def device_name(self) ->str:
        """Gets the device name from the host"""
        return self.api.deviceName

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

    @property
    def latest_version(self) -> str:
        """Gets the current version for the controller"""
        return self.api.latest_version
    @property
    def check_for_update(self) -> bool:
        """Indicates whether the firmware should check for updates"""
        return self.api.check_for_update

    @property
    def internet_available(self) -> bool:
        """Indicates whether the firmware should check for updates"""
        return self.api.internet_available

    @property
    def can_update(self) -> bool:
        """Gets a flag that indicates whether the firmware can be updated"""
        return self.api.can_update

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
            [EVT_CONNECTED, EVT_SHADEADDED, EVT_SHADEREMOVED, EVT_SHADESTATE, EVT_SHADECOMMAND, EVT_GROUPSTATE, EVT_FWSTATUS, EVT_UPDPROGRESS, EVT_WIFISTRENGTH, EVT_ETHERNET]
        )
        await self.ws_listener.connect()
    async def create_backup(self) -> bool:
        return await self.api.create_backup()

    async def update_firmware(self, version) -> bool:
        return await self.api.update_firmware(version)

    def ensure_group_configured(self, data):
        """Ensures the group exists on Home Assistant"""
        uuid = f"{self.unique_id}_group{data['groupId']}"
        devices = device_registry.async_get(self.hass)
        device = devices.async_get_device({(DOMAIN, self.unique_id)})
        entities = entity_registry.async_get(self.hass)
        for entity in async_entries_for_config_entry(entities, self.config_entry_id):
            if entity.unique_id == uuid:
                return
        dev_features = (
            CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
        )

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
        print(f"Group not found {uuid} and one was added")

    def ensure_shade_configured(self, data):
        """Ensures the shade exists on Home Assistant"""
        uuid = f"{self.unique_id}_{data['shadeId']}"

        devices = device_registry.async_get(self.hass)
        device = devices.async_get_device({(DOMAIN, self.unique_id)})

        entities = entity_registry.async_get(self.hass)

        for entity in async_entries_for_config_entry(entities, self.config_entry_id):
            if entity.unique_id == uuid:
                return
        dev_features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.STOP
            | CoverEntityFeature.SET_POSITION
        )

        dev_class = CoverDeviceClass.SHADE
        if "shadeType" in data:
            match int(data["shadeType"]):
                case 1:
                    dev_class = CoverDeviceClass.BLIND
                    if "tiltType" in data:
                        match int(data["tiltType"]):
                            case 1 | 2:
                                dev_features |= (
                                    CoverEntityFeature.OPEN_TILT
                                    | CoverEntityFeature.CLOSE_TILT
                                    | CoverEntityFeature.SET_TILT_POSITION
                                )
                    else:
                        if "hasTilt" in data and data["hasTilt"] is True:
                            dev_features |= (
                                CoverEntityFeature.OPEN_TILT
                                | CoverEntityFeature.CLOSE_TILT
                                | CoverEntityFeature.SET_TILT_POSITION
                            )
                case 2 | 7 | 8:
                    dev_class = CoverDeviceClass.CURTAIN
                case 3:
                    dev_class = CoverDeviceClass.AWNING
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

        # Catch the fwStatus messages before they go anywhere
        # this will allow us to simply update the latest firmware
        if "event" in data and data["event"] == EVT_FWSTATUS:
            self.api.set_firmware(data)


        self.async_set_updated_data(data=data)

    def ws_onopen(self):
        """Callback when the websocket is opened"""
        _LOGGER.debug("ESPSomfy RTS Socket was opened")
        if self.api.is_configured:
            _LOGGER.debug("ESPSomfy RTS Already Configured")
            data = {"event": EVT_CONNECTED, "connected": True}
            self.async_set_updated_data(data=data)
        else:
            _LOGGER.debug("ESPSomfy RTS configuring entities")
            loop = asyncio.get_event_loop()
            coro = loop.create_task(self.api.get_initial())
            def handle_connected(_coro):
                data = {"event": EVT_CONNECTED, "connected": True}
                self.async_set_updated_data(data=data)
            coro.add_done_callback(handle_connected)


    def ws_onerror(self, exception):
        """An error occurred on the socket connection"""
        data = {"event": EVT_CONNECTED, "connected": False}
        self.async_set_updated_data(data=data)

    def ws_onclose(self):
        """The socket has been closed"""
        data = {"event": EVT_CONNECTED, "connected": False}
        self.async_set_updated_data(data=data)


class ESPSomfyAPI:
    """API for sending data to nodejs-PoolController"""

    def __init__(self, hass: HomeAssistant, config_entry_id, data) -> None:
        self.hass = hass
        self.data = data
        self._host = data[CONF_HOST]
        self._sock_url = f"ws://{self._host}:8080"
        self._api_url = f"http://{self._host}:8081"
        self._config: Any = {}
        self._session = async_get_clientsession(self.hass, verify_ssl=False)
        self._authType = 0
        self._needsKey = False
        self._headers = dict({"apikey": ""})
        self._canLogin = False
        self._deviceName = data[CONF_HOST]
        self._can_update = False
        self._config_entry_id = config_entry_id
        self._configured = False

    @property
    def shades(self) -> Any:
        """Return the state shades."""
        if "shades" in self._config:
            return self._config["shades"]
        return []

    @property
    def groups(self) -> Any:
        """Return the state groups"""
        if "groups" in self._config:
            return self._config["groups"]
        return []

    @property
    def server_id(self) -> str | None:
        """Getter for the server id"""
        if "serverId" in self._config:
            return self._config["serverId"]

    @property
    def version(self) -> str:
        """Getter for the api version"""
        if "version" in self._config:
            return self._config["version"]
        elif "fwVersion" in self._config:
            return self._config["fwVersion"]
        return "0.0.0"

    @property
    def latest_version(self) -> str | None:
        """Getter for the latest version"""
        if "latest" in self._config:
            if self._config["latest"] == "":
                return None
            return self._config["latest"]
        return None

    @property
    def model(self) -> str:
        """Getter for the model number"""
        return self._config["model"]

    @property
    def apiKey(self) -> str:
        """Getter for the api key"""
        return self._config["apiKey"]

    @property
    def deviceName(self) -> str:
        """Getter for the device name"""
        return self._deviceName

    @property
    def can_update(self) -> bool:
        """Getter for whether the firmware is updatable"""
        return self._can_update
    @property
    def backup_dir(self) -> str:
        """Gets the backup directory for the device"""
        return self.hass.config.path(f"ESPSomfyRTS_{self.server_id}")
    @property
    def check_for_update(self) -> bool:
        if "checkForUpdate" in self._config:
            return self._config["checkForUpdate"]
        return self._can_update
    @property
    def internet_available(self) -> bool:
        if "inetAvailable" in self._config:
            return self._config["inetAvailable"]
        return self._can_update
    @property
    def is_configured(self) -> bool:
        """Indicates whether the integration has been configured"""
        return self._configured

    def get_sock_url(self):
        """Get the socket interface url"""
        return self._sock_url

    def get_api_url(self):
        """Get that url used for api reference"""
        return self._api_url

    def get_config(self):
        """Return the initial config"""
        return self._config

    def get_data(self):
        """Return the internal data"""
        return self.data

    def set_firmware(self, data) -> None:
        """Set the firmware data from the socket"""
        cver = "0.0.0"
        if "version" in self._config:
            cver = self._config["version"]
        new_ver = cver
        if "fwVersion" in data:
            new_ver = data["fwVersion"]
            if "name" in new_ver:
                new_ver = new_ver["name"]
        elif "version" in data:
            new_ver = data["version"]
        if "latest" in data:
            latest_ver = data["latest"]
            if "name" in latest_ver:
                latest_ver = latest_ver["name"]
            self._config["latest"] = latest_ver
        if "checkForUpdate" in data:
            self._config["checkForUpdate"] = data["checkForUpdate"]
        if "inetAvailable" in data:
            self._config["inetAvailable"] = data["inetAvailable"]
        if cver != new_ver:
            # print(f"Version: {cver} to {new_ver}")
            dev_registry = device_registry.async_get(self.hass)
            if dev := dev_registry.async_get_device(identifiers={(DOMAIN, f"espsomfy_{self.server_id}")}):
                dev_registry.async_update_device(dev.id, sw_version=new_ver)
        self._config["version"] = new_ver
        v = version_parse(new_ver)
        if (v.major > 2) or (v.major == 2 and v.minor > 2) or (v.major == 2 and v.minor == 2 and v.micro > 0):
            self._can_update = True
        else:
            self._can_update = False

    async def check_address(self, url) -> bool:
        """Sends a head to a url to check if it exists"""
        try:
            async with self._session.get(url) as resp:
                if resp.status == 200:
                    return True
                print(resp)
        except:
            pass
        return False

    async def update_firmware(self, version) -> bool:
        url = f"{self._api_url}/downloadFirmware?ver={version}"
        async with self._session.get(url, headers=self._headers) as resp:
            if(resp.status == 200):
                return True
            _LOGGER.error(await resp.text())
        return False

    async def create_backup(self) -> bool:
        """Creates a backup"""
        url = f"{self._api_url}/backup?attach=true"
        async with self._session.get(url, headers=self._headers) as resp:
            if  resp.status == 200:
                if not os.path.exists(self.backup_dir):
                    os.mkdir(self.backup_dir)
                data = await resp.text(encoding=None)
                fpath = self.hass.config.path(f"{self.backup_dir}/{datetime.now().strftime('%Y-%m-%dT%H_%M_%S')}.backup")
                with open(file=fpath, mode="wb+") as f:
                    if f is not None:
                        f.write(data.encode())
                        f.close()
                    else:
                        return False
                    return True
        return False

    def get_backups(self) -> list[str] | None:
        """Gets a list of all the available backups"""
        f:list[str] = []
        if not os.path.exists(self.backup_dir):
            return None
        files = os.listdir(self.backup_dir)
        for file in files:
            if(os.path.isfile(os.path.join(self.backup_dir, file)) and file.endswith(".backup") and file[:1].isdigit()):
                f.append(file)
        f.sort(reverse=True)
        return f
    def apply_data(self, data) -> None:
        """Applies the returned data to the configuration"""
        self._config["serverId"] = data["serverId"]
        self._config["model"] = data["model"]
        if "chipModel" in data:
            self._config["chipModel"] = data["chipModel"]
        if "connType" in data:
            self._config["connType"] = data["connType"]
        if "checkForUpdate" in data:
            self._config["checkForUpdate"] = data["checkForUpdate"]
        if "rooms" in data:
            self._config["rooms"] = data["rooms"]
        elif "rooms" not in self._config:
            self._config["rooms"] = []
        if "shades" in data:
            self._config["shades"] = data["shades"]
        elif "shades" not in self._config:
            self._config["shades"] = []
        if "groups" in data:
            self._config["groups"] = data["groups"]
        elif "groups" not in self._config:
            self._config["groups"] = []
        if "hostname" in data:
            self._config["hostname"] = data["hostname"]
            self._deviceName = data["hostname"]
        if "authType" in data:
            self._config["authType"] = data["authType"]
            self._canLogin = True
        elif "authType" not in self._config:
            self._config["authType"] = 0
            self._canLogin = False
        if "permissions" in data:
            self._config["permissions"] = data["permissions"]
        elif "permissions" not in self._config:
            self._config["permissions"] = 1
        self._needsKey = False
        if self._config["authType"] > 0:
            if self._config["permissions"] != 1:
                self._needsKey = True
        self.set_firmware(data)


    async def discover(self) -> Any | None:
        """Discover the device on the network"""
        url = f"{self._api_url}{API_DISCOVERY}"
        async with self._session.get(url, headers=self._headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                self.apply_data(data)
                return data
            _LOGGER.error(await resp.text())
            raise DiscoveryError(f"{url} - {await resp.text()}")

    async def load_shades(self) -> Any | None:
        """Loads all the shades from the controller"""
        async with self._session.get(f"{self._api_url}{API_SHADES}") as resp:
            if resp.status == 200:
                self._config["shades"] = await resp.json()
                return self._config["shades"]
            _LOGGER.error(await resp.text())

    async def load_groups(self) -> Any | None:
        """Loads all the groups from the controller"""
        async with self._session.get(f"{self._api_url}{API_GROUPS}") as resp:
            if resp.status == 200:
                self._config["groups"] = await resp.json()
                return self._config["groups"]
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

    async def sun_flag_off(self, shade_id: int):
        """Send the command to turn off the sun flag"""
        await self.shade_command({"shadeId": shade_id, "command": "flag"})

    async def sun_flag_on(self, shade_id: int):
        """Send the command to turn off the sun flag"""
        await self.shade_command({"shadeId": shade_id, "command": "sunflag"})

    async def sun_flag_group_off(self, group_id: int):
        """Send the command to turn off the sun flag"""
        await self.group_command({"groupId": group_id, "command": "flag"})

    async def sun_flag_group_on(self, group_id: int):
        """Send the command to turn off the sun flag"""
        await self.group_command({"groupId": group_id, "command": "sunflag"})

    async def open_shade(self, shade_id: int):
        """Send the command to open the shade"""
        await self.shade_command({"shadeId": shade_id, "command": "up"})

    async def close_shade(self, shade_id: int):
        """Send the command to close the shade"""
        await self.shade_command({"shadeId": shade_id, "command": "down"})

    async def toggle_shade(self, shade_id: int):
        """Sent the command to toggle"""
        await self.shade_command({"shadeId": shade_id, "command": "toggle"})

    async def stop_shade(self, shade_id: int):
        """Send the command to stop the shade"""
        #print(f"STOP ShadeId:{shade_id}")
        await self.shade_command({"shadeId": shade_id, "command": "my"})

    async def open_group(self, group_id: int):
        """Send the command to open the group"""
        await self.group_command({"groupId": group_id, "command": "up"})

    async def close_group(self, group_id: int):
        """Send the command to close the group"""
        await self.group_command({"groupId": group_id, "command": "down"})

    async def stop_group(self, group_id: int):
        """Send the command to stop the group"""
        #print(f"STOP GroupId:{group_id}")
        await self.group_command({"groupId": group_id, "command": "my"})

    async def position_shade(self, shade_id: int, position: int):
        """Send the command to position the shade"""
        #print(f"POS ShadeId:{shade_id} Target:{position}")
        await self.shade_command({"shadeId": shade_id, "target": position})

    async def raw_command(self, shade_id: int, command: str):
        """Send the command to the shade"""
        await self.shade_command({"shadeId": shade_id, "command": command})

    async def shade_command(self, data):
        """Send commands to ESPSomfyRTS via PUT request"""
        await self.put_command(API_SHADECOMMAND, data)

    async def set_current_position(self, shade_id:int, position:int):
        """Sets the current position without moving the motor"""
        await self.put_command(API_SETPOSITIONS, {"shadeId": shade_id, "position": position})

    async def set_current_tilt_position(self, shade_id: int, tilt_position:int):
        """Sets the current position without moving the motor"""
        await self.put_command(API_SETPOSITIONS, {"shadeId": shade_id, "tiltPosition": tilt_position})

    async def set_sunny(self, shade_id:int, sunny:bool):
        """Set the sunny condition for the motor"""
        await self.put_command(API_SETSENSOR, {"shadeId": shade_id, "sunny": sunny})

    async def set_windy(self, shade_id:int, windy:bool):
        """Set the windy condition for the motor"""
        await self.put_command(API_SETSENSOR, {"shadeId": shade_id, "windy": windy})


    async def put_command(self, command, data):
        """Sends a put command to the device"""
        async with self._session.put(
            f"{self._api_url}{command}", json=data) as resp:
            if resp.status == 200:
                pass
            else:
                _LOGGER.error(await resp.text())

    async def login(self, data):
        """Log in to EPSSomfy device"""
        if self._canLogin:
            async with self._session.put(
                f"{self._api_url}{API_LOGIN}", json=data
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if "success" in data and data["success"]:
                        if "apiKey" in data:
                            self._config["apiKey"] = self._headers["apikey"] = data[
                                "apiKey"
                            ]
                    else:
                        if "type" in data:
                            if data["type"] == 1:
                                raise LoginError(CONF_PIN, "invalid_pin")
                            elif data["type"] == 2:
                                raise LoginError(CONF_USERNAME, "invalid_password")
                        raise LoginError(CONF_HOST, "invalid_login")

                else:
                    _LOGGER.error(f"Error logging in: {await resp.text()}")
                    raise LoginError(f"{self._api_url} - {await resp.text()}")

    async def group_command(self, data):
        """Send commands to ESPSomfyRTS via PUT request"""
        async with self._session.put(
            f"{self._api_url}{API_GROUPCOMMAND}", json=data
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
        """Get the initial config from ESPSomfy RTS."""
        try:
            self._session = aiohttp_client.async_get_clientsession(self.hass)
            async with self._session.get(f"{self._api_url}{API_DISCOVERY}") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.apply_data(data)
                    entry = self.hass.config_entries.async_get_entry(self._config_entry_id)
                    if(self._configured == False):
                        _LOGGER.debug("ESPSomfy RTS Setting up entities")
                        await self.hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
                        self._configured = True
                else:
                    _LOGGER.error(await resp.text())
        except aiohttp.ClientError:
            pass


class InvalidHost(HomeAssistantError):
    """Error to indicate that hostname/IP address is invalid."""


class DiscoveryError(HomeAssistantError):
    """Error that occurred during discovery"""


class LoginError(HomeAssistantError):
    """Error that occurs when login fails"""

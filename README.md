<image src="https://user-images.githubusercontent.com/47839015/218900217-81f88955-67b8-4ed8-8e97-271de66c555e.png" align="right" style="margin-top:-2em;width:177px;margin-right:2em;display:inline-block;float:right;"></image>

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration) 

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=rstrouse&repository=espsomfy-rts-ha)


# ESPSomfy RTS-HA 
Control up to 32 of your somfy shades in Home Assistant and set their position using an ESP32 and an inexpensive CC1101 tranceiver module.  You may also define up to 16 group shades that will allow you to move multiple covers at once.

# Requirements
This integration requires hardware that uses an ESP32 microcontroller and a CC1101 transceiver.  Setup for this controller can be found at the [ESPSomfy RTS hardware repositiory](https://github.com/rstrouse/ESPSomfy-RTS).  You must have one of these inexpensive radios configured for your shades.

# Installation
The easiest way to get going is to install this integration in Home Assistant using HACS as a [Custom Repository](https://hacs.xyz/docs/faq/custom_repositories/).  As an alternative you may install it manually by copying the contents of the `custom_components` folder to the `config/custom_components` directory of your Home Assistant installation.

## Setup
Once installed, ESPSomfy-RTS-HA will automatically detect any radio devices on your local network. Just browse to Home Assistant's Settings &rarr; Devices & Services and your ESPSomfy-RTS device will show up as available to configure.

# Updates
After you have installed the plugin, you will be notified when there is a new version of the plugin available.  As of v2.2.1 of the ESPSomfy RTS firmware you can also update your devices remotely using the update entity included in the plugin.  It will notify you when there is a new version to install.

# Functionality
Once configured you will be able to open, close, and set the position of your shades using home assistant.  The integration will monitor the position of the shade regardless of how it was opened or closed.  This includes opening or closing it using a Telis remote.  Shades can be added to your dashboards and automated with Home Assistant services through automations.

![image](https://user-images.githubusercontent.com/47839015/213933858-95042e9e-0874-4e58-8123-87146439a20e.png)

# Services
There are a number of automation services available.  You can find these in the [Services](https://github.com/rstrouse/ESPSomfy-RTS-HA/wiki/Services) wiki.

# Events
The integration emits events on the Home Assistant event bus for all commands whether they have originated in Home Assistant, a remote control, or the ESPSomfy RTS web interface.  These events can be captured using the `espsomfy-rts_event` type.

The data payload for the event includes:
* `entity_id`: The entitiy id in home assistant for the target cover
* `event_key`: The event that triggered this event (for now this is always shadeCommand)
* `name`: The name assigned to the entity
* `source`: The originator of the command.  This will be one of the following
  * `remote`: The user pressed a button on a remote
  * `internal`: The command originated from ESPSomfy RTS
  * `group`: The command was part of a group command
* `remote_address`: The address defined for the ESPSomfy RTS motor
* `source_address`: The address of the source device.  If this is a remote it will be the address of the remote channel.  If it is part of a group request it will be the address of the group.
* `command`: This will be one of the following commands
  * `Up` - An up command was issued
  * `Down` - A down command was issued
  * `My` - A my/stop command was issued
  * `StepUp` - A step up command was issued
  * `StepDown` - A step down command was issued
  * `Prog` - The prog button was pressed
  * `My+Up` - A combination of the my and up button was pressed at the same time
  * `My+Down` - A combination of the my and down button was pressed at the same time
  * `Up+Down` - The up and down buttons were pressed at the same time
  * `My+Up+Down` - The my, up, and down buttons were all pressed at the same time
  

![image](https://github.com/rstrouse/ESPSomfy-RTS-HA/assets/47839015/2fbf4ad8-86b4-4d4e-ac8e-ce04ba4adeeb)






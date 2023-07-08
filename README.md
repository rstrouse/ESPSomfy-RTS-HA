[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration) 
# ESPSomfy RTS-HA <image src="https://user-images.githubusercontent.com/47839015/218900217-81f88955-67b8-4ed8-8e97-271de66c555e.png" style="margin-top:-2em;width:107px;margin-right:2em;display:inline-block;float:right;"></image>
Control up to 32 of your somfy shades in Home Assistant and set their position using an ESP32 and an inexpensive CC1101 tranceiver module.  You may also define up to 16 group shades that will allow you to move multiple covers at once.

# Requirements
This integration requires hardware that uses an ESP32 microcontroller and a CC1101 transceiver.  Setup for this controller can be found at the [ESPSomfy RTS hardware repositiory](https://github.com/rstrouse/ESPSomfy-RTS).  You must have one of these inexpensive radios configured for your shades.

# Installation
The easiest way to get going is to install this integration in Home Assistant using HACS as a [Custom Repository](https://hacs.xyz/docs/faq/custom_repositories/).  As an alternative you may install it manually by copying the contents of the `custom_components` folder to the `config/custom_components` directory of your Home Assistant installation.

## Setup
Setup is a snap and ESPSomfy-RTS will automatically detect any radio devices on your local network for inclusion in home assistant.

# Functionality
Once configured you will be able to open, close, and set the position of your shades using home assistant.  The integration will monitor the position of the shade regardless of how it was opened or closed.  This includes opening or closing it using a Telis remote.  Shades can be added to your dashboards and automated with Home Assistant services through automations.

![image](https://user-images.githubusercontent.com/47839015/213933858-95042e9e-0874-4e58-8123-87146439a20e.png)

# Events
The integration emits events on the Home Assistant event bus for all commands whether they have originated in Home Assistant, a remote control, or the ESPSomfy RTS web interface.  These events can be captured using the `espsomfy-rts_event` type.

![image](https://github.com/rstrouse/ESPSomfy-RTS-HA/assets/47839015/2fbf4ad8-86b4-4d4e-ac8e-ce04ba4adeeb)






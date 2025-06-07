# DomBusGateway
Python gateway that **interfaces one or more DomBus networks of home automation modules with MQTT AutoDiscovery**


### What is DomBus?

It's a custom protocol developed by [Creasol](https://www.creasol.it/domotics) to communicate with home automation modules using a **RS485 serial bus, made by a standard alarm cable within 4 wires**, 2 for data at 115200bps, 2 for 12-24V to supply all devices.

It's a **multi-master protocol**, where each **DomBus module can start communicating to the controller for example when an input changes** (for example a counter, alarm sensor, pushbutton), with a low latency (typically less than 100ms).

Also, it supports the so-called *DCMD*, commands sent between modules triggered by a input change or when a condition becomes true. **DCMD can be used to realize simple automations that work even when the main controller (Domoticz, Home Assistant, ...) is frozen or OFF, similarly to [KNX](https://www.knx.org/)**.


### What are DomBus modules?

They are **very low power consumption devices** with several **versatile I/Os and sensors**, performing general or specific functions, that can be used in building automations. 
They can be factory programmed with **DomBus** custom protocol, or **Modbus** standard protocol.

A list of DomBus modules can be found below.


### For what home automation systems can DomBus modules be used?

DomBus modules equipped with DomBus firmware can be used with:
* [Domoticz](https://wiki.domoticz.com/Creasol_Dombus), using the **CreasolDomBus plugin**
* [Home Assistant](https://www.home-assistant.io/) and [OpenHAB](https://www.openhab.org/), using the **DomBusGateway** software that acts as a **DomBus to MQTT-AD gateway**. Also, other systems supporting MQTT can be used in this way, for example [NodeRED](https://nodered.org/) and many others.

DomBus modules equipped with Modbus firmware can be used with:
* [Home Assistant](https://www.home-assistant.io/), [OpenHAB](https://www.openhab.org/), [NodeRED](https://nodered.org/), [ioBroker](https://www.iobroker.net/) and many other systems supporting the Modbus protocol. 


### For HomeAssistant and OpenHAB, is it better DomBus + DomBusGateway, or Modbus?

DomBus + DomBusGateway implementation is simpler, because all devices/entities are created. It's a must in case that DCMD, pushbuttons, alarm sensors and counters are needed.

Modbus can be used for relay modules, EVSE module (to make your own electric vehicle charging wallbox), Dual axis solar tracker. It's not recommended in case that pushbuttons, alarm sensors and counters have to be used.



## How does DomBusGateway work?

Once executed, using the command _python3 dombusgateway.py &_ , it opens one or more serial ports connected to DomBus modules (to get a reliable large network, it's possible to divide the DomBus network in trunks with 20-30 modules/each, or divide the building by floors/zones). It's also possible to use WiFi/LAN RS485 modules that provide a virtual serial interface, to get a wireless connection between the main controller where DomBusateway runs, and RS485 port physically connected to the DomBus modules. 

If MQTT is enabled, it opens a connection to the MQTT broker to exchange data (sending device states and reading command from the domotic controller).

If TELNET port is enabled, the user can connect DomBusGateway to show the network of modules and set configuration parameters for each module. DomBus modules usually have configurable I/Os, for example a I/O should be configured as digital input, analog input, counter, energy counter, and so on, and this configuration can be done by Telnet.

**The software is still experimental, in development stage**

![screenshot of Home Assisstant that automatically read and manage some DomBus modules](https://images.creasol.it/dombusprotocol.webp)

# Files

* _dombusgateway.py_: main server that must be runned in background, calling _python3 dombusgateway.py &_

* _dombusgateway_const.py_: script with several constants used by _dombusgateway.py_

* _dombusgateway_conf.py_: configuration file 

* _dombusgateway_conf_local.py_: configuration file that will never be overwritten from the GitHub repository: this is the right place to store your local configuration

* _data/_: directory, created if not existing, where list of DomBus modules and configuration is saved and restored



# Installation

* git clone git@github.com:CreasolTech/DomBusGateway.git

* cd DomBusGateway

* edit file _dombusgateway_conf_local.py_ to define the serial ports, logging, MQTT parameters

* python3 dombusgateway.py

The software is still in developing, so do not expect to have full features available and software stability!



# Telnet command line interface

It's possible to connect dombusgateway by telnet in this way:

_telnet localhost 8023_

Telnet CLI permits to:

* _showbus BUS_ : list modules attached to the specified bus (it's possible to connect 20-30 modules to the same bus, but for safety reasons it can be good to differentiate bus by floors or by area to manage very large buildings). For example _showbus 2_ to list modules attached to bus #2<br clear="all" /> 
![showbus command](https://images.creasol.it/showbus.webp)

* _showmodule ADDR_ : list ports associated to the specified module. For example _showmodule 3701_ to list ports and configuration for the module with address 3701.

* _setport PORT CONFIGURATION_ : TODO change the configuration of the specified port. For example _setport 1 IN_COUNTER,DIVIDER=2000_ to configure port1 in counter mode, type energy meter with pulsed output, 2000 pulses / kWh.<br clear="all" /> 
![setport command example](https://images.creasol.it/setport.webp)


# Credits
Software is written by Creasol, https://www.creasol.it with the valuable help of:

*





***

## Creasol DomBus modules

Below a list of modules, produced in Europe by Creasol, designed for Domoticz to be reliable and optimized for very very low power consumption.

Our industrial and home automation modules are designed to be
* very low power (**around 10mW with relays OFF**)
* reliable (**no disconnections**)
* bus connected (**no radiofrequency interference, no battery to replace**).

Modules are available in two version:
1. with **DomBus proprietary protocol**, working with [Domoticz](https://www.domoticz.com) only
2. with **Modbus standard protocol**, working with [Home Assistant](https://www.home-assistant.io), [OpenHAB](https://www.openhab.org), [Node-RED](https://nodered.org)

[Store website](https://store.creasol.it/domotics) - [Information website](https://www.creasol.it/domotics)

### Youtube video showing DomBus modules
[![Creasol DomBus modules video](https://images.creasol.it/intro01_video.png)](https://www.creasol.it/DomBusVideo)



### DomBusEVSE - EVSE module to build a Smart Wallbox / EV charging station
<a href="https://store.creasol.it/DomBusEVSE"><img src="https://images.creasol.it/creDomBusEVSE_plug_300.webp" alt="DomBusEVSE smart EVSE module to make a Smart Wallbox EV Charging station" style="float: left; margin-right: 2em;" align="left" /></a>
Complete solution to make a Smart EVSE, **charging the electric vehicle using only energy from renewable source (photovoltaic, wind, ...), or adding 25-50-75-100% of available power from the grid**.

* **Single-phase and three-phase**, up to 32A (8kW or 22kW)
* Needs external contactor, RCCB (protection) and EV cable
* Optional power meter to measure charging power, energy, voltage and power factor
* Optional power meter to measure the power usage from the grid (not needed if already exists)
* **Two max grid power thresholds** can be programmed: for example, in Italy who have 6kW contractual power can drain from the grid Max (6* 1.27)=7.6kW for max 90 minutes followed by (6* 1.1)=6.6kW for another 90 minutes: in this case **the EVSE module can drain ALL available power** when programmed to charge at 100% **minimizing the charge time and increasing the charging efficiency**.
* **Works without the domotic controller** (stand-alone mode), and **can also work in *managed mode*, with an automation in the home automation system setting the charging current**

<br clear="all"/>

### DomBusTH - Compact board to be placed on a blank cover, with temperature and humidity sensor and RGW LEDs
<a href="https://store.creasol.it/DomBusTH"><img src="https://images.creasol.it/creDomBusTH6_200.png" alt="DomBusTH domotic board with temperature and humidity sensor, 3 LEDs, 6 I/O" style="float: left; margin-right: 2em;" align="left" /></a>
Compact board, 32x17mm, to be installed on blank cover with a 4mm hole in the middle, to exchange air for the relative humidity sensor. It can be **installed in every room to monitor temperature and humidity, check alarm sensors, control blind motor UP/DOWN**, send notifications (using red and green leds) and activate **white led in case of power outage**.

Includes:
* temperature and relative humidity sensor
* red, green and white LEDs
* 4 I/Os configurable as analog or digital inputs, pushbuttons, counters (water, gas, S0 energy, ...), NTC temperature and ultrasonic distance sensors
* 2 ports are configured by default as open-drain output and can drive up to 200mA led strip (with dimming function) or can be connected to the external module DomRelay2 to control 2 relays; they can also be configured as analog/digital inputs, pushbuttons and distance sensors.
<br clear="all"/>

### DomBus12 - Compact domotic module with 9 I/Os
<a href="https://store.creasol.it/DomBus12"><img src="https://images.creasol.it/creDomBus12_400.webp" alt="DomBus12 domotic module with 9 I/O" style="float: left; margin-right: 2em;" align="left" /></a>
**Very compact, versatile and cost-effective module with 9 ports**. Each port can be configured by software as:
* analog/digital inputs
* pushbutton and UP/DOWN pushbutton
* counters (water, gas, S0 energy, ...)
* NTC temperature and ultrasonic distance sensors
* 2 ports are configured by default as open-drain output and can drive up to 200mA led strip (with dimming function) or can be connected to the external module DomRelay2 to control 2 relays.
<br clear="all"/>

### DomBus21 - Latching relays domotic module
<a href="https://store.creasol.it/DomBus21"><img src="https://images.creasol.it/creDomBus21_400.webp" alt="DomBus21 domotic module with 3 latching relays, 1 AC input and 4 low voltage inputs" style="float: left; margin-right: 2em; vertical-align: middle;" align="left" /></a>
Very compact domotic module providing:
* **3x latching relays SPST, max current 15A (3kW): no power consumption when relays are On or Off!**
* 1x 230V AC opto-isolated input to detect 230V and power outage, with **zero-detection to switch relays/loads minimizing in-rush current**
* 4x I/O lines, configurable as analog/digital inputs, temperature/distance sensor, counter, meter, ...
<br clear="all"/>

### DomBus23 - Domotic module with many functions
<a href="https://store.creasol.it/DomBus23"><img src="https://images.creasol.it/creDomBus23_400.webp" alt="DomBus23 domotic module with many functions" style="float: left; margin-right: 2em; vertical-align: middle;" align="left" /></a>
Versatile module designed to control **gate or garage door**.
* 2x relays SPST 5A
* 1x 10A 30V mosfet (led stripe dimming)
* 2x 0-10V analog output: each one can be configured as open-drain output to control external relay
* 2x I/O lines, configurable as analog/digital inputs, temperature/distance sensor, counter, ...
* 2x low voltage AC/DC opto-isolated inputs, 9-40V
* 1x 230V AC opto-isolated input
<br clear="all"/>

### DomBus31 - Domotic module with 8 relays
<a href="https://store.creasol.it/DomBus31"><img src="https://images.creasol.it/creDomBus31_400.webp" alt="DomBus31 domotic module with 8 relay outputs" style="float: left; margin-right: 2em; vertical-align: middle;" align="left" /></a>
DIN rail low profile module, with **8 relays and very low power consumption**:
* 6x relays SPST 5A
* 2x relays STDT 10A
* Only 10mW power consumption with all relays OFF
* Only 500mW power consumption with all 8 relays ON !!
<br clear="all"/>

### DomBus32 - Domotic module with 3 relays
<a href="https://store.creasol.it/DomBus32"><img src="https://images.creasol.it/creDomBus32_200.webp" alt="DomBus32 domotic module with 3 relay outputs" style="float: left; margin-right: 2em; vertical-align: middle;" align="left" /></a>
Versatile module with 230V inputs and outputs, and 5 low voltage I/Os.
* 3x relays SPST 5A
* 3x 115/230Vac optoisolated inputs
* Single common for relays and AC inputs
* 5x general purpose I/O, each one configurable as analog/digital inputs, pushbutton, counter, temperature and distance sensor.
<br clear="all"/>

### DomBus33 - Module to domotize a light system using step relays
<a href="https://store.creasol.it/DomBus33"><img src="https://images.creasol.it/creDomBus32_200.webp" alt="DomBus33 domotic module with 3 relay outputs that can control 3 lights" style="float: left; margin-right: 2em; vertical-align: middle;" align="left" /></a>
Module designed to **control 3 lights already existing and actually controlled by 230V pushbuttons and step-by-step relays**. In this way each light can be activated by existing pushbuttons, and by the domotic controller.
* 3x relays SPST 5A
* 3x 115/230Vac optoisolated inputs
* Single common for relays and AC inputs
* 5x general purpose I/O, each one configurable as analog/digital inputs, pushbutton, counter, temperature and distance sensor.

Each relay can toggle the existing step-relay, switching the light On/Off. The optoisolator monitors the light status. The 5 I/Os can be connected to pushbuttons to activate or deactivate one or all lights.
<br clear="all"/>

### DomBus36 - Domotic module with 12 relays
<a href="https://store.creasol.it/DomBus36"><img src="https://images.creasol.it/creDomBus36_400.webp" alt="DomBus36 domotic module with 12 relay outputs" style="float: left; margin-right: 2em; vertical-align: middle;" align="left" /></a>
DIN rail module, low profile, with **12 relays outputs and very low power consumption**.
* 12x relays SPST 5A
* Relays are grouped in 3 blocks, with a single common per block, for easier wiring
* Only 12mW power consumption with all relays OFF
* Only 750mW power consumption with all 12 relays ON !!
<br clear="all"/>

### DomBus37 - 12 inputs, 3 115/230Vac inputs, 3 relay outputs
<a href="https://store.creasol.it/DomBus37"><img src="https://images.creasol.it/creDomBus37_400.webp" alt="DomBus37 domotic module with 12 inputs, 3 AC inputs, 3 relay outputs" style="float: left; margin-right: 2em; vertical-align: middle;" align="left" /></a>
Module designed to **interface alarm sensors (magnetc contact sensors, PIRs, tampers): it's able to monitor mains power supply (power outage / blackout) and also have 3 relays outputs.**
* 12x low voltage inputs (analog/digital inputs, buttons, alarm sensors, balanced double/triple biased alarm sensors,  counters, meters, temperature and distance sensors, ...)
* 3x 115/230Vac optoisolated inputs
* 2x relays SPST 5A
* 1x relay SPST 10A
<br clear="all"/>

### DomBus38 - 12 inputs, 1 100-250Vac input, 6 relay outputs
<a href="https://store.creasol.it/DomBus38"><img src="https://images.creasol.it/creDomBus38_400.webp" alt="DomBus38 smart home module with 12 inputs, 1 AC input, 6 SPDT relay outputs + 2 SPDT relay outputs 10A" style="float: left; margin-right: 2em; vertical-align: middle;" align="left" /></a>
Module designed to **interface alarm sensors (magnetc contact sensors, PIRs, tampers), lights and appliances outputs, ...**
* 12x low voltage inputs (analog/digital inputs, buttons, alarm sensors, balanced double/triple biased alarm sensors, counters, meters, temperature and distance sensors, ...)
* 1x 115/230Vac optoisolated input to detect power outage and for zero-crossing detection (to switch relays minimizing the in-rush current)
* 4x relays SPDT 10A (with Normally Open and Normally Closed contacts)
* 2x relays SPST 10A (with only Normally Open contacts)
<br clear="all"/>

### DomBusTracker - Dual axis sun tracker controller working with Domoticz, Home Assistant, Node-RED, Modbus, ... and also working in standalone with no external controllers
<a href="https://store.creasol.it/DomBusTracker"><img src="https://images.creasol.it/creDomBusTracker_sun_400.webp" alt="DomBusTracker smart home module that controls 2 linear actuators in a solar tracking system" style="float: left; margin-right: 2em; vertical-align: middle;" align="left" /></a>
Module that **check a deep-hole sun sensor to detect the direction of maximal sun radiation, working also in case of cloudy weather.**
* Controls two external actuators/motors (linear or not) to move motors to reach the best tilt / elevation and azimuth position to optimize photovoltaic production.
* **Check current through the motors to detect internal limit switch** (useful for linear actuators) and find where the tracker reach the final/initial position.
* **Works autonomously** (stand-alone), without any home automation system controller, but **also can be interface by Domoticz** (DomBus protocol) and **Home Assistant, NodeRED, OpenHAB,** ... (using Modbus protocol).
* Wire connection (RS485) to the domotic controller for the best reliability.
<br clear="all"/>

### DomRelay2 - 2x relays board
<a href="https://store.creasol.it/DomRelay2"><img src="https://images.creasol.it/creDomRelay22_200.png" alt="Relay board with 2 relays, to be used with DomBus domotic modules" style="float: left; margin-right: 2em; vertical-align: middle;" align="left" /></a>
Simple module with 2 relays, to be used with DomBus modules (like <a href="https://store.creasol.it/DomBusTH">DomBusTH</a> and <a href="https://store.creasol.it/DomBus12">DomBus12</a>) or other electronic boards with open-collector or open-drain outputs
* **2x SPST relays 5A** (Normally Open contact)
* Overvoltage protection (for inductive loads, like motors)
* Overcurrent protection (for capacitive laods, like AC/DC power supply, LED bulbs, ...)
<br clear="all"/>

### DomESP1 / DomESP2 - Board with relays and more for ESP8266 NodeMCU WiFi module
<a href="https://store.creasol.it/DomESP1"><img src="https://images.creasol.it/creDomESP2_400.webp" alt="Relay board for ESP8266 NodeMCU module" style="float: left; margin-right: 2em; vertical-align: middle;" align="left" /></a>
**IoT board designed for NodeMCU v3 board using ESP8266 WiFi microcontroller**
* 9÷24V power supply input, with high efficiency DC/DC regulator with 5V output
* **4x SPST relays 5A with overvoltage protection** (varistor)
* **2x mosfet outputs** (max 30V, 10A) for LED dimming or other DC loads
* 1x I²C interface for sensors, extended I/Os and more)
* 1x OneWire interface (DS18B20 or other 1wire sensors/devices)
<br clear="all"/>


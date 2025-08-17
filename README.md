# DomBusGateway
Gateway that **interfaces one or more DomBus networks of home automation modules with MQTT AutoDiscovery**


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
* [Home Assistant](https://www.home-assistant.io/), [OpenHAB](https://www.openhab.org/), [NodeRED](https://nodered.org/), [ioBroker](https://www.iobroker.net/) and other systems supporting MQTT, by using the **DomBusGateway** software that acts as a **DomBus to MQTT-AD gateway**. 
* Other building automation systems supporting **Modbus** protocol can use DomBus modules equipped with Modbus firmware.


### For HomeAssistant, is it better DomBus + DomBusGateway, or Modbus protocol?

**DomBus firmware + DomBusGateway** implementation is quick and simple, because **all devices/entities are created automatically** without any specific integration. **Enable MQTT integration, start DomBusGateway software, connect one or more DomBus modules, and all DomBus ports are immediately visible in your home automation system**.
Also, DomBus protocol is a must in case that DCMD, pushbuttons, alarm sensors and counters are needed.

Modbus may be used for relay modules, EVSE module (to make your own electric vehicle charging wallbox), Dual axis solar tracker. **Modbus is not recommended in case that pushbuttons, alarm sensors and counters have to be used**, because Modbus is a master-slave protocol where the controller have to poll continuosly all Modbus modules to get their input status, introducing delays.

### Example: DomBusEVSE module used to make a Smart Wallbox with Home Assistant

Using DomBusGateway software, Home Assistant is able to automatically create, read and manage all entities of the DomBusEVSE module: MQTT integration have to be enabled, of course!

Then it's possible to arrange entities in a custom dashboard as shown below:

![HomeAssistant Dashboard for the Home Made Wallbox using DomBusEVSE module](https://images.creasol.it/creDomBusEVSE_dashboard3.webp)

More information about the DomBusEVSE module, that can be used to make a home made wallbox working with HomeAssistant, NodeRED, OpenHAB, Domoticz, can be found at https://www.creasol.it/EVSE and https://store.creasol.it . Also, please check the section _DomBusEVSE module to build a DIY EV charger_ below
		

## How does DomBusGateway work?

Once executed, using the command _python3 dombusgateway.py &_ , it opens **one or more serial ports connected to DomBus modules** (to get a reliable large network, it's possible to divide the DomBus network in trunks with 20-30 modules/each, or divide the building by floors/zones). It's also possible to use **WiFi/LAN RS485 modules that provide a virtual serial interface**, to get a wireless connection between the main controller where DomBusateway runs, and RS485 port physically connected to the DomBus modules. 

If MQTT is enabled, it **opens a connection to the MQTT broker** to exchange data (sending device states and reading command from the domotic controller).

If TELNET port is enabled, **the user can connect DomBusGateway by Telnet to check the network of modules and set configuration parameters for each module**. DomBus modules usually have configurable I/Os, for example a I/O should be configured as digital input, analog input, counter, energy counter, and so on, and this configuration can be done by Telnet.

**The software is still experimental, in development stage**

![screenshot of Home Assisstant that automatically read and manage some DomBus modules](https://images.creasol.it/dombusprotocol.webp)

# Files and directories

* _dombusgateway.py_: main server that must be runned in background, calling _python3 dombusgateway.py &_

* _dombusgateway_const.py_: script with several constants used by _dombusgateway.py_

* _dombusgateway_conf.py_: configuration file that must NOT be changed by the user

* _local/dombusgateway_conf_local.py_: local configuration file with custom configuration: this is the right place to store your local configuration, that will not be overwritten by git command

* _data/_: directory, created if not existing, where list of DomBus modules and configuration is saved and restored

* _/var/log/dombusgateway_: directory where logs are stored

* _/etc/systemd/system/dombusgateway.service_: service configuration file for systemd



# Installation

## In a normal Linux environment

From the shell, run the command:

__sudo bash -c "$(curl -sSfL https://creasol.it/DBGinstall)"__

that will automatically install the package and run it from systemd.

DomBusGateway daemon then can be stopped and started by systemd, using the commands:

__systemctl stop dombusgateway__

__systemctl start dombusgateway__


## In HASSOS (Home Asisstant Operating System)

TODO: realize an addon for HASSOS



_Disclaimer: the software is still in developing, and will be improved soon!_



# Telnet command line interface

It's possible to connect dombusgateway by telnet in this way:

_telnet localhost 8023_

Telnet CLI permits to:

* _showbus BUS_ : **list modules attached to the specified bus** (it's possible to connect 20-30 modules to the same bus, but for safety reasons it can be good to differentiate bus by floors or by area to manage very large buildings). For example _showbus 2_ to list modules attached to bus #2<br clear="all" /> 
![showbus command](https://images.creasol.it/showbus.webp)

* _showmodule ADDR_ : **list ports associated to the specified module**. For example _showmodule 3701_ to list ports and configuration for the module with address 3701.
In case that more than 1 bus is installed, this command should be performed after a _showbus N_ module to select the bus number N, or the first bus will be automatically selected.

* _setport PORT CONFIGURATION_ : **change the configuration of the specified port**. For example _setport 1 IN_COUNTER,DIVIDER=2000_ to configure port1 in counter mode, type energy meter with pulsed output, 2000 pulses / kWh. This command can be issued only after a _showmodule ADDR_ to select the appropriate module.<br clear="all" /> 
![setport command example](https://images.creasol.it/setport.webp)

* _setport 1 HWADDR=101_ : **set the new address 101 for the current module**. A unique address should be specified, in hex format, from 1 to efff.



# DomBusEVSE module to build a DIY EV charger
Wiring diagrams to make the charging station, single phase or three phase, is available at <a href="https://www.creasol.it/EVSE">www.creasol.it/EVSE</a>

**The EVSE module is programmed to work, by default, with two energy meters** (one to measure the Grid power, and one to measure the EV power, energy, voltage, PF) connected to the 2nd RS485 bus available on the module: in this case the charging station can work independently from the home automation system.

**As most probably the user already have an energy meter measuring grid power (sometimes included in hybrid solar inverters), it's possible to avoid installing a new energy meter for the grid power by implementing a simple automation that sends the current value of power from the grid**, positive when importing energy, negative when exporting, **to the *P0c Grid Power* entity**. Similarly, for buildings having a stationary battery, it's good to send to the EVSE module the value *Power_from_the_grid* + *Power_from_the_battery* : in this case, when charging the EV in *Solar* mode, the EVSE module works to have *P0c Grid Power*=0 that means *"do not use energy from the grid, nor energy from the stationary battery, but consume only energy from the photovoltaic"*. The same in case of wind, hydro or other power sources. In this case the charging station needs that home automation system works, sending the right value of power from the Grid or Grid-Battery.
In this case you have to configure *P0c Grid Power* as a number entity, in this way:
* open a telnet connection with DomBusGateway _telnet localhost 8023_
* select bus, if needed (default=bus1) _showbus 2_
* select EVSE module _showmodule ffe3_
* set port 0c as platform number, with min value = -12000W and max value = 12000W (depending by your solar and contractual power)  _setport c p=number,min=-12000,max=12000_

Example of an automation for HA that sends (ImportPower - ExportPower) to the *P0c Grid Power* device:

```
- id: '1750798854962'
  alias: power2wallbox
  description: 'Sends Grid power value to the wallbox'
  triggers:
  - trigger: state
    entity_id:
    - sensor.dombus_1201_p07_io7	# Grid import power value (0 while exporting)
    - sensor.dombus_1201_p08_io8	# Grid export power value (0 while importing)
  conditions: []
  actions:
  - service: number.set_value 
    target:
      entity_id: number.dbevse_ffe3_on_bus_2_p0c_grid_power		# Entity name of P0c EVSE module
    data:
      value: >
        {{ (states('sensor.dombus_1201_p07_io7') | float) - (states('sensor.dombus_1201_p08_io8') | float) }}
  mode: single
```


# Credits
Software is written by Creasol, https://www.creasol.it with the valuable help of:

*


# Special thanks to:

* Alex Adam, for debugging


***

## Creasol DomBus modules

Below a list of modules, produced in Italy by Creasol, designed for high reliability and optimized for very very low power consumption.

Our industrial and home automation modules are designed to be
* very low power &rArr; **10÷15mW with relays OFF**
* reliable &rArr; **no disconnections**
* wired network (bus) &rArr; **no radiofrequency interference, no battery to replace**

Modules are available in two versions:
1. with **DomBus proprietary protocol**, suitable for every type of DomBus modules, working with [Domoticz](https://www.domoticz.com) by using the Creasol DomBus plugin, and [Home Assistant](https://www.home-assistant.io), [OpenHAB](https://www.openhab.org), [Node-RED](https://nodered.org) ... by using the [DomBusGateway software, a DomBus 2 MQTT-AutoDiscovery interface](https://www.creasol.it/DomBusGateway)
2. with **Modbus standard protocol**, suitable for relays modules, EVSE and Dual Axis solar tracker, working with almost any building automation system supporting Modbus

What version is the best? DomBus version, because:

**Modbus** is a standard protocol Master/Slave: the controller must poll each module to get its status, so it's **not suitable to manage inputs and counters that change frequently**, but can be used to manage relay outputs or read inputs status every 2-5s

**DomBus** is a proprietary multi-master protocol where **each module is able to initiate the communication with the master** to notify, for example, an input change, with a short latency (<100ms) that permits to **manage alarm sensors in a reliable way**. Also, DomBus supports the so-called DCMD, **commands exchanged between modules as KNX does**, so it's possible to program simple automations that work between modules even if the domotic controller is OFF (for example, short pulse on button to toggle a light ON/OFF, 1s pulse to open the garage door, 2s pulse to turn OFF some lights, ...)


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
<a href="https://store.creasol.it/DomBus21"><img src="https://images.creasol.it/creDomBus21_size_400.webp" alt="DomBus21 domotic module with 3 latching relays, 1 AC input and 4 low voltage inputs" style="float: left; margin-right: 2em; vertical-align: middle;" align="left" /></a>
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
* Only 15mW power consumption with all relays OFF
* Only 600mW power consumption with all 8 relays ON !!
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
* 12x low voltage inputs (analog/digital inputs, buttons, alarm sensors, **balanced double/triple biased alarm sensors**,  counters, meters, temperature and distance sensors, ...)
* 3x 115/230Vac optoisolated inputs
* 2x relays SPST 5A
* 1x relay SPST 10A
<br clear="all"/>

### DomBus38 - 12 inputs, 1 100-250Vac input, 6 relay outputs
<a href="https://store.creasol.it/DomBus38"><img src="https://images.creasol.it/creDomBus38_400.webp" alt="DomBus38 smart home module with 12 inputs, 1 AC input, 6 SPDT relay outputs + 2 SPDT relay outputs 10A" style="float: left; margin-right: 2em; vertical-align: middle;" align="left" /></a>
Module designed to **interface alarm sensors (magnetc contact sensors, PIRs, tampers), lights and appliances outputs, ...**
* 12x low voltage inputs (analog/digital inputs, buttons, alarm sensors, **balanced double/triple biased alarm sensors**, counters, meters, temperature and distance sensors, ...)
* 1x 115/230Vac optoisolated input to detect power outage and for zero-crossing detection (to switch relays minimizing the in-rush current)
* 4x relays SPDT 10A (with Normally Open and Normally Closed contacts)
* 2x relays SPST 10A (with only Normally Open contacts)
<br clear="all"/>

### DomBusTracker - Dual axis sun tracker controller working with Domoticz, Home Assistant, Node-RED, Modbus, ... and also working in standalone with no external controllers
<a href="https://store.creasol.it/DomBusTracker"><img src="https://images.creasol.it/creDomBusTracker_sun_400.webp" alt="DomBusTracker smart home module that controls 2 linear actuators in a solar tracking system" style="float: left; margin-right: 2em; vertical-align: middle;" align="left" /></a>
Module that **check a deep-hole sun sensor to detect the direction of maximal sun radiation, working also in case of cloudy weather.**
* Controls two external actuators/motors (linear or not) to move motors to reach the best tilt / elevation and azimuth position to optimize photovoltaic production.
* **Check current through the motors to detect internal limit switch** (useful for linear actuators) and find where the tracker reach the final/initial position.
* **Works autonomously** (stand-alone), without any home automation system controller, but **also can be connected to a home automation system using Domoticz, Home Assistant, NodeRED, OpenHAB,** and other systems by using the DomBusGateway software (that converts DomBus protocol to MQTT AutoDiscovery), or with other systems by using DomBusTracker with Modbus firmware.
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


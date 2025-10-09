# DomBusGateway - DomBus 2 MQTT bridge

Developed by Creasol - https://www.creasol.it/domotics

For info about changes in the DomBusGateway features, please check github at https://github.com/creasoltech/DomBusGateway

## TODO
* Periodically update entities for each device

## [Unreleased] 

### Added

### Fixed

## [Unreleased] 

### Added
	Management of NTC 10k with B=3950 coefficient, connected between port and GND:
		port must support this configuration, having the 10k pullup resistor (in some modules, the pullup resistor must be enabled by shorting a PCB jumper):
			telnet localhost 8023 						# connect to dombus gateway
			showmodule ff37								# select the module
			setport N IN_ANALOG,FUNCTION=3950			# configure port a ANALOG with coeff. 3950
		In this case the port is configured as a temperature sensor, showing the temperature in °C

	**--data_dir** parameter to override dataDir variable in _dombusgateway_conf.py_ file: used to set the folder path where 
		Devices and Modules are saved for the next reload (persistent data)

### Fixed

### Changed

### Removed

## [0.3] 2025-09-26 

### Added
* Password for telnet connections coming not from localhost or LAN (password required only for remote IP addresses).
Added telnet['password'] on configuration file and --telnet-pass (or -ts) command line parameter

* Routing of DCMD messages among buses: if a DCMD command from DomBus module X is directed to Dombus module Y, but Y is connected to 
  another bus, DomBusGateway will transmit DCMD command to that bus. Also, the DCMD-ACK will be routed to the opposite path.

## [0.2] 2025-09-24 

### Added
* In line arguments to overwrite configuration set in local/dombusgateway_conf_local.py: execute ```python3 dombusgateway.py -h``` to check available parameters

* Periodically check serial connection, and retry connecting serial ports in case of failure

### Fixed
* Immediate Dombus packet transmission and retry management

### Changed

### Removed

## [0.1] 2025-05-25
First version with initial support.

### Added
* DomBus 

* MQTT-AD

* Telnet



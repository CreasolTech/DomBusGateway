# DomBusGateway - DomBus 2 MQTT bridge

Developed by Creasol - https://www.creasol.it/domotics

For info about changes in the DomBusGateway features, please check github at https://github.com/creasoltech/DomBusGateway

## TODO
* periodically update entities for each device

* Remove payload_on/off from dombusgateway_const.py for SENSOR_ALARM


## [Unreleased] 

### Added
* In line arguments to overwrite configuration set in local/dombusgateway_conf_local.py: execute ```python3 dombusgateway.py -h``` to check available parameters

### Fixed
* Immediate Dombus packet transmission and retry management

### Changed

### Removed

## [0.1] - 2025-05-25
First version with initial support.

### Added
* DomBus 

* MQTT-AD

* Telnet



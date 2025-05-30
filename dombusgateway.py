#!/usr/bin/python3
# DomBusGateway module to manage DomBus home automation modules 
# (relays, inputs, outputs, sensors, EV charging, ...) - https://www.creasol.it/domotics
# Written by Creasol - www.creasol.it
#

VERSION = "0.1"

from dombusgateway_conf import *
import asyncio
import serial_asyncio
if mqtt['enabled'] != 0:
    from aiomqtt import Client as MQTTClient
    import paho.mqtt.client as MQTTpaho

import os
from pathlib import Path
import json
import time
import re
import bisect
import struct
from typing import Any
from datetime import datetime
from queue import Queue

Devices = dict()    # list of all devices (one device for each module port)
Modules = dict()    # list of modules
delmodules = []     # list of frameAddr that must be removed from Modules{}
portsDisabled = dict()   # for each module, list of ports that should be disabled (not shown) # TODO: read configuration from file

def log(level, msg):
    if debugLevel & level:
        logName = DB.LOGNAME[DB.LOG_NONE]
        if level in DB.LOGNAME:
            logName = DB.LOGNAME[level]
        print(f"{datetime.now().strftime('%H:%M:%S.%f')[:-3]} {logName}{msg}")

def getFloat(s):
    """Extract the float value from string. Return None in case of error"""
    try:
        return float(s)
    except (ValueError, TypeError):
        return None

def getInt(s):
    """Extract the integer value from string. Return None in case of error"""
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None

def getHex(s):
    """Extract the integer value from string, in hex format. Return None in case of error"""
    try:
        return int(s, 16)
    except (ValueError, TypeError):
        return None

def devIDName2devID(devIDname: str) -> int:
    """Convert devIDname in the format 013601_0a to the integer value 0x0136010a used as index for Devices"""
    pattern = r'^([0-9a-fA-F]{6})_([0-9a-fA-F]{2})$'
    match = re.fullmatch(pattern, devIDname)
    if match:
        frameAddr, port = match.groups()
        hex_str = frameAddr + port  # Combine to "BBHHHHPP"
        return int(hex_str, 16)
    else:
        return None

######################################## DomBusDevice class ###############################################    
class DomBusDevice():
    """Device class"""
    def __init__(self, devID : int, portType: int, portOpt: int, portName: str, portConf: str, options: dict, haOptions: dict, dcmd: dict = {}, status: dict = {}):
        self.devID = int(devID) # devID=0xBBAAAAPP
        self.busID = devID >> 24
        self.frameAddr = self.devID >> 8     #0xBBAAAA for example 0x01ff38
        self.devAddr = self.frameAddr & 0xffff
        self.port = devID & 0xff
        # self.devIDname = f"b{self.busID:02x}_h{self.devAddr:04x}_p{self.port:02x}"
        self.devIDname = f"{self.frameAddr:06x}_{self.port:02x}"
        self.devIDname2 = ""    # ID name of a second device associated to this, for example a Watt device associated to this kWh device
        self.portType = portType
        self.portOpt = portOpt
        self.portName = portName  # "P01 RL1"
        self.portConf = portConf  # "ID=01ff31_01 OUT_RELAY_LP"
        self.dcmd = dcmd

        self.ha = haOptions.copy()
        if 'p' not in self.ha:
            self.ha['p'] = 'switch'  # default entity platform

        if options:
            self.options = options.copy()
        else:
            self.options = {}
        if 'A' not in self.options:
            self.options['A'] = 1
        if 'B' not in self.options:
            self.options['B'] = 0

        self.lastUpdate = int(time.time())
        self.value = 0      # TODO: retrieve value from file?
        self.valueHA = 'OFF'
        self.counterValue = 0   # counter value
        self.counterTime = 0    # last time a pulse was received (in ms)
        self.energy = 0         # energy in kWh
        self.lastValueHA = 0    # last published value
        self.lastEnergy = 0     # last published energy
        self.lastValueUpdate = 0    # last time that value has been published
        self.lastEnergyUpdate = 0   # last time that energy has been published
        self.lastPortType = 0

        self.setTopics(self.ha['p'], "")  # Set self.topic and self.topic2

        if status:
            self.devIDname2 = status['devIDname2']
            self.value = status['value']
            self.counterValue = status['counterValue']
            self.counterTime = status['counterTime']
            self.energy = status['energy']
            self.topic2 = status['topic2']
            self.topic2Config = status['topic2Config']

        self.lastTopicConfig = self.topicConfig
        self.lastTopic2Config = self.topic2Config


        log(DB.LOG_INFO, f"New device, Bus={self.busID:x}, HWaddr={self.devAddr:04x}, Port={self.port:x}, Type={self.portType:x}{' (' + DB.PORTTYPES_NAME[self.portType] + ') ' if self.portType in DB.PORTTYPES_NAME else ''} Name={self.portName}")
            
    def setTopics(self, platform1, platform2):
        """ Set self.topic, self,topicConfig, self.topic2, self.topic2COnfig """
        self.topic = f"{mqtt['topic']}/{platform1}/{self.devIDname}"
        self.topicConfig = f"{mqtt['topicConfig']}/{platform1}/{self.devIDname}/config"
        if platform2 != "":
            self.topic2 = f"{mqtt['topic']}/{platform2}/{self.devID2name}"
            self.topic2Config = f"{mqtt['topicConfig']}/{platform2}/{self.devID2name}/config"
        else:
            if not hasattr(self, 'topic2'):
                self.topic2 = ""
                self.topic2Config = ""

    def to_dict(self) -> dict[str, Any]:
        """Transform DomBusDevice classes into a dictionary, to be saved in a json file"""
        status = dict(devIDname2 = self.devIDname2, value = self.value, counterValue = self.counterValue, counterTime = self.counterTime, energy = self.energy, topic2 = self.topic2, topic2Config = self.topic2Config)
        return { 
            'devID': self.devID, 'portType': self.portType, 'portOpt': self.portOpt, 'portName': self.portName, 'portConf': self.portConf, 'options': self.options, 
            'ha': self.ha, 'dcmd': self.dcmd, 'status': status
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'DomBusDevice':
        """Transform json data in the file to a dictionary of DomBusDevice devices"""
        return cls(data['devID'], data['portType'], data['portOpt'], data['portName'], data['portConf'], data['options'], data['ha'], data['dcmd'], data['status'])


    def value2valueHA(self):
        """Convert value got from DomBus to a device state compatible with Home Assistant"""
        if self.ha['p'] == 'select':
            self.valueHA = self.ha['options'][int(self.value / 10)]
        elif (self.portType & (DB.PORTTYPE_OUT_DIGITAL | DB.PORTTYPE_OUT_RELAY_LP | DB.PORTTYPE_OUT_LEDSTATUS | DB.PORTTYPE_IN_AC)):
            self.valueHA = 'OFF' if self.value==0 else 'ON'
        elif (self.portType & (DB.PORTTYPE_IN_TWINBUTTON | DB.PORTTYPE_OUT_BLIND)):
            self.valueHA = 'stopped'
            if self.value == 1 or self.value == 10: 
                self.valueHA = 'closing'
            elif self.value == 2 or self.value == 20:
                self.valueHA = 'opening'
        elif self.portType == DB.PORTTYPE_SENSOR_TEMP:
            self.valueHA = (self.value - 2731) / 10.0     # DomBusTH sends Kelvin temperature with 0.1°C resolution
        elif self.portType == DB.PORTTYPE_SENSOR_HUM:
            self.valueHA = self.value / 10.0         # DomBusTH sends relative humdity with 0.1% resolutiom
        elif self.portType & (DB.PORTTYPE_IN_ANALOG | DB.PORTTYPE_SENSOR_DISTANCE): # send value
            self.valueHA = self.value
        elif self.portType == DB.PORTTYPE_SENSOR_TEMP_HUM:
            return  # ignore this kind of sensor (used by Domoticz only)
        elif self.portType == DB.PORTTYPE_IN_COUNTER:
            if self.ha['device_class'] == 'power':
                self.valueHA = self.value   # watt
                if self.valueHA >= 32768:
                    self.valueHA -= 65536   # negative value                                  
                # TODO: also send energy!
            else:
                # plain counter
                self.valueHA = self.counterValue
        elif self.portType == DB.PORTTYPE_OUT_DIMMER:
            # Dimmer: DomBus uses value from 0 to 20 where 20=100%
            self.valueHA = self.value * 5
        elif self.ha['p'] == 'number': 
            self.valueHA = self.value
        elif self.ha['p'] == 'sensor':  # valueHA = value (sensor data)
            self.valueHA = int(self.value * 100) / 100  # 1% precision
            
        else:
            if 'device_class' in self.ha and self.ha['device_class'] in ('door','window'):
                self.valueHA = 'closed' if self.value == 0 or self.value == 2 else 'open'
                log(DB.LOG_DEBUG, f'binary sensor type door: value={self.value}, valueHA={self.valueHA}')
            else:
                self.valueHA = 'Off' if self.value == 0 else 'On'
            
    def updateFromBus(self, what, value:int = None, counterValue:int = None):
        """ Data received from bus: update device and send command to MQTT, ..."""
        global manager
        self.lastUpdate=int(time.time())  # LastUpdate = number of seconds since epoch

        if what & DB.UPDATE_VALUE:
            if value is not None:
                self.value = value * self.options['A'] + self.options['B']
            if counterValue is not None:
                # COUNTER !
                if self.portType == DB.PORTTYPE_CUSTOM and (self.portOpt == DB.PORTOPT_IMPORT_ENERGY or self.portOpt == DB.PORTOPT_EXPORT_ENERGY):
                    self.energy = counterValue
                elif self.portType == DB.PORTTYPE_IN_COUNTER:
                    # value = current counter value
                    # counterValue = previous counter value
                    counter = value - counterValue
                    if counter != 0:
                        if counter < 0 : counter += 65536   # value is a 16bit unsigned variable
                        if counterValue != self.counterValue:
                            # dombusgateway not in sync with DomBus module
                            # most probably dombusgateway has been restarted
                            counter = 0 # prevent to compute power with a very high value
                            

                        self.counterValue = value
                        ms = int(time.time()*1000)
                        if self.ha['device_class'] == 'power':
                            if counter>0 and ms > self.counterTime:
                                self.value = int((counter * 3600000000/ (ms - self.counterTime)) * self.options['A'])  # watt
                                self.energy += counter * self.options['A']  # energy in kWh
                            else:
                                self.value = 0  # Watt
                        self.counterTime = ms
                elif self.portType == DB.PORTTYPE_SENSOR_ALARM:
                    self.energy = counterValue
            
            self.value2valueHA()    # set the valueHA according to value
            if mqtt['enabled'] != 0:
                if self.portType != DB.PORTTYPE_SENSOR_TEMP_HUM and self.portType != DB.PORTTYPE_OUT_LEDSTATUS:    # do not add TEMP+HUM device
                    # send data by MQTT only if it changed, or every publishInterval
                    if self.valueHA != self.lastValueHA or (self.lastUpdate - self.lastValueUpdate) > mqtt['publishInterval']:
                        self.lastValueHA = self.valueHA; self.lastValueUpdate = self.lastUpdate
                        payload = self.valueHA    # message = ON
                        manager.mqttPublish(self.topic + '/state', payload)

                    # if devIDname2 exists => transmit energy value (good also for PORTTYPE_SENSOR_ALARM
                    if self.devIDname2 != "" and (self.energy != self.lastEnergy or (self.lastUpdate - self.lastEnergyUpdate) > mqtt['publishInterval']):
                        # a second entity is associated to this
                        self.lastEnergy = self.energy; self.lastEnergyUpdate = self.lastUpdate
                        if self.portType == DB.PORTTYPE_SENSOR_ALARM:
                            self.energy = int(self.energy)
                            if self.energy > 4: 
                                self.energy = 0
                            payload = DB.SENSOR_ALARM_NAME[ self.energy ]
                        else:
                            payload = int(self.energy * 1000) / 1000    # energy, with Wh resolution
                        manager.mqttPublish(self.topic2 + '/state', payload)
                            

        if what & DB.UPDATE_ACK:
            # Received and ACK to a SET command I sent before. Controller (HA) sent a SET command, now I have to confirm it!
            if mqtt['enabled'] != 0:
                # send state update to the controller 
                if self.portType != DB.PORTTYPE_SENSOR_TEMP_HUM and self.portType != DB.PORTTYPE_OUT_LEDSTATUS:    # do not add TEMP+HUM device
                    payload = self.valueHA    # message = ON
                    manager.mqttPublish(self.topic + '/state', payload)
                        

        if what & DB.UPDATE_CONFIG:
            if mqtt['enabled'] != 0:
                # Create device by MQTT_AD
                if self.portType != DB.PORTTYPE_SENSOR_TEMP_HUM and self.portType != DB.PORTTYPE_OUT_LEDSTATUS:    # do not add TEMP+HUM device
                    if self.portType != self.lastPortType and self.lastTopicConfig != "":
                        # portType changed => remove previous entity by sending config topic with empty payload
                        log(DB.LOG_DEBUG,f'Removing old entity, topic={self.lastTopicConfig}, payload=""')
                        manager.mqttPublish(self.lastTopicConfig, "")
                        if self.lastTopic2Config != "":
                            # portType changed => remove previous entity by sending config topic with empty payload
                            log(DB.LOG_DEBUG,f'Removing old associated entity, topic={self.lastTopic2Config}, payload=""')
                            manager.mqttPublish(self.lastTopic2Config, "")
                        
                    self.setTopics(self.ha['p'], "")    # update current topic
                    payload = dict(name = f"{self.portName}", unique_id = 'dombus_' + self.devIDname, command_topic = f"{self.topic}/set", \
                            state_topic = f"{self.topic}/state", schema = "json")
                    

                    o = {}  # originator
                    o['name'] = 'DomBusGateway'
                    o['sw'] = VERSION
                    o['url'] = 'https://creasol.it/DomBusGateway'
                    payload['o'] = o

                    if self.frameAddr in Modules:
                        dev = {} # device
                        dev['identifiers'] = [ self.frameAddr ]
                        dev['name'] = f"DomBus {self.devAddr:04x}"
                        if self.busID > 1:
                            dev['name'] += f" on bus {self.busID:x}"
                        dev['mf'] = "Creasol"
                        dev['mdl'] = Modules[self.frameAddr][DB.LASTTYPE]
                        dev['sw'] = Modules[self.frameAddr][DB.LASTFW]
                        payload['dev'] = dev
                    if self.ha:
                        payload.update(self.ha)  # Add Home Assistant specific options (platform, device_class, ...
                    if self.portType == DB.PORTTYPE_SENSOR_DISTANCE:
                        if self.options['A'] == 0.1:
                            payload['unit_of_measurement'] = 'cm'
                        elif self.options['A'] == 0.01:
                            payload['unit_of_measurement'] = 'dm'
                        elif self.options['A'] == 0.001:
                            payload['unit_of_measurement'] = 'm'
                        else:
                            payload['unit_of_measurement'] = 'mm'
                    manager.mqttPublish(self.topicConfig, payload)

                    if 'device_class' in self.ha and self.ha['device_class'] == 'power':
                        # set a second entity with energy value
                        payload['p'] = 'sensor' # platform
                        self._initDevice2Config(payload) # init payload, topic2 and topic2 config, send empty payload to remove previous entity
                        payload['device_class'] = 'energy'
                        payload['state_class'] = 'total'
                        payload['unit_of_measurement'] = "kWh"
                        manager.mqttPublish(self.topic2Config, payload)
                    elif self.portType == DB.PORTTYPE_SENSOR_ALARM:
                        # set a second entity showing all sensor statuses: Closed, Open, Masked, Tampered, Shorted
                        payload['p'] = 'select' # platform
                        self._initDevice2Config(payload) # init payload, topic2 and topic2 config, send empty payload to remove previous entity
                        payload['options'] = ['Closed', 'Open', 'Masked', 'Tampered', 'Shorted']
                        manager.mqttPublish(self.topic2Config, payload)
                        self.lastTopic2Config = self.topic2Config
                    else:
                        # No associated device
                        self.devIDname2 = ""
                        self.topic2 = ""
                        self.topic2Config = ""
                        self.lastTopic2Config = ""


        if what & DB.UPDATE_DCMD:
            #TODO: propagate DCMD command
            log(DB.LOG_DEBUG, "*** Send MQTT topic to propagate DCMD ***")

    def _initDevice2Config(self, payload):
        """Called from updateFromBus(DB.UPDATE_CONFIG): init payload, topic2 and topic2 config, send empty payload to remove previous entity"""
        self.devIDname2 = f"{self.frameAddr:06x}_{(self.port + 0x80):02x}"
        self.topic2 = f"{mqtt['topic']}/{payload['p']}/{self.devIDname2}"
        self.topic2Config = f"{mqtt['topicConfig']}/{payload['p']}/{self.devIDname2}/config"
        self.lastTopic2Config = self.topic2Config
        for item in ('device_class', 'state_class', 'unit_of_measurement', 'payload_on', 'payload_off', 'options', 'min', 'max', 'step', 'icon' ):
            if item in payload:
                del payload[item]
        payload['unique_id'] = 'dombus_' + self.devIDname2
        payload['name']=f'{self.portName}_E'
        payload['command_topic'] = f"{self.topic2}/set"
        payload['state_topic'] = f"{self.topic2}/state"


    def updateToBus(self, what:int, valueStr:str = None):
        """ Data received from MQTT: update device and send command to bus"""
        global manager
        if what & DB.UPDATE_VALUE:
            error = False
            if valueStr is not None:
                try:
                    valueArr = json.loads(valueStr)
                except ValueError as e:
                    if type(valueStr) == str:
                        valueHA = valueStr  # maybe it's just a string, like "ON", "OFF", ...
                    else:
                        valueHA = valueStr  # int, digit, ...

                else:
                    if type(valueArr) == dict:
                        if 'state' in valueArr:
                            valueHA = valueArr['state']
                        else:
                            log(DB.LOG_ERR, f"Error on dict passed to updateToBus, not containing 'state' item")
                            error = True
                    else:
                        if type(valueStr) == str:
                            valueHA = valueStr  # maybe it's just a string, like "ON", "OFF", ...
                        else:
                            valueHA = valueStr  # int, digit, ...

                if error == False and type(valueHA) == str:
                    if self.ha['p'] == 'select':
                        try:
                            value = self.ha['options'].index(valueHA)
                        except ValueError:
                            log(DB.LOG_ERR, f"Item {valueHA} not found in select entity {self.portName} {self.devIDname}")
                            error = True
                        else:
                            value *= 10;    # 0: OFF, 10: Solar, 20: 25%, ....

                    elif valueHA in ("OFF", "STOP"):
                        value = 0
                    elif valueHA in ("ON"):
                        value = 1
                    elif valueHA in ("CLOSE"):
                        value = 10
                    elif valueHA in ("OPEN"):
                        value = 20
                    else:
                        try:
                            value = float(valueHA)
                        except ValueError:
                            log(DB.LOG_WARN, f"Invalid value from MQTT: {valueStr}, type={type(valueHA)}")
                            log(DB.LOG_DEBUG, f"ha={self.ha}")
                            error = True
                        else:
                            # valueHA is a float or int
                            self.valueHA = value
                            log(DB.LOG_DEBUG, f"value={value} is float -> valueHA={self.valueHA}")
                            if self.portType == DB.PORTTYPE_OUT_ANALOG:
                                # 0-10.0V step 0.1V
                                value = int(value*10)
                            elif self.portType == DB.PORTTYPE_OUT_DIMMER:
                                # 0 - 100% step 5% => 0 = 0%, 20 = 100%
                                value = int(value/5)
                                if value > 20: 
                                    value = 20
                            else:
                                value = int(value)
                            self.value = value
                elif type(valueHA) == int or type(valueHA) == float:
                    self.valueHA = valueHA
                    self.value = valueHA
                    value = valueHA
                else:
                    log(DB.LOG_ERR, f"Invalid value type from MQTT: value={valueHA}, type={type(valueHA)}")  
                    error = True
                if self.ha['device_class'] == 'power':
                    if value < 0:
                        value += 65536  # Negative power => convert to int(16)
                if error == False:
                    log(DB.LOG_DEBUG, f"TX to DomBus module {self.frameAddr}, on port {self.port}, value={value}")
                    buses[self.busID]['protocol'].txQueueAdd(self.frameAddr, DB.CMD_SET, 2, 0, self.port, [value], DB.TX_RETRY, 1)


        log(DB.LOG_DEBUG, "Call send()...")
        buses[self.busID]['protocol'].send()    # Transmit, if needed


    def updateDeviceConfig(self, newHwAddr: int, newModbusAddr: int, portType: int, portOpt: int, cal: int, dcmd: dict, portConf: str, options: dict, haOptions: dict):
        """Port configuration change requested by the user (via telnet, for example)"""
        diff = 0
        
        self.lastTopicConfig = self.topicConfig     # save previous config topic, used to remove the old entity
        self.lastTopic2Config = self.topic2Config   # save previous config topic, used to remove the old associated entity

        if self.portType != portType:
            self.portType = portType
            if portType in DB.PORTTYPES_HA:
                self.ha = DB.PORTTYPES_HA[portType].copy()  # get platform and device_class from const file
            diff += 1
        if self.portOpt != portOpt:
            self.portOpt = portOpt
            diff += 2
        if dcmd and self.dcmd != dcmd:
            self.dcmd = dcmd.copy()
            diff += 4
        if portConf:
            self.portConf = portConf
        if options:
            self.options = options.copy()
            if 'A' not in self.options:
                self.options['A'] = 1
            if 'B' not in self.options:
                self.options['B'] = 0

        if haOptions:
            self.ha.update(haOptions)
            diff += 16

        if diff & 7:
            # update DomBus module configuration
            log(DB.LOG_INFO, f'Update configuration for DomBus module {self.devIDname}:\r\n  {portConf}')
            buses[self.busID]['protocol'].txQueueAdd(self.frameAddr, DB.CMD_CONFIG, 7, 0, self.port, [((self.portType>>24)&0xff), ((self.portType>>16)&0xff), ((self.portType>>8)&0xff), (self.portType&0xff), (self.portOpt >> 8), (self.portOpt&0xff)], DB.TX_RETRY,0)
            buses[self.busID]['protocol'].send()    # Transmit

        if newModbusAddr and newModbusAddr>0 and newModbusAddr<248:
            Log(DB.LOG_INFO, f"Send command to change modbus device address to {newModbusAddr}")
            buses[self.busID]['protocol'].txQueueAdd(self.frameAddr, DB.CMD_CONFIG, 4, 0, self.port, [DB.SUBCMD_SET, (newModbusAddr>>8), (newModbusAddr&0xff)], DB.TX_RETRY, 1)    #EVSE: until 2023-04-24 port must be replaced with port+5 to permit changing modbus address 
            buses[self.busID]['protocol'].send()    # Transmit

        if cal and cal < 65536: # Transmit calibration or INIT parameter
            buses[self.busID]['protocol'].txQueueAdd(self.frameAddr, DB.CMD_CONFIG, 4, 0, self.port, [DB.SUBCMD_CALIBRATE, (cal>>8), (cal&0xff)], DB.TX_RETRY, 1)   
            buses[self.busID]['protocol'].send()    # Transmit
        
        parName = 'PAR1'; 
        if parName in self.options and self.options[parName] < 65536:
            parValue = self.options[parName]
            buses[self.busID]['protocol'].txQueueAdd(self.frameAddr, DB.CMD_CONFIG, 4, 0, self.port, [DB.SUBCMD_SET, (parValue>>8), (parValue&0xff)], DB.TX_RETRY, 1)
        parName = 'PAR2'; 
        if parName in self.options and self.options[parName] < 65536:
            parValue = self.options[parName]
            buses[self.busID]['protocol'].txQueueAdd(self.frameAddr, DB.CMD_CONFIG, 4, 0, self.port, [DB.SUBCMD_SET2, (parValue>>8), (parValue&0xff)], DB.TX_RETRY, 1)
        parName = 'PAR3'; 
        if parName in self.options and self.options[parName] < 65536:
            parValue = self.options[parName]
            buses[self.busID]['protocol'].txQueueAdd(self.frameAddr, DB.CMD_CONFIG, 4, 0, self.port, [DB.SUBCMD_SET3, (parValue>>8), (parValue&0xff)], DB.TX_RETRY, 1)
        parName = 'PAR4'; 
        if parName in self.options and self.options[parName] < 65536:
            parValue = self.options[parName]
            buses[self.busID]['protocol'].txQueueAdd(self.frameAddr, DB.CMD_CONFIG, 4, 0, self.port, [DB.SUBCMD_SET4, (parValue>>8), (parValue&0xff)], DB.TX_RETRY, 1)
        buses[self.busID]['protocol'].send()    # Transmit
        parName = 'PAR5'; 
        if parName in self.options and self.options[parName] < 65536:
            parValue = self.options[parName]
            buses[self.busID]['protocol'].txQueueAdd(self.frameAddr, DB.CMD_CONFIG, 4, 0, self.port, [DB.SUBCMD_SET5, (parValue>>8), (parValue&0xff)], DB.TX_RETRY, 1)
        buses[self.busID]['protocol'].send()    # Transmit
        parName = 'PAR6'; 
        if parName in self.options and self.options[parName] < 65536:
            parValue = self.options[parName]
            buses[self.busID]['protocol'].txQueueAdd(self.frameAddr, DB.CMD_CONFIG, 4, 0, self.port, [DB.SUBCMD_SET6, (parValue>>8), (parValue&0xff)], DB.TX_RETRY, 1)
        buses[self.busID]['protocol'].send()    # Transmit
        parName = 'PAR7'; 
        if parName in self.options and self.options[parName] < 65536:
            parValue = self.options[parName]
            buses[self.busID]['protocol'].txQueueAdd(self.frameAddr, DB.CMD_CONFIG, 4, 0, self.port, [DB.SUBCMD_SET7, (parValue>>8), (parValue&0xff)], DB.TX_RETRY, 1)
        buses[self.busID]['protocol'].send()    # Transmit
        parName = 'PAR8'; 
        if parName in self.options and self.options[parName] < 65536:
            parValue = self.options[parName]
            buses[self.busID]['protocol'].txQueueAdd(self.frameAddr, DB.CMD_CONFIG, 4, 0, self.port, [DB.SUBCMD_SET8, (parValue>>8), (parValue&0xff)], DB.TX_RETRY, 1)
        buses[self.busID]['protocol'].send()    # Transmit
        parName = 'PAR9'; 
        if parName in self.options and self.options[parName] < 65536:
            parValue = self.options[parName]
            buses[self.busID]['protocol'].txQueueAdd(self.frameAddr, DB.CMD_CONFIG, 4, 0, self.port, [DB.SUBCMD_SET9, (parValue>>8), (parValue&0xff)], DB.TX_RETRY, 1)
        buses[self.busID]['protocol'].send()    # Transmit
        parName = 'PAR10'; 
        if parName in self.options and self.options[parName] < 65536:
            parValue = self.options[parName]
            buses[self.busID]['protocol'].txQueueAdd(self.frameAddr, DB.CMD_CONFIG, 4, 0, self.port, [DB.SUBCMD_SET10, (parValue>>8), (parValue&0xff)], DB.TX_RETRY, 1)
        buses[self.busID]['protocol'].send()    # Transmit
 

        if newHwAddr and newHwAddr>0 and newHwAddr<0xffff:
            log(DB.LOG_INFO, f'Change module address from {self.devAddr:04x} to {newHwAddr}')
            buses[self.busID]['protocol'].txQueueAdd(self.frameAddr, DB.CMD_CONFIG, 4, 0, 0, [(newHwAddr >> 8), (newHwAddr&0xff), (0-(newHwAddr >> 8)-(newHwAddr&0xff)-0xa5)], DB.TX_RETRY,1)
            buses[self.busID]['protocol'].send()    # Transmit
            # Change address to every devices
            devIDbase = (self.busID<<24) | (self.newAddr<<8)    #0xBBNNNN00
            for dev in Devices:
                if (dev & 0xffffff00) == (self.devID & 0xffffff00):
                    d = Devices[dev]
                    d.devID &= 0x000000ff
                    d.devID |= devIDbase
                    d.frameAddr = devIDbase >> 8
                    d.devAddr = d.frameAddr & 0xffff
                    d.devIDname = f"{d.frameAddr:06x}_{d.port:02x}"
                    if d.devIDname2 != "":
                        d.devIDname2 = f"{d.frameAddr:06x}_{(d.port+0x80):02x}"
                    Devices[d.devID] = Devices[self.devID]
                    del Devices[self.devID]


        if diff & 19:
            # update HA configuration
            log(DB.LOG_INFO, f'Update configuration to domotic controller for module {self.devIDname}:\r\n  {portConf}\r\n  {haOptions}')
            self.updateFromBus(DB.UPDATE_CONFIG)


######################################## DomBusProtocol class ###############################################    
class DomBusProtocol(asyncio.Protocol):
    def __init__(self, busID, on_data_received_callback):
        self.busID = busID
        self.devAddr = 0    #0xff31
        self.frameAddr = 0  #0x01ff31       bus|devAddr      used in Modules{}
        self.devID = 0      #0x01ff3101     bus|devAddr|port used in Devices{}
        self.devIDname = "" #b01_hff31_p01
        self.on_data_received_callback = on_data_received_callback
        self.transport = None
        self.buffer = b""   
        self.frame = b""
        self.txbuffer = b""
        self.txQueue = dict()
        self.checksumValue = 0

    def connection_made(self, transport):
        """Called when the connection is made."""
        self.transport = transport
        log(DB.LOG_INFO, f"Connection established on bus {self.busID}.")

    def connection_lost(self, exc):
        """Called when the connection is lost or closed."""
        log(DB.LOG_ERR, f"Connection lost on bus {self.busID}: {exc}")
        

    def setID(self, port):
        """Set frameAddr (01ff31) devID (01ff3101) and devIDname ("b01_hff31_p01")"""
        # Known data: self.busID and self.devAddr
        self.frameAddr = (self.busID << 16) + self.devAddr  # e.g. 0x01ff51 
        self.devID = (self.frameAddr << 8) + port
        self.devIDname = ""
        if port != 0:
            self.devIDname = f"b{self.busID:02x}_h{self.devAddr:04x}_p{port:02x}"

    def data_received(self, data):
        """Called when data is received from the serial port."""
        # log(DB.LOG_DEBUG, f"data_received(): received {len(data)} bytes")
        self.buffer += data
        self._process_buffer() # Frame check and create self.frame
        # log(DB.LOG_DEBUG, f"data_received: exit")

    def dumpRaw(self, frame: bytearray, frameLen: int, logLevel: int):
        """Display raw frame"""
        msg = ""
        for i in range (0,frameLen): 
            msg += f"{frame[i]:02x} "
        log(logLevel, msg)

    def dump(self, frame, frameLen, direction, bus, frameError):
        """Dump frame: frameLen = total frame length"""
        logLevel = DB.LOG_DUMPRX if direction == 'RX' else DB.LOG_DUMPTX    # current type of frame: TX or RX?
        if (debugLevel & DB.LOG_DUMPDCMD) or (debugLevel & logLevel):
            _, dst, src = struct.unpack('>BHH', frame[:5])
            msg = f"{direction} B{bus} {src:04x} -> {dst:04x}"
            i = DB.FRAME_HEADER
            while i < frameLen-1:
                if i+3 > frameLen:
                    msg += " ERROR: cmd length does not fit in frame length"
                    break
                else:    
                    cmd, port, arg = struct.unpack(">BBB", frame[i:i+3])
                    cmdAck = 1 if (cmd & DB.CMD_ACK) else 0
                    cmdLen = (cmd & DB.CMD_LEN_MASK) * 2
                    cmd &= DB.CMD_MASK
                    msg += " "
                    if cmdAck:
                        msg += "A-"
                    if cmd == DB.CMD_CONFIG:
                        msg += 'CFG '
                        if cmdAck and port == 0xfe:
                            # Module version and type
                            msg += f'{port:02x} '
                            for j in range (2, cmdLen+1):
                                if frame[i+j] == 0:
                                    break
                                else:
                                    msg += chr(frame[i+j])
                            msg += ';'
                            i += cmdLen + 1
                            continue
                        if cmdAck and (port & 0xf0) == 0xf0:
                            # whole port configuration => cmdLen without any sense
                            msg += f"{port:02x} {arg:x}"
                            i += 3
                            while i < frameLen-1:
                                portType, portOpt = struct.unpack('>IH', frame[i:i+6])
                                msg += f" {portType:x} {portOpt:x} "
                                i += 6
                                while i < frameLen-1 and frame[i] != 0:
                                    msg += chr(frame[i])
                                    i += 1
                                msg += ';'
                                i += 1
                            log(DB.LOG_DUMPRX, msg)
                            return

                    elif cmd == DB.CMD_SET:
                        msg += 'SET '
                    elif cmd == DB.CMD_GET:
                        msg += 'GET '
                    elif cmd == DB.CMD_DCMD_CONFIG:
                        msg += 'DCMDCFG '
                        logLevel |= DB.LOG_DUMPDCMD
                    elif cmd==DB.CMD_DCMD:
                        msg += 'DCMD '
                        logLevel |= DB.LOG_DUMPDCMD
                    
                    msg += f"P{port} {arg}"
                    i += 1
                    if i+cmdLen >= frameLen:
                        msg += " ERROR: cmd length > frame length"
                        break
                    else:
                        for j in range(2, cmdLen):
                            msg += f" {frame[i + j]}"
                        i += cmdLen
                    msg += ';'
            if frameError == DB.FRAME_INVALID_CHECKSUM:
                msg += ' INVALID CHECKSUM'
                self.dumpRaw(frame, frameLen, logLevel)
            log(logLevel, msg)

    def _checksum(self, buffer, frameLen):
        """Compute checksum value for a frame"""
        self.checksumValue=0
        for i in range(0, frameLen-1):
            self.checksumValue += buffer[i]
        self.checksumValue &= 0xff

    def _process_buffer(self):
        """Process the buffer to extract complete frames."""
        while len(self.buffer) >= DB.FRAME_LEN_MIN:  # Minimum frame size (preamble + addresses + frameLen)
            # Look for the preamble
            if self.buffer[0] != DB.PREAMBLE:
                # Remove the first byte, as it's not the start of a valid frame
                self.buffer = self.buffer[1:]
                continue

            # Parse frame header (preamble, destination, source, frameLen)
            if len(self.buffer) < DB.FRAME_LEN_MIN:
                return  # Not enough data for the header

            _, dst, src, frameLen = struct.unpack(">BHHB", self.buffer[:6])

            # Ensure the full frame is available
            frameLen += DB.FRAME_HEADER + 1  # total length = Header + payload + checksum
            if len(self.buffer) < frameLen:
                return  # Wait for more data

            # Extract the frame
            frame = self.buffer[:frameLen]

            # Verify checksum
            self._checksum(frame, frameLen)
            if self.checksumValue != int(frame[-1]):
                # Checksum error => remove first byte and seek again the preamble
                self.dump(self.buffer, frameLen, 'RX', self.busID, DB.FRAME_INVALID_CHECKSUM)
                self.buffer = self.buffer[1:]
                continue

            # Pass the frame to the callback
            self.on_frame_received_callback(
                self.busID, dst, src, frameLen, frame
            )
            self.send()
            
            self.buffer = self.buffer[frameLen:]  # Remove the frame from the buffer

    def on_frame_received_callback(self, busID, dst, src, frameLen, frame):
        self.busID = busID
        self.devAddr = src
        self.setID(0)
        self.dump(frame, frameLen, 'RX', self.busID, DB.FRAME_OK)
        if src == 0xffff:
            # broadcast
            log(DB.LOG_DEBUG, "Received a broadcast frame")
        elif src == 0:
            # broadcast
            # TODO: remove comment log(DB.LOG_DEBUG, "Received a frame from another controller")
            src = 0 # dummy instruction
        elif dst == 0:
            # frame addressed to me: parse frame
            frameIdx = DB.FRAME_HEADER
            while frameIdx+3 < frameLen:
                portIdx = frameIdx + 1
                cmd, port, arg = struct.unpack(">BBB", frame[frameIdx:frameIdx+3])
                cmdAck = 1 if (cmd & DB.CMD_ACK) else 0
                cmdLen = (cmd & DB.CMD_LEN_MASK) * 2
                cmd &= DB.CMD_MASK
                if cmd == DB.CMD_CONFIG and port != 0xfe and (port & 0xf0) == 0xf0:
                    cmdLen = 4 # cmdLen does not make sense in case of full port configuration
                if cmdLen>=3:
                    arg2 = frame[portIdx+2]
                    if cmdLen >= 4:
                        arg3 = frame[portIdx+3]
                        if cmdLen >= 5:
                            arg4 = frame[portIdx+4]
                            if cmdLen >= 6:
                                arg5 = frame[portIdx+5]
                                if cmdLen >= 7:
                                    arg6 = frame[portIdx+6]
                                    if cmdLen >= 8:
                                        arg7 = frame[portIdx+7]
                                        if cmdLen >= 9:
                                            arg8 = frame[portIdx+8]
                                            if cmdLen >= 10:
                                                arg9 = frame[portIdx+9]
                                                if cmdLen >= 11:
                                                    arg10 = frame[portIdx+10]
                                                    if cmdLen >= 12:
                                                        arg11 = frame[portIdx+11]
                self.setID(port)    # set self.devID and self.devIDname
                self.moduleUpdate() # update modules dictionary to keep trace of running modules
                # check if device exists
                if cmdAck == 0 and self.devID not in Devices:
                    # send frame to ask configuration
                    self.txQueueAskConfig(self.frameAddr)
                else:
                    # module already recognized
                    if cmdAck:
                        # ACK received
                        if self.devID in Devices:
                            Devices[self.devID].updateFromBus(0)    # Only update lastUpdate
                        self.txQueueRemove(self.frameAddr, cmd, port, arg)  # Remove frame from TX queue
                        if cmd == DB.CMD_CONFIG:
                            if port == 0xfe:  # Version
                                if cmdLen >= 8:
                                    strVersion = frame[portIdx+1:portIdx+5].decode()
                                    strModule = frame[portIdx+5:portIdx+cmdLen-1].decode()
                                    log(DB.LOG_INFO, f"Module {strModule} Rev.{strVersion} Bus={self.busID:02x} Addr={self.devAddr:04x}")
                                    Modules[self.frameAddr][DB.LASTTYPE] = strModule # Module type, example "DomBus31"
                                    Modules[self.frameAddr][DB.LASTFW] = strVersion  # Module firmware version, example "02j1"
                                    self.forceTxStatus()    # force transmit output status
                            elif (port & 0xf0) == 0xf0:   #0xff or 0xf0, 0xf1, 0xf2, ...0xfd
                                #arg contains the DB.PORTTYPE_VERSION (to extend functionality in the future)
                                frameIdx = portIdx + 2
                                if arg == 2:    # protocol = 2
                                    if port == 0xff:    
                                        port = 1    # port was 0xff => start configuring port 1
                                    else:
                                        port = arg2   # arg2 set the starting port number (needed to configure dombus devices with several ports)
                                        frameIdx += 1 # start from arg3

                                    while frameIdx < frameLen-1: #scan all ports defined in the frame
                                        self.setID(port)    # set self.devID and self.devIDname
                                        portType, portOpt = struct.unpack(">IH", frame[frameIdx:frameIdx+6])
                                        frameIdx += 6

                                        portName = ""
                                        for i in range(0,16): #get the name associated to the current port
                                            ch = frame[frameIdx]
                                            frameIdx += 1
                                            if ch == 0:
                                                break
                                            else:
                                                portName += chr(ch)

                                        #check if this port device has been disabled
                                        if (self.frameAddr not in portsDisabled) or (port not in portsDisabled[self.frameAddr]):
                                            # this device has not been disabled
                                            if self.devID not in Devices:
                                                portConf = f'ID={self.devIDname},{DB.PORTTYPES_NAME[portType]},{DB.PORTOPTS_NAME[portOpt]}' 

                                                ############################## New device, read from Bus => set default parameters ########################
                                                if portType != DB.PORTTYPE_CUSTOM or portOpt >= 2:
                                                    # do not enable CUSTOM device with DB.PORTOPT not specified (ignore it!)
                                                    if portType == DB.PORTTYPE_CUSTOM:
                                                        if portOpt == DB.PORTOPT_SELECTOR:
                                                            ha['p'] = 'select'  # platform
                                                            if "S.On" in portName:
                                                                ha['options'] = ['Off', 'On']
                                                            elif "S.State" in portName:
                                                                ha['options'] = ['Off', 'On', 'HiCurr', 'LoVolt', 'HiDiss', 'HiDissLoVolt']
                                                        elif portOpt==DB.PORTOPT_DIMMER:
                                                            ha = {'p': 'number', 'min': 0, 'max':100, 'step':1, 'unit_of_measurement': '%'}
                                                            if 'EV Current' in portName:
                                                                ha['max'] = 32
                                                                ha['unit_of_measurement'] = 'A'
                                                        elif portOpt==DB.PORTOPT_LATCHING_RELAY:
                                                            ha['p'] = 'switch'
                                                        elif portOpt==DB.PORTOPT_ADDRESS:
                                                            ha['p'] = 'text'
                                                        elif portOpt==DB.PORTOPT_IMPORT_ENERGY or portOpt==DB.PORTOPT_EXPORT_ENERGY:
                                                            ha['p'] = 'sensor'
                                                            ha['device_class'] = 'power'
                                                            ha['state_class'] = 'measurement'
                                                            ha['unit_of_measurement'] = 'W'
                                                            # sValue="0;0"    #power,energy
                                                            if "Solar" in portName or "Exp" in portName or portOpt==DB.PORTOPT_EXPORT_ENERGY:
                                                                ha['icon'] = 'mdi:solar-power'
                                                        elif portOpt==DB.PORTOPT_VOLTAGE:
                                                            ha['p'] = 'sensor'
                                                            ha['device_class'] = 'voltage'
                                                            ha['unit_of_measurement'] = 'V'
                                                        elif portOpt==DB.PORTOPT_CURRENT:
                                                            ha['p'] = 'sensor'
                                                            ha['device_class'] = 'current'
                                                            ha['unit_of_measurement'] = 'A'
                                                        elif portOpt==DB.PORTOPT_POWER_FACTOR:
                                                            portConf += ",A=0.1"
                                                            ha['p'] = 'sensor'
                                                            ha['device_class'] = 'power_factor'
                                                            ha['unit_of_measurement'] = '%'
                                                        elif portOpt==DB.PORTOPT_FREQUENCY:
                                                            portConf += ",A=0.01"
                                                            ha['p'] = 'sensor'
                                                            ha['device_class'] = 'frequency'
                                                            ha['unit_of_measurement'] = 'Hz'
                                                        elif portOpt==DB.PORTOPT_TOUCH:
                                                            ha['p'] = 'binary_sensor'
                                                            ha['device_class'] = 'motion'
                                                        if "EV State" in portName:
                                                            ha['p'] = 'select'  # platform
                                                            ha['options'] = ['Off', 'Dis', 'Con', 'Ch', 'Vent', 'AEV', 'APO', 'AW']
                                                        elif "EV Mode" in portName:   #Off, Solar, 50%, 75%, 100%, Managed
                                                            ha['p'] = 'select'  # platform
                                                            ha['options'] = ['Off', 'Solar', '25%', '50%', '75%', '100%', 'Man']
                                                            # TODO
                                                            setMaxCurrent=16
                                                            setMaxPower=6000
                                                            setStartPower=1200
                                                            setStopTime=90
                                                            setAutoStart=1
                                                            setMeterType=0
                                                            portConf+=f",EVMAXCURRENT={setMaxCurrent},EVMAXPOWER={setMaxPower},EVSTARTPOWER={setStartPower},EVSTOPTIME={setStopTime},EVAUTOSTART={setAutoStart},ENERGYMETERTYPE=0"
                                                            # nValue=0
                                                            # sValue="0"
                                                            # Configure 
                                                            self.txQueueAdd(self.frameAddr, DB.CMD_CONFIG, 4, 0, port, [DB.SUBCMD_SET, 0, (setMaxCurrent&0xff)], DB.TX_RETRY,0)
                                                            self.txQueueAdd(self.frameAddr, DB.CMD_CONFIG, 4, 0, port, [DB.SUBCMD_SET2, ((setMaxPower>>8)&0xff), (setMaxPower&0xff)], DB.TX_RETRY,0)
                                                            self.txQueueAdd(self.frameAddr, DB.CMD_CONFIG, 4, 0, port, [DB.SUBCMD_SET3, ((setStartPower>>8)&0xff), (setStartPower&0xff)], DB.TX_RETRY,0)
                                                            self.txQueueAdd(self.frameAddr, DB.CMD_CONFIG, 4, 0, port, [DB.SUBCMD_SET4, ((setStopTime>>8)&0xff), (setStopTime&0xff)], DB.TX_RETRY,0)
                                                            self.txQueueAdd(self.frameAddr, DB.CMD_CONFIG, 4, 0, port, [DB.SUBCMD_SET5, ((setAutoStart>>8)&0xff), (setAutoStart&0xff)], DB.TX_RETRY,0)
                                                            # Check if EV MAXCURRENT device exists, with DeviceID=Hxxxx_P0018
                                                            # TODO: create EVMAXCURRENT device
                                                            # evmaxcurrentDevID="{:x}.{:x}".format(frameAddr, 0x104)  # 0x103 => SUBCMD_SET for port number 4
                                                            # Log(LOG_INFO,f"Add virtual device EV MaxCurrent with DeviceID={evmaxcurrentDeviceID}")
                                                            # Domoticz.Device(Name="("+evmaxcurrentDevID+") EV MaxCurrent", TypeName="Setpoint", Type=242, Subtype=1, Options={'ValueStep':'1', 'ValueMin':'6', 'ValueMax':'32', 'ValueUnit':'A'}, DeviceID=evmaxcurrentDeviceID, Unit=UnitFree, Description=f"ID={evmaxcurrentDevID},SETPOINT,TypeName=Setpoint,DESCR=EV Max Current").Create()
                                                            # Devices[UnitFree].Update(nValue=16, sValue="16", Used=1)
                                                            # unit=getDeviceUnit(Devices,1)   # find another free Unit to create EV Mode
                                                    elif portType == DB.PORTTYPE_IN_COUNTER:
                                                        # counter or kWh ?
                                                        # ha['device_class'] = 'energy'
                                                        # ha['state_class'] = 'total_increasing'
                                                        # ha['unit_of_measurement'] = 'kWh'
                                                        portConf += f',DIVIDER=2000'   # Default: 1kW = 2000 pulses => 1 pulse = 0.0005Wh

#                                                    if portType == DB.PORTTYPE_IN_DIGITAL:
#                                                        ha['device_class'] = 'motion' if portName == 'Touch' else 'door'

                                                    self.parseConfiguration(devID, portType, portOpt, portName, portConf)
                                                    # log(DB.LOG_DEBUG, f"DomBusDevice({self.devID:08x}, {portType:x}, {portOpt:x}, P{port:02x} {portName}, {portConf}, {Options}, {ha})")
                                                    # Devices[self.devID] = DomBusDevice(self.devID, portType, portOpt, f"P{port:02x} {portName}", portConf, Options, ha)
                                                    # Devices[self.devID].updateFromBus(DB.UPDATE_VALUE | DB.UPDATE_CONFIG, 0)
                                                    ha.clear()
                                                    Options.clear()

                                        port+=1;
                        elif cmd==DB.CMD_SET:
                            # received a ACK to a SET command: check status
                            if self.devID in Devices:
                                # I sent a SET command, and received the ACK
                                d = Devices[self.devID]
                                if d.portType & (DB.PORTTYPE_OUT_DIGITAL | DB.PORTTYPE_OUT_RELAY_LP | DB.PORTTYPE_OUT_DIMMER | DB.PORTTYPE_OUT_FLASH | DB.PORTTYPE_OUT_ANALOG):
                                    # Update device state taking ACK value (1 byte)
                                    d.value = arg
                                    d.value2valueHA()   # update valueHA 
                                    # log(DB.LOG_DEBUG, f"Received SET+ACK: value={d.value} valueHA={d.valueHA}")
                                d.updateFromBus(DB.UPDATE_ACK, 0)
                    else:
                        #cmdAck==0 => decode command from slave module
                        if src != 0xffff and dst == 0:
                            #Receive command from a slave module
                            if cmd == DB.CMD_CONFIG:
                                if (port&0xf0) == 0xe0: #send text to the log file: port incremented at each transmission
                                    log(DB.LOG_INFO,f"Msg #{port&15} from {self.devIDname}: {frame[portIdx+1:portIdx+cmdLen].decode()}")
                                    self.forceTxStatus() # force transmit output status
                                    self.txQueueAdd(self.frameAddr, cmd, 2, DB.CMD_ACK, port, [arg], 1, 1)
                            elif cmd == DB.CMD_GET:
                                if port==0: #port==0 => request from module to get status of all output!  NOT USED by any module, actually
                                    self.txQueueAdd(self.frameAddr, cmd, 2, DB.CMD_ACK, port, [arg], 1, 1)   #tx ack
                                    self.forceTxStatus() # force transmit output status
                                else: # port specified: return status for that port
                                    if self.devID in Devices:
                                        value = Devices[self.devID].value & 0xff    # TODO: manage counter, temperature, and other values 16-32bits
                                        self.txQueueAdd(self.frameAddr, cmd, 2, DB.CMD_ACK, port, [ value ], 1, 1)
                            elif cmd == DB.CMD_SET:
                                #digital or analog input changed?
                                if self.devID not in Devices:
                                    if self.frameAddr not in portsDisabled or port not in portsDisabled[self.frameAddr]:
                                        #got a frame from a unknown device, that is not disabled => ask for configuration
                                        #Log(LOG_DEBUG,"Device="+devID+" portsDisabled["+str(deviceAddr)+"]="+portsDisabled[deviceAddr]+" => Ask config")
                                        txQueueAskConfig(self.frameAddr)
                                    else:
                                        # ports is disabled => send ACK anyway, to prevent useless retries
                                        #Log(LOG_DEBUG,"Send ACK even if port "+str(port)+" is disabled")
                                        self.txQueueAdd(self.frameAddr, cmd, 2, DB.CMD_ACK, port, [arg], 1, 1)
                                else:
                                    #got a frame from a well known device
                                    d = Devices[self.devID]
                                    counterValue = None   # used to pass a second parameter to updateFromBus() within a counter value or energy
                                    if cmdLen == 2: # cmd, port, arg1
                                        value = arg # 8bit value that have to be set
                                        if d.portType == DB.PORTTYPE_SENSOR_ALARM:  # state: 0=closed, 1=open, 2=masked, 3=tampered, 4=shorted
                                            counterValue = value    # 0 = closed, 1 = open, 2 = masked, 3 = tampered, 4 = shorted

                                    elif cmdLen == 3 or cmdLen == 4:
                                        value = arg*256 + arg2    # 16 bit value
                                        """ TODO: NTC 3950
                                        if d.Type==DB.PORTTYPE[DB.PORTTYPE_SENSOR_TEMP] and value!=0:
                                            if 'function' in d.Options:
                                                Ro=10000.0  # 20230703: float (was int)
                                                To=25.0
                                                temp=0.0  #default temperature # 20230703: float (was int)
                                                if (d.Options['function']=='3950'):
                                                    #value=0..65535
                                                    beta=3950
                                                    if (value==65535): value=65534  #Avoid division by zero
                                                    r=value*Ro/(65535-value)
                                                    temp=math.log(r / Ro) / beta      # log(R/Ro) / beta
                                                    temp+=1.0/(To + 273.15)
                                                    temp=round((1.0/temp)-273.15, 2)
                                            else:
                                                temp=round(value/10.0-273.1,2)
                                                #Log(LOG_DEBUG,"Temperature: value="+str(value)+" temp="+str(temp))

                                            # compute the averaged temperature and save it in d.Options[]
                                            if 'avgTemp' in d.Options:
                                                avgTemp=float(d.Options['avgTemp'])
                                            else:
                                                avgTemp=temp
                                            if abs(avgTemp-temp)>=1.5:
                                                Log(LOG_WARN,f"Temperature warning: Name={d.Name} temp={temp} avgTemp={avgTemp} diff={round(temp-avgTemp,1)}")
                                            Log(LOG_DEBUG,f"Name={d.Name} temp={temp} avgTemp={avgTemp} diff={round(temp-avgTemp,1)} value={value}")
                                            temp=(avgTemp*5+temp)/6
                                            #Log(LOG_DEBUG,"tempDiff<1 => temp=(avgTemp*5+temp)/6="+str(temp))
                                            d.Options['avgTemp']=str(round(temp,2))   #save current avg value, with 2 digit precision

                                            #Now manage A and B
                                            v=getOpt(d,"B=")
                                            b=float(v) if (v!="false") else 0
                                            value=round(temp+b, 1)
                                        elif (d.Type==DB.PORTTYPE[DB.PORTTYPE_SENSOR_HUM]):
                                            hum=int(value/10)
                                            if (hum>5 and d.nValue!=hum):
                                                d.Update(nValue=hum, sValue=HRstatus(hum))
                                        elif d.Type==85: # rain meter
                                            updateCounter(Devices, d, value, 0)
                                        elif (d.Type==243): #distance, voltage, frequency, power factor, watt, ...
                                            if (d.SubType==29): #kWh => signed power
                                                Value=value
                                                if (value&0x8000): Value=value-65536
                                            else:
                                                #extract A and B, if defined, to compute the right value VALUE=A*dombus_value+B
                                                v=getOpt(d,"A=")
                                                a=float(v) if (v!="false") else 1
                                                v=getOpt(d,"B=")
                                                b=float(v) if (v!="false") else 0
                                                Value=a*value+b

                                        """
                                    elif cmdLen == 5 or cmdLen == 6:
                                        value = arg*256 + arg2
                                        value2 = arg3*256 + arg4
                                        if d.portType == DB.PORTTYPE_IN_COUNTER:
                                            counterValue = value2   # pass value and value2 to updateFromBus() that will compute the current power
                                        """
                                        #temp+hum?
                                        if (d.Type==DB.PORTTYPE[DB.PORTTYPE_SENSOR_TEMP_HUM]):
                                            temp=round(value/10.0-273.1,1)
                                            hum=int(value2/10)
                                            stringval=str(float(temp))+";"+str(hum)+";"+HRstatus(hum)
                                            #Log(LOG_DEBUG,"TEMP_HUM: nValue="+str(temp)+" sValue="+stringval)
                                            if (temp>-50 and hum>5 and d.sValue!=stringval):
                                                d.Update(nValue=int(temp), sValue=stringval)
                                            #self.txQueueAdd(frameAddr,CMD_SET,5,CMD_ACK,port,[arg1,arg2,arg3,arg4,0],1,1)
                                            self.txQueueAdd(frameAddr,cmd,2,CMD_ACK,port,[arg1],1,1) #limit the number of data in ACK to cmd|ACK + port
                                        elif d.Type==85: # rain meter
                                            updateCounter(Devices, d, value, value2)
                                        elif (d.Type==243):
                                            updateCounter(Devices, d, value, value2)
                                        """    
                                    elif cmdLen == 7 or cmdLen == 8:
                                        # transmitted power (int16) + energy (uint32)
                                        value = arg*256 + arg2
                                        value2 = (arg3<<24) + (arg4<<16) + (arg5<<8) + arg6
                                        #kWh?
                                        if d.portType == DB.PORTTYPE_CUSTOM and (d.portOpt == DB.PORTOPT_IMPORT_ENERGY or d.portOpt == DB.PORTOPT_EXPORT_ENERGY): #kWh
                                            #value=Watt, signed
                                            #value2=N*10Wh
                                            if (value&0x8000):
                                                value=value-65536
                                            counterValue = value2 / 100     # value2 was in 10Wh unit => convert to kWh
                                    # update device and send ack
                                    self.txQueueAdd(self.frameAddr, cmd, 2, DB.CMD_ACK, port, [ arg ], 1, 1)
                                    d.updateFromBus(DB.UPDATE_VALUE, value, counterValue) # Energy in Wh -> kWh
                            elif cmd == DB.CMD_DCMD and arg<DB.DCMD_OUT_CMDS['MAX']: # DCMD command addressed to me? deactivate/activate/toggle a scene or group
                                log(DB.LOG_INFO,f"Request to activate or deactivate scene/group with idx={port}")
                                switchcmd=''    # TODO: manage scenes by DCMD
                                if arg1==1:
                                    switchcmd='Off'
                                elif arg1==2:
                                    switchcmd='On'
                                elif arg1==3:
                                    switchcmd='Toggle'
                                """ TODO: activate scene on the controller
                                # Domoticz
                                if switchcmd!='':
                                    PARAMS = {'type':'command', 'param':'switchscene', 'idx':str(port), 'switchcmd':switchcmd}
                                    r=requests.get(url = JSONURL, params = PARAMS)
                                    # data = r.json()
                                """
                                self.txQueueAdd(self.frameAddr, cmd, 2, DB.CMD_ACK, port, [arg], 1, 1)
                        else:   # frameaddr==0xffff or dstaddr!=0 => command to another device
                            if cmd == DB.CMD_DCMD and arg<DB.DCMD_OUT_CMDS['MAX']: #DCMD command addressed to another device
                                value = arg2*256+arg3
                                log(DB.LOG_INFO,f"DCMD command from {self.frameAddr:04x} to {self.devAddr:04x}: port={port:02x} cmd={DB.DCMD_OUT_CMDS_Names[arg]} {value}")

                frameIdx = frameIdx + cmdLen + 1
                
    def moduleUpdate(self):
        """Update Modules[self.devID], used to store which Modules have been RXed"""
        if self.frameAddr not in Modules:
            Modules[self.frameAddr] = [ int(time.time()), int(time.time()*1000), int(time.time())+3-DB.PERIODIC_STATUS_INTERVAL, 0, 'N.A.', 'N.A.']
        else:
            Modules[self.frameAddr][DB.LASTRX] = time.time()

    def txQueueAdd(self, frameAddr, cmd,cmdLen,cmdAck,port,args,retries,now):
        #add a command in the tx queue for the specified module (frameAddr)
        #if that command already exists, update it
        #cmdLen=length of data after command (port+args[])
        sec=int(time.time())
        ms=int(time.time()*1000)
        if len(self.txQueue)==0 or frameAddr not in self.txQueue:
            #create self.txQueue[frameAddr]
            self.txQueue[frameAddr]=[[cmd, cmdLen, cmdAck, port, args, retries]]
            #Log(LOG_DEBUG,"self.txQueueAdd (frameAddr does not exist) frameAddr="+hex(frameAddr)+" cmd="+hex(cmd|cmdAck|cmdLen)+" port="+hex(port))
        else:
            found=0
            for f in self.txQueue[frameAddr]:
                #f=[cmd,cmdlen,cmdAck,port,args[]]
                if (f[DB.TXQ_CMD]==cmd and f[DB.TXQ_CMDLEN]==cmdLen and f[DB.TXQ_PORT]==port and (cmd!=DB.CMD_CONFIG or len(args)==0 or args[0]==f[DB.TXQ_ARGS][0])): #if CMD_CONFIG, also check that SUBCMD is the same
                    #command already in txQueue: update values
                    f[DB.TXQ_CMDACK]=cmdAck
                    f[DB.TXQ_ARGS]=args
                    if (f[DB.TXQ_RETRIES]<retries):
                        f[DB.TXQ_RETRIES]=retries
                    found=1
                    break
            if (found==0):
                self.txQueue[frameAddr].append([cmd,cmdLen,cmdAck,port,args,retries])
                #Log(LOG_DEBUG,"txQueueAdd (frame with same cmd,cmdLen... does not exist) frameAddr="+hex(frameAddr)+" cmd="+hex(cmd|cmdAck|cmdLen)+" port="+hex(port))
            #txQueueRetry: don't modify it... transmit when retry time expires (maybe now or soon)
        self.moduleUpdate() # Update Modules[frameAddr]

    def txQueueAskConfig(self, frameAddr):
        self.txQueueAdd(frameAddr, DB.CMD_CONFIG, 1, 0, 0xff, [], DB.TX_RETRY, 1)    #port=0xff to ask full configuration 

    def txQueueRemove(self, frameAddr,cmd,port,arg1):
        # if self.txQueue[frameAddr] esists, remove cmd and port from it.
        # if cmd==255 and port==255 => remove all frames for module frameAddr
        removeItems=[]
        if len(self.txQueue)!=0 and frameAddr in self.txQueue:
            for f in self.txQueue[frameAddr][:]:
                #Log(LOG_DEBUG,"f="+str(f))
                #f=[cmd,cmdlen,cmdAck,port,args[],retries]
                if (((cmd&port)==255) or (f[DB.TXQ_CMD]==cmd and f[DB.TXQ_PORT]==port and (len(f[DB.TXQ_ARGS])==0 or f[DB.TXQ_ARGS][0]==arg1))):
                    self.txQueue[frameAddr].remove(f)


    def forceTxStatus(self):
        """force transmit output status"""
        if self.frameAddr in Modules:
            Modules[self.frameAddr][DB.LASTSTATUS] = 0    #force transmit output status

    def txOutputsStatus(self, frameAddr):
        # transmit the status of outputs for the device frameAddr
        for dev in Devices:
            # dev = 0xBBff51PP where BB=bus number and PP=port number;   frameAddr=0xBBff51
            if (dev >> 8) == frameAddr:
                d=Devices[dev]
                # check that this is an output
                if d.portType & (DB.PORTTYPE_OUT_DIGITAL | DB.PORTTYPE_OUT_RELAY_LP | DB.PORTTYPE_OUT_DIMMER | DB.PORTTYPE_OUT_FLASH | DB.PORTTYPE_OUT_BUZZER | DB.PORTTYPE_OUT_ANALOG):
                    # output! get the port and output state
                    log(DB.LOG_INFO, f"Send periodic status: device={d.devIDname} value={d.value}")
                    #TODO: enable! self.txQueueAdd(frameAddr, DB.CMD_SET, 2, 0, d.port, [d.value], DB.TX_RETRY, 1)

    def send(self):
        """Read txQueue[] and create frames, one for each address, and start transmitting"""
        # txQueue[frameAddr]=[[cmd, cmdLen, cmdAck, port, [arg1, arg2, arg3, ...], retries]]
        tx = 0
        sec = int(time.time())
        ms = int(time.time() * 1000)
        # scan all Modules
        delModules = []
        for frameAddr, module in Modules.items():
            timeFromLastTx = ms-module[DB.LASTTX]        #number of milliseconds since last TXed frame
            timeFromLastRx = sec-module[DB.LASTRX]       #number of seconds since last RXed frame
            timeFromLastStatus = sec-module[DB.LASTSTATUS]     #number of seconds since last TXed output status
            if frameAddr in self.txQueue and len(self.txQueue[frameAddr]) > 0:
                retry = module[DB.LASTRETRY]                         #number of retris (0,1,2,3...): used to compute the retry period
                if retry > DB.TX_RETRY:
                    retry = DB.TX_RETRY
                if timeFromLastTx > (DB.TX_RETRY_TIME << (retry+1)):
                    tx=1
                    self.txbuffer = bytearray()
                    self.txbuffer.append(DB.PREAMBLE)
                    self.txbuffer.append((frameAddr >> 8) & 0xff)       #dstAddr
                    self.txbuffer.append(frameAddr & 0xff)
                    self.txbuffer.append(0)                  #master address
                    self.txbuffer.append(0)
                    self.txbuffer.append(0)                  #length
                    txbufferIndex=DB.FRAME_HEADER
                    # transmit ACK first: build a new queue with all ACK and commands for the selected module frameAddr
                    txQueueNow = []
                    # Transmit ACK first, then commands
                    for txq in self.txQueue[frameAddr][:]:    #iterate a copy of self.txQueue[frameAddr]
                        (cmd, cmdLen, cmdAck, port, args, retry) = txq
                        if cmdAck: txQueueNow.append(txq)
                    for txq in self.txQueue[frameAddr][:]:    #iterate a copy of txQueue[frameAddr]
                        (cmd, cmdLen, cmdAck, port, args, retry) = txq
                        if cmdAck==0: txQueueNow.append(txq)

                    for txq in txQueueNow:    #iterate txQueueNow
                        #[cmd,cmdLen,cmdAck,port,[*args]]
                        (cmd, cmdLen, cmdAck, port, args, retry) = txq
                        if (txbufferIndex+cmdLen+2>=DB.FRAME_LEN_MAX):
                            break   #frame must be truncated
                        self.txbuffer.append((cmd | cmdAck | int((cmdLen+1) / 2)))   #cmdLen field is the number of cmd payload/2, so if after cmd there are 3 or 4 bytes, cmdLen field must be 2 (corresponding to 4 bytes)
                        txbufferIndex += 1
                        self.txbuffer.append(port & 0xff)
                        txbufferIndex += 1
                        for i in range(0, cmdLen-1):
                            self.txbuffer.append((args[i]&0xff))
                            txbufferIndex+=1

                        if (cmdLen&1):  #cmdLen is odd => add a dummy byte to get even cmdLen
                            self.txbuffer.append(0)
                            txbufferIndex+=1

                        # if this cmd is an ACK, or values[0]==1, remove command from the queue
                        if (cmdAck or retry<=1):
                            self.txQueue[frameAddr].remove(txq)
                        else:
                            txq[DB.TXQ_RETRIES] = retry-1   #command, no ack: decrement retry
                    self.txbuffer[DB.FRAME_LEN] = txbufferIndex - DB.FRAME_HEADER
                    module[DB.LASTRETRY] += 1    #increment RETRY to multiply the retry period * 2
                    if (module[DB.LASTRETRY] >= DB.TX_RETRY):
                        module[DB.LASTRETRY] = 4;
                    txbufferIndex += 1  # add 1 to txbufferIndex to include checksum in the frame length
                    self._checksum(self.txbuffer, txbufferIndex)
                    self.txbuffer.append(self.checksumValue)

                    # TODO SerialConn.Send(frameAddr, self.txbuffer)    # frameAddr contains the busID, self.txbuffer the frame ready to be transmitted
                    self.transport.write(self.txbuffer[:txbufferIndex])
                    self.dump(self.txbuffer, txbufferIndex, "TX", frameAddr >> 16, DB.FRAME_OK)
                    Modules[frameAddr][DB.LASTTX] = ms

            else: #No frame to be TXed for this frameAddr
                #check that module is active
                if timeFromLastRx > DB.MODULE_ALIVE_TIME:
                    # too long time since last RX from this module: remove it from Modules
                    if not frameAddr: 
                        frameAddr = 0xffffff  # dummy value to avoid errors
                    log(DB.LOG_INFO,f"Remove module {frameAddr:06x} because it's not alive")
                    delmodules.append(frameAddr)
                    # also remove any cmd in the self.txQueue
                    log(DB.LOG_INFO,"Remove txQueue for {frameAddr:06x}")
                    self.txQueueRemove(frameAddr,255,255,0)
                    # TODO: set device as not available
                    """
                    log(DB.LOG_INFO,"Set devices in timedOut mode (red header) for this module")
                    deviceIDMask="H{:04x}_P".format(frameAddr)
                    for Device in Devices:
                        d=Devices[Device]
                        if (d.Used==1 and d.DeviceID[:7]==deviceIDMask):
                            # device is used and matches frameAddr
                            d.Update(nValue=d.nValue, sValue=d.sValue, TimedOut=1) #set device in TimedOut mode (red bar)
                    """

        for d in delmodules:    #remove module address of died modules (that do not answer since long time (MODULE_ALIVE_TIME))
            if d in Modules:
                del Modules[d]

        if (tx==0): #nothing has been transmitted: send outputs status for device with older lastStatus
            olderFrameAddr=0
            olderTime=sec
            # find the device that I sent the output status earlier
            for frameAddr,module in Modules.items():
                if module[DB.LASTSTATUS]<olderTime:
                    #this is the older device I sent status, till now
                    olderTime = module[DB.LASTSTATUS]
                    olderFrameAddr = frameAddr
            # transmit only the output status of the older device, if last time I transmitted the status was at least PERIODIC_STATUS_INTERVAL seconds ago
            if (sec-olderTime > DB.PERIODIC_STATUS_INTERVAL):
                Modules[olderFrameAddr][DB.LASTSTATUS]=sec+(olderFrameAddr&0x000f)   #set current time + extra seconds to avoid all devices been refresh together
                #Log(LOG_DEBUG,"send(): Transmit outputs Status for "+hex(olderFrameAddr))
                self.txOutputsStatus(olderFrameAddr)



class DomBusManager:
    def __init__(self):
        self.loop = asyncio.get_event_loop()
        self.mqttConnected = False
        self.mqttPublishQueue = Queue() # Queue for MQTT messages
        self.selectedBus = 1        # default bus selected for command line interface (telnet)
        self.selectedModule = 0     # address of module selected by CLI (telnet)

        self.commands = {
            'help':     { 
                'cmd': self.cmd_help,     
                'help': 'Print this help. Type "help CMD" to get info about the specified cmd' },
            'refresh':   {
                'cmd': self.cmd_refresh,
                'help': 'Send list of all devices to the domotic controller',   },
            'showbus':  { 
                'cmd': self.cmd_showbus,
                'help': 'Show the list of available buses\r\nSpecify a bus to show modules attached to that bus, e.g. "showbus 1"' }, 
            'showmodule':   { 
                'cmd': self.cmd_showmodule, 
                'help': 'Show data about the specified module: e.g. "showmodule ffe3"' },
            'setport':  {
                'cmd': self.cmd_setport,
                'help': 'Configure the specified port: "showbus" and "showmodule" commands have to be invoked\r\nto select the module to be configured. Examples:\r\n"setport 01 IN_ANALOG,A=0.00042" to set port 1 as analog input, specifying the A coefficient\r\n"setport 02 IN_DIGITAL,INVERTED" to set port 2 as digital input with inverted logic\r\n(On when port 2 is pulled to GND, Off when left open)' },
        }

    async def add_bus(self, busID, port, baudrate=115200):
        """Add a new serial bus."""
        if busID in buses and 'protocol' in buses[busID]:
            raise ValueError(f"Bus ID {busID} already exists.")

        def on_data_received(busID, data):
            """Callback for handling received data."""
            # Parse and handle the message here
        
        log(DB.LOG_INFO, f"Connecting DomBus {busID} on port {port} {baudrate}bps ...")
        transport, protocol = await serial_asyncio.create_serial_connection(
            self.loop,
            lambda: DomBusProtocol(busID, on_data_received),
            port,
            baudrate=baudrate,
        )
        buses[busID]['protocol'] = protocol
        log(DB.LOG_DEBUG, f"Bus {busID} added on port {port}.")

    def remove_bus(self, busID):
        """Remove a bus by its ID."""
        if busID in buses and 'protocol' in buses[busID]:
            buses[busID]['protocol'].transport.close()
            del buses[busID]['protocol']
            log(DB.LOG_DEBUG, f"Bus {busID} removed.")
        else:
            log(DB.LOG_WARN, f"Bus ID {busID} does not exist.")

    def stop_all_buses(self):
        """Stop all buses."""
        for busID in list(buses.keys()):
            self.remove_bus(busID)

    async def add_mqtt(self):
        """Connect to the MQTT broker and set up subscriptions."""

        try:
            log(DB.LOG_INFO, f"Connecting to MQTT broker using AIOMQTT at {mqtt['host']}:{mqtt['port']}")
            mqtt['client'] = MQTTClient(mqtt['host'], mqtt['port'], username = mqtt['user'], password = mqtt['pass'])
            await mqtt['client'].__aenter__()
            self.mqttConnected = True

            # Start the publishing task
            self.loop.create_task(self._mqttPublishFromQueue())
            # Start the subscription task
            self.loop.create_task(self._mqttSubscribe())

        except Exception as e:
            log(DB.LOG_ERR, f"Failed to connect to MQTT broker: {e}")

    async def mqttDisconnect(self):
        await mqtt['client'].__aexit__(None, None, None)
        self.mqttConnected = False

    async def _mqttSubscribe(self):
        """Subscribe to all topics asynchronously."""
        topics = f'{mqtt["topic"]}/#'
        await mqtt['client'].subscribe(topics, options={"no_local": True})  # Subscribe to all topics
        log(DB.LOG_INFO, f"Subscribed to topics {topics}")

        async for message in mqtt['client'].messages:
            if str(message.topic)[-6:] != '/state' and '"_sender": "dbp"' not in message.payload.decode():  # ignore msg generated by me, and state messages (only commands should be received)
                log(DB.LOG_MQTTRX, f"Received on {message.topic}: {message.payload.decode()}")
                # check topic  /dombus/platform/devID/set
                f = str(message.topic).split('/')
                if len(f)>=4 and f[0] == mqtt['topic']:

                    devID = devIDName2devID(f[2])
                    if devID and devID in Devices:
                        # Device exists
                        d = Devices[devID]
                        d.updateToBus(DB.UPDATE_VALUE, message.payload.decode())
                    else:
                        log(DB.LOG_MQTTRX, f"Unknown device {devID}")
                else:
                    log(DB.LOG_MQTTRX, "received topic not in valid format")
                

    async def _mqttPublishFromQueue(self):
        """Process the publish queue asynchronously."""
        while self.mqttConnected:
            topic, message = await self.loop.run_in_executor(None, self.mqttPublishQueue.get)
            # Publish the message
            log(DB.LOG_MQTTTX, f"Publish to {topic}: {message}")
            await mqtt['client'].publish(topic, message, qos=1)
            self.mqttPublishQueue.task_done()

    def mqttPublish(self, topic: str, payload: any):
        """Send message to a queue, to send it asyncronously"""
        if isinstance(payload, (dict, list)):
            payload['_sender'] = 'dbp'  # add a tag to identify msg sent by me, to ignore loopback mqtt commands 
            message = json.dumps(payload)
        else:
            message = str(payload)
        self.mqttPublishQueue.put((topic, message))

    async def addTelnetServer(self):
        """Listen to a TCP port to receive commands by Telnet"""

        telnetServer = await asyncio.start_server(
            self.handleTelnetConnection,
            telnet['address'],
            telnet['port'],
        )
        telnet['clients'] = {}  # init void list of clients
        log(DB.LOG_INFO, f"Listening on telnet port {telnet['port']} interface {telnet['address']}")

    async def handleTelnetConnection(self, reader, writer):
        """Manage telnet connections"""
        clientIP = writer.get_extra_info('peername')[0]
        log(DB.LOG_INFO, f"New telnet connection from {clientIP}")
        telnet['clients'][writer] = dict(reader = reader, writer = writer, ip = clientIP)
        writer.write(b'Welcome to DomBusGateway telnet interface\r\nType help to get a list of commands\r\nMore info at https://www.creasol.it/DomBusGateway\r\n> ')
        await writer.drain()

        try:
            while True:
                data = await reader.read(1024)
                if not data:
                    break
                """ handle UP/DOWN arrows...
                if data == b'\xff':  # IAC (Interpret As Command)
                    # Read the next two bytes for telnet command
                    cmd = await reader.read(2)
                    if cmd == b'\xfd\x18':  # Ctrl+C
                        break
                    elif cmd in (b'\xfd\x20', b'\xfd\x21'):  # Arrow keys prefix
                        arrow = await reader.read(1)
                        await self.handle_arrow_key(arrow, writer)
                    continue
                """
                message = data.decode().strip()
                log(DB.LOG_TELNET, f"Received {message}")
                await self.handleCmd(message, writer) # parse commands

        except ConnectionResetError:
            log(DB.LOG_INFO, f"Telnet connection closed by {clientIP}")
        finally:
            del telnet['clients'][writer]
            writer.close()
            await writer.wait_closed()


    async def handleCmd(self, message, writer):
        """Handle commands received from telnet port"""
        cmd = message.split(maxsplit=2) # ['show', 'module', '0xffe3 on bus 1']
        if len(cmd)>=1 and cmd[0] in self.commands:
            await self.commands[cmd[0]]['cmd'](cmd[1:], writer)
        else:
            writer.write(b'Invalid command: please type "help" for a list of commands\r\n> ') 
        writer.write(b'\r\n> ')
        await writer.drain()


    async def cmd_help(self, args, writer):
        """Send back an help text"""
        if args and args[0] in self.commands:
            writer.write(f'{self.commands[args[0]]['help']}\r\n'.encode())
        else:
            writer.write(f'This interface permits to check and set configuration for a DomBus network of home automation modules.\r\nAvailable commands:\r\n'.encode())
            for cmd in self.commands:
                hs=re.sub('\r\n', '\r\n           ', self.commands[cmd]['help'])
                writer.write(f'{cmd:10} {hs}\r\n\r\n'.encode())

    async def cmd_refresh(self, args, writer):
        """Send whole list of devices to the domotic controller"""
        dlist = []
        for dev in Devices: # sort by devID
            bisect.insort(dlist, dev)
        for dev in dlist:
            d = Devices[dev]
            if (dev >> 8) in Modules:
                writer.write(f'Sending configuration refresh for device {d.devIDname} portType={d.portType:08x} platform={d.ha["p"]}...\r\n'.encode())
                d.updateFromBus(DB.UPDATE_CONFIG)
            else:
                writer.write(f'Skip sending configuration for device {d.devIDname}: module {(dev >> 8):06x} not alive or not received yet!\r\n'.encode())
        del dlist            

    async def cmd_showbus(self, args, writer):
        """Show list of buses, or parameter of the selected bus"""
        bus = 0
        if args:
            try:
                bus = int(args[0], 16)
            except ValueError:
                writer.write(b"Invalid typed bus\r\n")
                bus = 0

        if bus != 0 and bus in buses:
            # Show modules attached to the selected bus
            self.selectedBus = bus
            self.showModuleList(writer)
        else:
            # Show list of buses
            writer.write(f'Available buses:\r\n'.encode())
            for b in buses:
                writer.write(f'- {b:02x}: {buses[b]['serialPort']:20} {"CONNECTED" if 'protocol' in buses[b] else "DISCONNECTED"}\r\n'.encode())


    async def cmd_showmodule(self, args, writer):
        """Show list of modules for the selected bus, or parameters of the selected module"""
        module = 0
        if args:
            try:
                module = int(args[0], 16)
            except ValueError:
                module = 0
                writer.write(b"Invalid module address\r\n")
        frameAddr = module + (self.selectedBus << 16)
        if module != 0 and frameAddr in Modules:
            # List all devices with the same address of module
            self.selectedModule = module
            self.showDeviceList(writer)
        else:
            self.showModuleList(writer)

    async def cmd_setport(self, args, writer):
        """Configure a port for the specified module"""
        port = 0
        if args:
            try:
                port = int(args[0], 16)
            except ValueError:
                port = 0
                writer.write(b"Invalid port\r\n")
        if (port != 0):
            devID = (self.selectedBus << 24) + (self.selectedModule << 8) + port
            if devID in Devices:
                # Device exists: check new configuration 
                self.parseConfiguration(devID, Devices[devID].portType, Devices[devID].portOpt, "", args[1])

            else:
                if self.selectedModule == 0 or (devID>>8) not in Modules: 
                    writer.write(b'Please select an existing module with command "showmodule XXXX"\r\n')
                    self.showModuleList(writer)
                else:
                    writer.write(f'Device {self.selectedModule:04x} on bus {self.selectedBus:x} does not have port {port}\r\n'.encode())
                    self.showDeviceList

    def showModuleList(self, writer):
        """Show modules attached to self.selectedBus"""
        writer.write(f'Modules attached to bus {self.selectedBus}: use "showbus BUS" to select another bus\r\n     Bus     Address Type      Version LastRX\r\n'.encode())
        mlist = []
        for m in Modules:
            if (m >> 16) == self.selectedBus:   # same bus!
                bisect.insort(mlist, m)         # add module to a sorted list mlist
        for m in mlist:
            elapsedTime = int(time.time() - Modules[m][DB.LASTRX])
            writer.write(f'- Bus {self.selectedBus:02x} Module {(m & 0xffff):04x} {Modules[m][DB.LASTTYPE]:10} {Modules[m][DB.LASTFW]:6} {elapsedTime}s\r\n'.encode())
        del mlist

    def showDeviceList(self, writer):
        writer.write(f"Devices (ports) for the selected module {self.selectedModule:04x} on bus {self.selectedBus:02x}:\r\n".encode())
        devIDbase = (self.selectedBus << 24) + (self.selectedModule << 8)
        for p in range(1, 256):
            devID = devIDbase + p
            if devID in Devices:
                writer.write(f'- {Devices[devID].portName:14} {Devices[devID].portConf}\r\n'.encode())

    def parseConfiguration(self, devID, portType, portOpt, portName, confString):
        """Received a configuration string from the user: update configuration on both Devices and DomBus module"""
        # confString: "ID=01ff37_01,IN_DIGITAL,INVERTED,DCMD(Pulse)=01ff36_07:Toggle,DCMD(Pulse1)=01ff36_08:Toggle"
        devIDname = f"{(devID >> 8):06x}_{(devID & 0xff):02x}"
        portConfName = ""   # Other parameters to write in portConf, else than portType and portOpt
        newHwAddr = 0       # Used to change module address
        newModbusAddr = 0   # Used to change the Modbus slave address of a meter
        dcmd = {}           # Used to set DCMD configuration
        options = {}
        haOptions = {}
        cal = None
        for cmd in confString.split(','):
            cmdu = cmd.upper().strip()
            cmdeq = cmdu.split('=')
            if cmdu in DB.PORTTYPES:
                # IN_DIGITAL or OUT_RELAY_LP or other port configuration
                portType = DB.PORTTYPES[cmdu]
            elif cmdu in DB.PORTOPTS:
                # INVERTED, NORMAL, PULLUP, ....
                portOpt = DB.PORTOPTS[cmdu]
            elif cmdeq[0] == "HWADDR":    # Request to change Modbus address of a meter
                par = getHex(cmdeq[1])
                if par and par > 0 and par < 65535:  
                    newHwAddr = par
            elif cmdeq[0] == "ADDR":    # Request to change Modbus address of a meter
                par=getInt(cmdeq[1])
                if par and par >= 1 and par <= 5:   # only 4 devices are supported
                    newModbusAddr = par
            elif cmdeq[0] == 'A':
                par = getFloat(cmdeq[1])
                if par:
                    options['A'] = par
                    portConfName += f',A={par}'
            elif cmdeq[0] == 'B':
                par = getFloat(cmdeq[1])
                if par:
                    options['B'] = par 
                    portConfName += f',B={par}'
            elif cmdeq[0] == 'CAL':
                # calibration value, e.g. 0.2
                par = getFloat(cmdeq[1])
                if par:
                    cal = int(par * 10)
            elif cmdeq[0] == 'INIT':
                # configuration value, integer
                par = getInt(cmdeq[1])
                if par:
                    cal = par
                    portConfName += f',{cmdeq[0]}={cmdeq[1]}'
            elif cmdeq[0] == 'FUNCTION':
                # used to convert an analog value to another
                options = {'function' : cmdeq[1]}
                portType = DB.PORTTYPE_IN_ANALOG
                if options['function'] == '3950':
                    # NTC sensor with B=3950 => temperature
                    ha.update(DB.PORTTYPES_HA[DB.PORTTYPE_SENSOR_TEMP]) # set parameters for this type of sensor
                    portConfName += f",{cmdeq[0]}={cmdeq[1]}"
            elif cmdeq[0] == "OPPOSITE":  #Used with kWh meter to set power to 0 when the opposite counter received a pulse (if import power >0, export power must be 0, and vice versa)
                if portType == DB.PORTTYPE_IN_COUNTER:
                    opposite=devIDName2devID(cmdeq[1])   # syntax: OPPOSITE=013701_02
                    if opposite and Device[opposite].portType == DB.PORTTYPE_IN_COUNTER:    # Opposite devID exists and it's a counter!
                        options['opposite'] = opposite
                        Devices[opposite].options['opposite'] = devID  # also set opposite on the other device!
                        if ',OPPOSITE=' not in Device[opposite].portConf:
                            Device[opposite].portConf += f',OPPOSITE={devID}'
                        portConfName += f",{cmdeq[0]}={cmdeq[1]}"
            elif cmdeq[0] == "DIVIDER": #Used with kWh meter to set how many pulses per kWh, e.g. 1000 (default), 2000, 1600, ...
                if portType == DB.PORTTYPE_IN_COUNTER:
                    par = getInt(cmdeq[1])
                    if par and par != 0:
                        options['A'] = 1 / par
                        portConfName += f",{cmdeq[0]}={cmdeq[1]}"
            elif cmdeq[0] in ('PAR1', 'PAR2', 'PAR3', 'PAR4'):
                par = getInt(cmdeq[1])
                if par and par < 65536:
                    options[cmdeq[0]] = par
                    portConfName += f",{cmdeq[0]}={par}"
            elif cmdeq[0] == "EVMAXCURRENT" and portType == DB.PORTTYPE_CUSTOM:    
                par = getInt(cmdeq[1])
                if par == None or par<6 or par>36:
                    par = 16    # default
                options['PAR1'] = par 
                portConfName += f",{cmdeq[0]}={par}"
            elif cmdeq[0] == "EVMAXPOWER" and portType == DB.PORTTYPE_CUSTOM:    
                par = getInt(cmdeq[1])
                if par == None or par<1000 or par>25000:
                    par = 6000    # default
                options['PAR2'] = par 
                portConfName += f",{cmdeq[0]}={par}"
            elif cmdeq[0] == "EVMAXPOWER2" and portType == DB.PORTTYPE_CUSTOM:    
                par = getInt(cmdeq[1])
                if par == None or par<1000 or par>25000:
                    par = 6000    # default
                options['PAR6'] = par 
                portConfName += f",{cmdeq[0]}={par}"
            elif cmdeq[0] == "EVMAXPOWERTIME" and portType == DB.PORTTYPE_CUSTOM:    
                par = getInt(cmdeq[1])
                if par == None or par<60 or par>43200:
                    par = 0    # default
                options['PAR7'] = par 
                portConfName += f",{cmdeq[0]}={par}"
            elif cmdeq[0] == "EVMAXPOWER2TIME" and portType == DB.PORTTYPE_CUSTOM:    
                par = getInt(cmdeq[1])
                if par == None or par<60 or par>43200:
                    par = 0    # default
                options['PAR8'] = par 
                portConfName += f",{cmdeq[0]}={par}"
            elif cmdeq[0] == "EVSTARTPOWER" and portType == DB.PORTTYPE_CUSTOM:    
                par = getInt(cmdeq[1])
                if par == None or par<800 or par>25000:
                    par = 1200    # default
                options['PAR3'] = par 
                portConfName += f",{cmdeq[0]}={par}"
            elif cmdeq[0] == "EVSTOPTIME" and portType == DB.PORTTYPE_CUSTOM:    
                par = getInt(cmdeq[1])
                if par == None or par<5 or par>600:
                    par = 90    # default
                options['PAR4'] = par 
                portConfName += f",{cmdeq[0]}={par}"
            elif cmdeq[0] == "EVAUTOSTART" and portType == DB.PORTTYPE_CUSTOM: 
                par = getInt(cmdeq[1])
                if par == None or par>1:
                    par = 1    # default
                options['PAR5'] = par 
                portConfName += f",{cmdeq[0]}={par}"
            elif cmdeq[0] == "EVWAITTIME" and portType == DB.PORTTYPE_CUSTOM:    
                par = getInt(cmdeq[1])
                if par == None or par<3 or par>60:
                    par = 6    # default
                options['PAR9'] = par 
                portConfName += f",{cmdeq[0]}={par}"
            elif cmdeq[0] == "EVMETERTYPE" and portType == DB.PORTTYPE_CUSTOM:
                par = getInt(cmdeq[1])
                if par == None or par>1:
                    par = 0    # default
                options['PAR10'] = par 
                portConfName += f",{cmdeq[0]}={par}"
            # TODO: DCMD    

            portConf = f'ID={devIDname},{DB.PORTTYPES_NAME[portType]}'
            if portOpt != 0:
                portConf += f',{DB.PORTOPTS_NAME[portOpt]}'
            portConf += f',{portConfName}'
            if devID not in Devices:
                # device object does not exist => create it
                portName = f'P{(devID & 0xff):02x} {portName}'
                Devices[devID] = DomBusDevice(devID, portType, portOpt, portName, portConf, options, haOptions) # Create device object with minimal configuration

            Devices[devID].updateDeviceConfig(newHwAddr, newModbusAddr, portType, portOpt, cal, dcmd, portConf, options, haOptions)  # Update configuration (setting CAL, DCMD, device_class, ...)
                

####################################################################### main #################################################################################

if __name__ == "__main__":
    async def main():
        global manager
        manager = DomBusManager()

            
        for bus in buses:
            try: 
                await manager.add_bus(busID=bus, port=buses[bus]['serialPort'], baudrate=115200)
            except Exception as e:
                log(DB.LOG_ERR, f"Error opening serial port {buses[bus]['serialPort']}: {e}")
                log(DB.LOG_ERR, "Skip this serial port!")

        if mqtt['enabled'] != 0:
            # await manager.add_mqtt()
            asyncio.create_task(manager.add_mqtt())

        if telnet['enabled'] != 0:
            # listen to TCP port waiting for connections and commands
            asyncio.create_task(manager.addTelnetServer())
        
        #await asyncio.sleep(150)  # Terminate in 15 seconds
        await asyncio.Event().wait()

    ############### main ################
    # check that data directory exists
    dataPath = Path(datadir)
    dataPath.mkdir(parents=True, exist_ok=True)

    modulesPath = dataPath / 'Modules.json'
    devicesPath = dataPath / 'Devices.json'

    # load saved data
    tempdict = {}
    if modulesPath.exists():
        with open(modulesPath, 'r', encoding='utf-8') as f:
            tempdict = json.load(f)
            Modules = {int(k): v for k, v in tempdict.items()}
    if devicesPath.exists():
        with open(devicesPath, 'r', encoding='utf-8') as f:
            tempdict = json.load(f)
            Devices = {int(k): DomBusDevice.from_dict(v) for k, v in tempdict.items()}
    del tempdict

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log(DB.LOG_INFO, "Keyboard interrupt => exit")
        
    # save data 
    with open(modulesPath, 'w', encoding='utf-8') as f:
        json.dump(Modules, f, indent=2)
    with open(devicesPath, 'w', encoding='utf-8') as f:
        json.dump({k: v.to_dict() for k, v in Devices.items()}, f, indent=2)


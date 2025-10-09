#!/usr/bin/python3
# DomBusGateway module to manage DomBus home automation modules 
# (relays, inputs, outputs, sensors, EV charging, ...) - https://www.creasol.it/domotics
# Written by Creasol - www.creasol.it
#

VERSION = "0.4-pre2"

from dombusgateway_conf import *

import logging
from logging.handlers import RotatingFileHandler

import asyncio
import serial_asyncio
if mqtt['enabled'] != 0:
    mqttversion='old'
    try:
        from asyncio_mqtt import Client as MQTTClient
    except:
        from aiomqtt import Client as MQTTClient
        mqttversion='new'
    import paho.mqtt.client as MQTTpaho
    from paho.mqtt.subscribeoptions import SubscribeOptions

import os
import signal
import sys
from pathlib import Path
import json
import time
import re
import bisect
import struct
import math
from typing import Any
import datetime
from queue import Queue

import argparse
import ipaddress

Devices = dict()    # list of all devices (one device for each module port)
Modules = dict()    # list of modules
delmodules = []     # list of frameAddr that must be removed from Modules{}
portsDisabled = dict()   # for each module, list of ports that should be disabled (not shown) # TODO: read configuration from file
saveDataTimeout = 0 # Used to determine if device configuration changes, in that case call saveData() to save Modules and Devices structures in filesystem

def log(level, msg):
    if debugLevel & level:
        logName = DB.LOGNAME[DB.LOG_NONE]
        if level in DB.LOGNAME:
            logName = DB.LOGNAME[level]
        logging.info(f"{logName}{msg}")

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
    """Convert devIDname in the format 013601_000a to the integer value 0x013601000a used as index for Devices"""
    try:
        devID = int(devIDname.replace('_', ''), 16)
    except Exception as e:
        log(DB.LOG_WARN, f"Error converting devIDname={devIDname} to devID (integer): {e}")
        return None
    else:
        return devID

def setSaveDataTimeout():
    """Set saveDataTimeout: next time that Modules and Devices structures must be saved due to new device configuration or new device in the bus"""
    global saveDataTimeout
    saveDataTimeout = datetime.datetime.now() + datetime.timedelta(seconds=DB.SAVE_DATA_TIMEOUT)
    log(DB.LOG_DEBUG,"####### Set saveDataTimeout ")

######################################## DomBusDevice class ###############################################    
class DomBusDevice():
    """Device class"""
    def __init__(self, devID : int, portType: int, portOpt: int, portName: str, options: dict, haOptions: dict, dcmd: list = [],  status: dict = {}, dcmdConf: str = ""):
        self.devID = int(devID) # devID=0xBBAAAAPPPP
        self.busID = devID >> 32
        self.frameAddr = self.devID >> 16     #0xBBAAAA for example 0x01ff38
        self.devAddr = self.frameAddr & 0xffff
        self.port = devID & 0xffff
        # self.devIDname = f"b{self.busID:02x}_h{self.devAddr:04x}_p{self.port:02x}"
        self.devIDname = f"{self.frameAddr:06x}_{self.port:04x}"
        self.devIDname2 = ""    # ID name of a second device associated to this, for example a Watt device associated to this kWh device
        self.portType = portType
        self.portOpt = portOpt
        self.portName = portName  # "P01 RL1"
        self.dcmd = dcmd
        self.dcmdConf = dcmdConf
        self.ha = {}

        if options:
            self.options = options.copy()
        else:
            self.options = {}
        if 'A' not in self.options:
            self.options['A'] = 1
        if 'B' not in self.options:
            self.options['B'] = 0

        if portType in DB.PORTTYPES_HA:
            self.ha = DB.PORTTYPES_HA[portType].copy()  # get platform and device_class from const file
        if 'p' not in self.ha:
            self.ha['p'] = 'switch'  # default entity platform
        if haOptions:
            self.ha.update(haOptions)

        self.setPortConf() # write configuration string self.portConf=IN_DIGITAL,PULLUP,INVERTED,...
        self.lastUpdate = int(time.time())
        self.value = 0          # later, retrieve value from file
        self.valueHA = ''
        self.counterValue = 0   # counter value
        self.counterTime = 0    # last time a pulse was received (in ms)
        self.energy = 0         # energy in kWh
        self.lastValue = 0
        self.lastValueHA = 0    # last published value
        self.lastEnergy = 0     # last published energy
        self.lastValueUpdate = 0    # last time that value has been published
        self.lastEnergyUpdate = 0   # last time that energy has been published
        self.lastPortType = self.portType

        self.setTopics(self.ha['p'], "")  # Set self.topic and self.topic2

        if status:
            self.devIDname2 = status['devIDname2']
            self.value = status['value']
            self.valueHA = status['valueHA']
            self.counterValue = status['counterValue']
            self.counterTime = status['counterTime']
            self.energy = status['energy']
            self.topic2 = status['topic2']
            self.topic2Config = status['topic2Config']

        self.lastTopicConfig = self.topicConfig
        self.lastTopic2Config = self.topic2Config


        log(DB.LOG_INFO, f"New device, Bus={self.busID:x}, HWaddr={self.devAddr:04x}, Port={self.port:x}, Type={self.portType:x}{' (' + DB.PORTTYPES_NAME[self.portType] + ')' if self.portType in DB.PORTTYPES_NAME else ''}, Name={self.portName}, platform={self.ha['p']}")
       
    def getDevID(self, strValue: str):
        """Return a devID (0xBBHHHHPPPP) from strValue like '8' or '1234.8' or 2.1234.8"""
        p = strValue.split('.')
        pi = []
        for par in p:
            try:
                par = int(par, 16)
            except Exception as e:
                log(DB.LOG_ERR, f"Error on string {strValue}, not in the valid format: '8', '123.8' or '2.123.8' specifying bus.addr.port")
                return None
            else:
                if par != 0 and par < 0x10000:
                    pi.append(par)
                else:
                    log(DB.LOG_ERR, f"Error on string {strValue}: bus, address or port must be between 1 and ffff")
                    return None
                
        if len(pi) == 1:    # 8
            dev = (self.devID & 0xffffff0000) | pi[0]
        elif len(pi) == 2:  # 123.8
            dev = (self.busID << 32) | (pi[0] << 16) | pi[1]
        elif len(pi) == 3:  # 2.123.8
            dev = (pi[0] << 32) | (pi[1] << 16) | pi[2]
        else:
            log(DB.LOG_ERR, f"Error on string {strValue}, not in the valid format: '8', '123.8' or '2.123.8' specifying bus.addr.port")
            return None
        return dev
            

    def setPortConf(self):
        """set the self.portConf string specifying device configuration"""
        self.portConf = ''
        if self.portType in DB.PORTTYPES_NAME:
            self.portConf += f'{DB.PORTTYPES_NAME[self.portType]}'

        if self.portOpt in DB.PORTOPTS_NAME and self.portOpt != DB.PORTOPT_NONE:  # ignore NORMAL portOpt
            self.portConf += f',{DB.PORTOPTS_NAME[self.portOpt]}'

        for opt in self.options:
            if not ((opt == 'A' and float(self.options[opt]) == 1) or (opt == 'B' and float(self.options[opt]) == 0) or opt == 'HWADDR'): 
                self.portConf += f',{opt}={self.options[opt]}'
        if len(self.dcmdConf)>0:
            self.portConf += ',' + self.dcmdConf    # Add DCMD description as written by the user                
        log(DB.LOG_DEBUG, f"setPortConf(): self.portConf={self.portConf}")

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
        status = dict(devIDname2 = self.devIDname2, value = self.value, valueHA = self.valueHA, counterValue = self.counterValue, counterTime = self.counterTime, energy = self.energy, topic2 = self.topic2, topic2Config = self.topic2Config)
        return { 
            'devID': self.devID, 'portType': self.portType, 'portOpt': self.portOpt, 'portName': self.portName, 'options': self.options, 
            'ha': self.ha, 'dcmd': self.dcmd, 'status': status, 'dcmdConf': self.dcmdConf
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'DomBusDevice':
        """Transform json data in the file to a dictionary of DomBusDevice devices"""
        if 'dcmdConf' not in data:
            data['dcmdConf'] = ''  
        return cls(data['devID'], data['portType'], data['portOpt'], data['portName'], data['options'], data['ha'], data['dcmd'], data['status'], data['dcmdConf'])


    def value2valueHA(self):
        """Convert value got from DomBus to a device state compatible with Home Assistant"""
        if self.ha['p'] == 'select':
            self.valueHA = int(self.value / 10)
            if 'options' in self.ha and self.ha['options'][self.valueHA]:
                # Extract the name corresponding to the current select option
                self.valueHA = self.ha['options'][self.valueHA]
        elif (self.portType & (DB.PORTTYPE_OUT_DIGITAL | DB.PORTTYPE_OUT_RELAY_LP | DB.PORTTYPE_OUT_LEDSTATUS | DB.PORTTYPE_IN_AC) or self.ha['p'] == 'switch'):
            self.valueHA = 'OFF' if self.value==0 else 'ON'
        elif (self.portType & (DB.PORTTYPE_IN_TWINBUTTON | DB.PORTTYPE_OUT_BLIND)):
            self.valueHA = 'stopped'
            if self.value == 1 or self.value == 10: 
                self.valueHA = 'closing'
            elif self.value == 2 or self.value == 20:
                self.valueHA = 'opening'
        elif self.portType == DB.PORTTYPE_SENSOR_TEMP:
            self.valueHA = self.value     # DomBusTH sends Kelvin temperature with 0.1°C resolution, but self.value already contains the real temperature in Celsius
        elif self.portType == DB.PORTTYPE_SENSOR_HUM:
            self.valueHA = self.value / 10.0         # DomBusTH sends relative humdity with 0.1% resolutiom
        elif self.portType & (DB.PORTTYPE_IN_ANALOG | DB.PORTTYPE_SENSOR_DISTANCE): # send value
            self.valueHA = float(self.value)
        elif self.portType == DB.PORTTYPE_SENSOR_TEMP_HUM:
            return  # ignore this kind of sensor (used by Domoticz only)
        elif self.portType == DB.PORTTYPE_IN_COUNTER:
            if 'device_class' in self.ha and self.ha['device_class'] == 'power':
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
#            if 'device_class' in self.ha and self.ha['device_class'] in ('door','window','motion'):
#                self.valueHA = 'OFF' if self.value == 0 or self.value == 2 else 'ON'
#            else:
#                self.valueHA = 'Off' if self.value == 0 else 'On'
            self.valueHA = 'OFF' if self.value == 0 or self.value == 2 else 'ON'
            
    def updateFromBus(self, what, value:int = None, counterValue:int = None, configOptions:str = None):
        """ Data received from bus: update device and send command to MQTT, ..."""
        global manager
        self.lastUpdate=int(time.time())  # LastUpdate = number of seconds since epoch

        if what & DB.UPDATE_VALUE:
            if value is not None:
                self.value = value * self.options['A'] + self.options['B']
                if 'PRECISION' in self.options: self.value = round(self.value, self.options['PRECISION'])
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
                        if 'device_class' in self.ha and self.ha['device_class'] == 'power':
                            if counter>0 and ms > self.counterTime:
                                self.value = int((counter * 3600000000/ (ms - self.counterTime)) * self.options['A'])  # watt
                                self.energy += counter * self.options['A']  # energy in kWh
                            else:
                                self.value = 0  # Watt
                        self.counterTime = ms
                elif self.portType == DB.PORTTYPE_SENSOR_ALARM:
                    self.energy = counterValue

                if self.value != 0 and 'OPPOSITE' in self.options:
                    # OPPOSITE = 'd' => dev = BBHHHH000d; OPPOSITE maybe 1234.b => dev = BB1234000b where B = current busID; OPPOSITE maybe 021234.b => dev = 021234000b
                    dev = self.getDevID(self.options['OPPOSITE'])
                    log(DB.LOG_DEBUG, f"OPPOSITE dev = {dev:x}, Devices[dev].value={Devices[dev].value}")
                    if dev is not None and dev in Devices and (Devices[dev].value != 0 or (self.lastUpdate - Devices[dev].lastValueUpdate) >= mqtt['publishInterval']):
                        # OPPOSITE is used for import / export pulsed meter: if import meter is counting => export meter is set to 0, and vice versa (cannot get both import and export power)
                        log(DB.LOG_DEBUG, "OPPOSITE option is set => reset the OPPOSITE entity value")
                        Devices[dev].updateFromBus(DB.UPDATE_VALUE, 0)
            
            self.value2valueHA()    # set the valueHA according to value
            if mqtt['enabled'] != 0:
                if self.portType != DB.PORTTYPE_SENSOR_TEMP_HUM and self.portType != DB.PORTTYPE_OUT_LEDSTATUS:    # do not add TEMP+HUM device
                    # send data by MQTT only if it changed, or every publishInterval
                    if self.valueHA != self.lastValueHA or (self.lastUpdate - self.lastValueUpdate) >= mqtt['publishInterval']:
                        payload = self.valueHA    # message = ON
                        manager.mqttPublish(self.topic + '/state', payload)
                        # self.lastValueHA = self.valueHA MUST BE CONFIRMED BY UPDATE_ACK
                        self.lastValueUpdate = self.lastUpdate
#                        if self.ha['p'] == 'switch':    #DEBUG
#                            manager.mqttPublish(self.topic + '/set', payload)

                    # if devIDname2 exists => transmit energy value (good also for PORTTYPE_SENSOR_ALARM
                    if self.devIDname2 != "" and (self.energy != self.lastEnergy or (self.lastUpdate - self.lastEnergyUpdate) >= mqtt['publishInterval']):
                        # a second entity is associated to this
                        self.lastEnergy = self.energy
                        self.lastEnergyUpdate = self.lastUpdate
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
                    if self.valueHA != self.lastValueHA or (self.lastUpdate - self.lastValueUpdate) >= mqtt['publishInterval']:
                        payload = self.valueHA    # message = ON
                        manager.mqttPublish(self.topic + '/state', payload)
                        self.lastValueHA = self.valueHA; self.lastValueUpdate = self.lastUpdate
                        

        if what & DB.UPDATE_CONFIG:
            if mqtt['enabled'] != 0:
                # Create device by MQTT_AD
                if self.portType != DB.PORTTYPE_SENSOR_TEMP_HUM and self.portType != DB.PORTTYPE_OUT_LEDSTATUS:    # do not add TEMP+HUM device
                    if configOptions == 'reset' or (self.portType != self.lastPortType and self.lastTopicConfig != ""):
                        # reset request, or portType changed => remove previous entity by sending config topic with empty payload
                        # log(DB.LOG_DEBUG,f'configOptions={configOptions}. self.portType={self.portType}, self.lastPortType={self.lastPortType}, self.lastTopicConfig={self.lastTopicConfig}')
                        log(DB.LOG_DEBUG,f'Removing old entity, topic={self.lastTopicConfig}, payload=""')
                        manager.mqttPublish(self.lastTopicConfig, "")
                        self.lastPortType = self.portType
                        if self.lastTopic2Config != "":
                            # portType changed => remove previous entity by sending config topic with empty payload
                            log(DB.LOG_DEBUG,f'Removing old associated entity, topic={self.lastTopic2Config}, payload=""')
                            manager.mqttPublish(self.lastTopic2Config, "")

                    if self.portType == DB.PORTTYPE_IN_ANALOG:
                        if 'FUNCTION' in self.options:
                            if self.options['FUNCTION'] == '3950' and (self.ha['p'] != 'sensor' or self.ha['device_class'] != 'temperature'):
                                self.ha = DB.PORTTYPES_HA[DB.PORTTYPE_SENSOR_TEMP].copy()    # set 'p': 'sensor', 'device_class': 'temperature', 'unit_of_measurement': '°C', 'suggested_display_precision': 1
                    else:
                        # not analog port => remove FUNCTION if exists
                        if 'FUNCTION' in self.options:    
                            del self.options['FUNCTION']

                    if self.portOpt == DB.PORTOPT_INVERTED and self.port not in (DB.PORTTYPE_IN_DIGITAL, DB.PORTTYPE_OUT_DIGITAL, DB.PORTTYPE_OUT_RELAY_LP, DB.PORTTYPE_OUT_DIMMER, DB.PORTTYPE_OUT_BUZZER):
                        self.portOpt = DB.PORTOPT_NONE   # reset INVERTED flag when port is configured as temperature, analog, ...


                    self.setTopics(self.ha['p'], "")    # update current topic
                    payload = dict(name = f"{self.portName}", friendly_name = f"{self.portName}", unique_id = 'dombus_' + self.devIDname, command_topic = f"{self.topic}/set", \
                            state_topic = f"{self.topic}/state", schema = "json")
                    

                    o = {}  # originator
                    o['name'] = 'DomBusGateway'
                    o['sw'] = VERSION
                    o['url'] = 'https://creasol.it/DomBusGateway'
                    payload['o'] = o

                    if self.frameAddr in Modules:
                        dev = {} # device
                        dev['identifiers'] = [ self.frameAddr ]
                        if Modules[self.frameAddr][DB.LASTTYPE]:
                            dev['name'] = Modules[self.frameAddr][DB.LASTTYPE]
                        else:
                            dev['name'] = 'DomBus'
                        dev['name'] += f" {self.devAddr:04x}"
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
        self.devIDname2 = f"{self.frameAddr:06x}_{(self.port + 0x80):04x}"
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
                if 'device_class' in self.ha and self.ha['device_class'] == 'power':
                    if value < 0:
                        value += 65536  # Negative power => convert to int(16)
                if error == False:
                    if buses[self.busID]['protocol'] != None:
                        log(DB.LOG_DEBUG, f"TX to DomBus module {self.frameAddr:06x}, on port {self.port:02x}, value={value}")
                        if self.port < 0x80:
                            buses[self.busID]['protocol'].txQueueAdd(self.frameAddr, DB.CMD_SET, 2, 0, self.port, [value], DB.TX_RETRY, 1)
                        elif self.port >= 0x100 and self.port < 0x1000:
                            # send DB.CMD_CONFIG, port (port&0x7f), DB.SUBCMD_SETx (port>>8), 16bit value
                            buses[self.busID]['protocol'].txQueueAddConfig16(self.frameAddr, self.port & 0x7f, self.port >> 8, value)
                        self.updateFromBus(DB.UPDATE_VALUE) # Send back value to update HA
                    else:
                        # serial bus is not active
                        # TODO: request activation of serial connection
                        log(DB.LOG_WARN, f"updateToBus(): serial port for bus {self.busID} is not active: discharge frame for DomBus module {self.frameAddr:06x}")

        if buses[self.busID]['protocol']:
            buses[self.busID]['protocol'].send()    # Transmit, if needed


    def updateDeviceConfig(self, portType: int, portOpt: int, cal: int, dcmd: dict, dcmdConf: str, options: dict, haOptions: dict, value: int = None):
        """Port configuration change requested by the user (via telnet, for example) or by a new device read from DomBus network"""

        self.lastTopicConfig = self.topicConfig     # save previous config topic, used to remove the old entity
        self.lastTopic2Config = None
        if self.topic2Config is not None:
            self.lastTopic2Config = self.topic2Config
        proto = buses[self.busID]['protocol']

        diff = 0
        if portType is not None and self.portType != portType:
            self.portType = portType
            diff |= 1
        if portOpt is not None and self.portOpt != portOpt:
            self.portOpt = portOpt
            diff |= 2
        if dcmd:    # and self.dcmd != dcmd:
            self.dcmd = dcmd.copy()
            self.dcmdConf = dcmdConf    # "DCMD(Pulse)=1ff37.1:Toggle,DCMD(Pulse1)=10001.2:On:1m"
        
        if options:
            self.options = options.copy()
        
        if haOptions:
            if 'p' in haOptions and 'p' in self.ha and haOptions['p'] != self.ha['p']:
                # changed platform
                diff |= 8       # entity must be removed and created again
                self.ha.clear() # remove all options from ha dictionary
            self.ha.update(haOptions)
            diff |= 16

        # update DomBus module configuration
        log(DB.LOG_INFO, f'Update configuration for DomBus module {self.devIDname}:\r\n  {self.portConf}')
        proto.txQueueAdd(self.frameAddr, DB.CMD_CONFIG, 7, 0, self.port, [((self.portType>>24)&0xff), ((self.portType>>16)&0xff), ((self.portType>>8)&0xff), (self.portType&0xff), (self.portOpt >> 8), (self.portOpt&0xff)], DB.TX_RETRY,1)
        proto.send()    # Transmit
        # DCMD ?
        dcmdnum=0
        for i in range(0, min(len(dcmd), 8)):
            d = dcmd[i]
            log(DB.LOG_DEBUG, f"DCMD: transmit #{i} ?")
            #note: port|=0, 0x20, 0x40, 0x60 (4 DCMD for each port)
            if (d[0]!=0 and d[0]<DB.DCMD_IN_EVENTS["MAX"]):
                dcmdnum += 1
                log(DB.LOG_DEBUG, f"Yes, txQueueAdd()")
                proto.txQueueAdd(self.frameAddr, DB.CMD_DCMD_CONFIG, 12, 0, self.port|(i<<5), [ 
                    d[0],
                    d[1]>>8, d[1]&0xff,
                    d[2]>>8, d[2]&0xff,
                    d[3]>>8, d[3]&0xff, d[4], d[5],
                    d[6]>>8, d[6]&0xff 
                ], DB.TX_RETRY, 1)
        if (dcmdnum == 0): #DCMD not defined => transmits an empty DCMD_CONFIG 
            proto.txQueueAdd(self.frameAddr, DB.CMD_DCMD_CONFIG, 2, 0, self.port, [ DB.DCMD_IN_EVENTS["NONE"] ], DB.TX_RETRY, 1)
        proto.send()    # Transmit!

        if 'ADDR' in options and options['ADDR']>0 and options['ADDR']<248:
            log(DB.LOG_INFO, f"Send command to change modbus device address to {options['ADDR']}")
            # proto.txQueueAdd(self.frameAddr, DB.CMD_CONFIG, 4, 0, self.port, [DB.SUBCMD_SET, (newModbusAddr>>8), (newModbusAddr&0xff)], DB.TX_RETRY, 1)    #EVSE: until 2023-04-24 port must be replaced with port+5 to permit changing modbus address 
            proto.txQueueAddConfig16(self.frameAddr, self.port, DB.SUBCMD_SET, options['ADDR'])    #EVSE: until 2023-04-24 port must be replaced with port+5 to permit changing modbus address 
            proto.send()    # Transmit

        if cal and cal < 65536: # Transmit calibration or INIT parameter
            proto.txQueueAddConfig16(self.frameAddr, self.port, DB.SUBCMD_CALIBRATE, cal)   
            proto.send()    # Transmit
        
        parName = 'PAR1'; 
        if parName in self.options and self.options[parName] < 65536:
            parValue = self.options[parName]
            proto.txQueueAddConfig16(self.frameAddr, self.port, DB.SUBCMD_SET1, parValue)
        parName = 'PAR2'; 
        if parName in self.options and self.options[parName] < 65536:
            parValue = self.options[parName]
            proto.txQueueAddConfig16(self.frameAddr, self.port, DB.SUBCMD_SET2, parValue)
        parName = 'PAR3'; 
        if parName in self.options and self.options[parName] < 65536:
            parValue = self.options[parName]
            proto.txQueueAddConfig16(self.frameAddr, self.port, DB.SUBCMD_SET3, parValue)
        parName = 'PAR4'; 
        if parName in self.options and self.options[parName] < 65536:
            parValue = self.options[parName]
            proto.txQueueAddConfig16(self.frameAddr, self.port, DB.SUBCMD_SET4, parValue)
        proto.send()    # Transmit
        parName = 'PAR5'; 
        if parName in self.options and self.options[parName] < 65536:
            parValue = self.options[parName]
            proto.txQueueAddConfig16(self.frameAddr, self.port, DB.SUBCMD_SET5, parValue)
        proto.send()    # Transmit
        parName = 'PAR6'; 
        if parName in self.options and self.options[parName] < 65536:
            parValue = self.options[parName]
            proto.txQueueAddConfig16(self.frameAddr, self.port, DB.SUBCMD_SET6, parValue)
        proto.send()    # Transmit
        parName = 'PAR7'; 
        if parName in self.options and self.options[parName] < 65536:
            parValue = self.options[parName]
            proto.txQueueAddConfig16(self.frameAddr, self.port, DB.SUBCMD_SET7, parValue)
        proto.send()    # Transmit
        parName = 'PAR8'; 
        if parName in self.options and self.options[parName] < 65536:
            parValue = self.options[parName]
            proto.txQueueAddConfig16(self.frameAddr, self.port, DB.SUBCMD_SET8, parValue)
        proto.send()    # Transmit
        parName = 'PAR9'; 
        if parName in self.options and self.options[parName] < 65536:
            parValue = self.options[parName]
            proto.txQueueAddConfig16(self.frameAddr, self.port, DB.SUBCMD_SET9, parValue)
        proto.send()    # Transmit
        parName = 'PAR10'; 
        if parName in self.options and self.options[parName] < 65536:
            parValue = self.options[parName]
            proto.txQueueAddConfig16(self.frameAddr, self.port, DB.SUBCMD_SET10, parValue)
        proto.send()    # Transmit
        parName = 'PAR11'; 
        if parName in self.options and self.options[parName] < 65536:
            parValue = self.options[parName]
            proto.txQueueAddConfig16(self.frameAddr, self.port, DB.SUBCMD_SET112, parValue)
        proto.send()    # Transmit

        if 'EV Mode' in self.portName:
            parName = 'EVMAXCURRENT'; 
            if parName in self.options and self.options[parName] >= 3 and self.options[parName] <= 36:
                proto.txQueueAddConfig16(self.frameAddr, self.port, DB.SUBCMD_SET1, options[parName])
            parName = 'EVMAXPOWER'; 
            if parName in self.options and self.options[parName] >= 1000 and self.options[parName] <= 25000:
                proto.txQueueAddConfig16(self.frameAddr, self.port, DB.SUBCMD_SET2, options[parName])
            parName = 'EVSTARTPOWER'; 
            if parName in self.options and self.options[parName] >= 800 and self.options[parName] <= 25000:
                proto.txQueueAddConfig16(self.frameAddr, self.port, DB.SUBCMD_SET3, options[parName])
            parName = 'EVSTOPTIME'; 
            if parName in self.options and self.options[parName] >= 5 and self.options[parName] <= 600:
                proto.txQueueAddConfig16(self.frameAddr, self.port, DB.SUBCMD_SET4, options[parName])
            proto.send()
            parName = 'EVAUTOSTART'; 
            if parName in self.options and self.options[parName] >= 0 and self.options[parName] <= 2:
                proto.txQueueAddConfig16(self.frameAddr, self.port, DB.SUBCMD_SET5, options[parName])
            parName = 'EVMAXPOWER2'; 
            if parName in self.options and self.options[parName] >= 0 and self.options[parName] <= 25000:
                proto.txQueueAddConfig16(self.frameAddr, self.port, DB.SUBCMD_SET6, options[parName])
            parName = 'EVPOWERTIME'; 
            if parName in self.options and self.options[parName] >= 0 and self.options[parName] <= 43200:
                proto.txQueueAddConfig16(self.frameAddr, self.port, DB.SUBCMD_SET7, options[parName])
            parName = 'EVPOWERTIME2'; 
            if parName in self.options and self.options[parName] >= 0 and self.options[parName] <= 43200:
                proto.txQueueAddConfig16(self.frameAddr, self.port, DB.SUBCMD_SET8, options[parName])
            parName = 'EVWAITTIME'; 
            if parName in self.options and self.options[parName] >= 3 and self.options[parName] <= 60:
                proto.txQueueAddConfig16(self.frameAddr, self.port, DB.SUBCMD_SET9, options[parName])
            parName = 'EVMETERTYPE'; 
            if parName in self.options and self.options[parName] >= 0 and self.options[parName] < 4:
                proto.txQueueAddConfig16(self.frameAddr, self.port, DB.SUBCMD_SET10, options[parName])
            parName = 'EVMINVOLTAGE'; 
            if parName in self.options and self.options[parName] >= 0 and self.options[parName] <= 500:
                proto.txQueueAddConfig16(self.frameAddr, self.port, DB.SUBCMD_SET11, options[parName])
            proto.send()
     

        if 'HWADDR' in options:
            try: 
                newHwAddr = int(options['HWADDR'], 16)
            except Exception as e:
                log(DB.LOG_ERR, f"Invalid address for HWADDR parameter: {options['HWADDR']} must be in hex format, from 1 to ffff")
            else:
                if (newHwAddr > 0 and newHwAddr < 0xffff and newHwAddr != self.devAddr):
                    log(DB.LOG_INFO, f"Change module address from {self.devAddr:04x} to {newHwAddr:04x}")
                    proto.txQueueAdd(self.frameAddr, DB.CMD_CONFIG, 4, 0, 0, [(newHwAddr >> 8), (newHwAddr&0xff), (0-(newHwAddr >> 8)-(newHwAddr&0xff)-0xa5)], DB.TX_RETRY,1)
                    proto.send()    # Transmit
                    # Change address to every devices
                    devIDbase = (self.busID<<32) | (newHwAddr<<16)    #0xBBNNNN0000 New devID base
                    for dev in list(Devices.keys()):
                        if (dev & 0xffffff0000) == (self.devID & 0xffffff0000):  # current device, with old hwaddr
                            # Create a new object for this device
                            devID = devIDbase | (dev & 0xffff)
                            d = DomBusDevice(devID, Devices[dev].portType, Devices[dev].portOpt, Devices[dev].portName, Devices[dev].options, Devices[dev].ha, Devices[dev].dcmd) # Create device object with same configuration as before
                            Devices[devID] = d
                            d.value = Devices[dev].value
                            d.valueHA = Devices[dev].valueHA
                            d.counterValue = Devices[dev].counterValue
                            # TODO: send MQTT configuration for the new device?
                            # send MQTT to remove old device
                            log(DB.LOG_DEBUG,f'Removing old entity for device={Devices[dev].devIDname}...')
                            manager.mqttPublish(Devices[dev].lastTopicConfig, "")
                            if Devices[dev].lastTopic2Config != "":
                                # portType changed => remove previous entity by sending config topic with empty payload
                                log(DB.LOG_DEBUG,f'Removing old associated entity for {Devices[dev].devIDname}...')
                                manager.mqttPublish(Devices[dev].lastTopic2Config, "")
                                del Devices[dev]
                    if self.frameAddr in Modules:
                        del Modules[self.frameAddr]
            del options['HWADDR']

        if 'A' not in self.options:
            self.options['A'] = 1
        if 'B' not in self.options:
            self.options['B'] = 0

        log(DB.LOG_DEBUG, f"updateDeviceConfig(): calling setPortConf()")
        self.setPortConf() # write configuration string self.portConf
        resetReq = None
        if diff != 0:
            setSaveDataTimeout()
            if diff & 8:
                # changed entity platform
                resetReq = "reset"
                log(DB.LOG_INFO, f"Changed entity platform to {haOptions['p']}")

            if diff & 27:
                # update HA configuration
                log(DB.LOG_INFO, f'Update configuration to domotic controller for module {self.devIDname}:\r\n  {options}\r\n  {haOptions}')
                self.updateFromBus(DB.UPDATE_CONFIG, None, None, resetReq)

        if value:
            self.updateFromBus(DB.UPDATE_VALUE, value)

######################################## DomBusProtocol class ###############################################    
class DomBusProtocol(asyncio.Protocol):
    def __init__(self, busID, on_data_received_callback):
        self.busID = busID
        self.devAddr = 0    #0xff31
        self.frameAddr = 0  #0x01ff31       bus|devAddr      used in Modules{}
        self.devID = 0      #0x01ff310001     bus|devAddr|port used in Devices{}
        self.devIDname = "" #b01_hff31_p0001
        self.on_data_received_callback = on_data_received_callback
        self.transport = None
        self.buffer = b""   
        self.frame = b""
        self.txbuffer = b""
        self.txQueue = dict()
        self.checksumValue = 0
        self.retryTime = 0 # time since epoch, in ms, when a frame have to be TXed again

    def connection_made(self, transport):
        """Called when the connection is made."""
        self.transport = transport
        log(DB.LOG_INFO, f"Connection established on bus {self.busID}.")

    def connection_lost(self, exc):
        """Called when the connection is lost or closed."""
        log(DB.LOG_ERR, f"Connection lost on bus {self.busID}: {exc}")
        buses[self.busID]['protocol'] = None
        

    def setID(self, port):
        """Set frameAddr (01ff31) devID (01ff310001) and devIDname ("b01_hff31_p0001")"""
        # Known data: self.busID and self.devAddr
        self.frameAddr = (self.busID << 16) + self.devAddr  # e.g. 0x01ff51 
        self.devID = (self.frameAddr << 16) + port
        self.devIDname = ""
        if port != 0:
            self.devIDname = f"b{self.busID:02x}_h{self.devAddr:04x}_p{port:04x}"

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
                    cmdAck = DB.CMD_ACK if (cmd & DB.CMD_ACK) else 0
                    cmdLen = (cmd & DB.CMD_LEN_MASK) * 2
                    cmd &= DB.CMD_MASK
                    msg += " "
                    if cmdAck != 0:
                        msg += "A-"
                    if cmd == DB.CMD_CONFIG:
                        msg += 'CFG '
                        if cmdAck != 0 and port == 0xfe:
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
                        if cmdAck != 0 and (port & 0xf0) == 0xf0:
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
                        logLevel = DB.LOG_DUMPDCMD
                    elif cmd==DB.CMD_DCMD:
                        msg += 'DCMD '
                        logLevel = DB.LOG_DUMPDCMD
                    
                    msg += f"P{port:02x} {arg:02x}"
                    i += 1
                    if i+cmdLen >= frameLen:
                        msg += " ERROR: cmd length > frame length"
                        break
                    else:
                        for j in range(2, cmdLen):
                            msg += f" {frame[i + j]:02x}"
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

        frameIdx = DB.FRAME_HEADER
        while frameIdx+3 < frameLen:
            portIdx = frameIdx + 1
            cmd, port, arg = struct.unpack(">BBB", frame[frameIdx:frameIdx+3])
            cmdAck = DB.CMD_ACK if (cmd & DB.CMD_ACK) else 0
            cmdLen = (cmd & DB.CMD_LEN_MASK) * 2
            cmd &= DB.CMD_MASK
            if cmd == DB.CMD_CONFIG and port != 0xfe and (port & 0xf0) == 0xf0:
                cmdLen = 4 # cmdLen does not make sense in case of full port configuration
            if frameLen < frameIdx + cmdLen + 1:
                # invalid cmdLen: 
                log(DB.LOG_DEBUG, f"Invalid cmdLen={cmdLen}: ignore frame")
                return
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
            if dst == 0:                                                    
                # frame addressed to me: parse frame
                self.setID(port)    # set self.devID and self.devIDname
                self.moduleUpdate(1) # update modules dictionary to keep trace of running modules
                # check if device exists
                if cmdAck == 0 and self.devID not in Devices:
                    # send frame to ask configuration
                    self.txQueueAskConfig(self.frameAddr)
                else:
                    # module already recognized
                    if cmdAck != 0:
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
                                                ha = dict()
                                                options = dict()

                                                ############################## New device, read from Bus => set default parameters ########################
                                                if portType != DB.PORTTYPE_CUSTOM or portOpt >= 2:
                                                    # do not enable CUSTOM device with DB.PORTOPT not specified (ignore it!)
                                                    if portType == DB.PORTTYPE_CUSTOM:
                                                        if portOpt == DB.PORTOPT_SELECT:
                                                            ha['p'] = 'select'  # platform
                                                            if "S.On" in portName:
                                                                ha['options'] = ['Off', 'On']
                                                            elif "S.State" in portName:
                                                                ha['options'] = ['Off', 'On', 'HiCurr', 'LoVolt', 'HiDiss', 'HiDissLoVolt']
                                                        elif portOpt==DB.PORTOPT_DIMMER:
                                                            if 'EV Current' in portName:
                                                                ha = {'p': 'number', 'min': 0, 'max': 36, 'step': 1, 'unit_of_measurement': 'A'}
                                                            else:
                                                                ha = {'p': 'number', 'min': 0, 'max':100, 'step':1, 'unit_of_measurement': '%'}
                                                        elif portOpt==DB.PORTOPT_LATCHING_RELAY:
                                                            ha['p'] = 'switch'
                                                        elif portOpt==DB.PORTOPT_ADDRESS:
                                                            ha['p'] = 'text'
                                                        elif portOpt==DB.PORTOPT_IMPORT_ENERGY or portOpt==DB.PORTOPT_EXPORT_ENERGY:
                                                            ha['p'] = 'sensor'
                                                            ha['device_class'] = 'power'
                                                            ha['state_class'] = 'measurement'
                                                            ha['unit_of_measurement'] = 'W'
                                                            ha['suggested_display_precision'] = 0
                                                            if "Solar" in portName or "Exp" in portName or portOpt==DB.PORTOPT_EXPORT_ENERGY:
                                                                ha['icon'] = 'mdi:solar-power'
                                                        elif portOpt==DB.PORTOPT_VOLTAGE:
                                                            ha['p'] = 'sensor'
                                                            ha['device_class'] = 'voltage'
                                                            ha['unit_of_measurement'] = 'V'
                                                            ha['suggested_display_precision'] = 0
                                                        elif portOpt==DB.PORTOPT_CURRENT:
                                                            ha['p'] = 'sensor'
                                                            ha['device_class'] = 'current'
                                                            ha['unit_of_measurement'] = 'A'
                                                        elif portOpt==DB.PORTOPT_POWER_FACTOR:
                                                            options['A'] = 0.1
                                                            ha['p'] = 'sensor'
                                                            ha['device_class'] = 'power_factor'
                                                            ha['unit_of_measurement'] = '%'
                                                            ha['suggested_display_precision'] = 1
                                                        elif portOpt==DB.PORTOPT_FREQUENCY:
                                                            options['A'] = 0.01
                                                            ha['p'] = 'sensor'
                                                            ha['device_class'] = 'frequency'
                                                            ha['unit_of_measurement'] = 'Hz'
                                                            ha['suggested_display_precision'] = 2
                                                        elif portOpt==DB.PORTOPT_TOUCH:
                                                            ha['p'] = 'binary_sensor'
                                                            ha['device_class'] = 'motion'
                                                        if "EV State" in portName:
                                                            ha['p'] = 'select'  # platform
                                                            ha['options'] = ['Off', 'Dis', 'Con', 'Ch', 'Vent', 'AEV', 'APO', 'AW']
                                                        elif "EV Mode" in portName:   #Off, Solar, 50%, 75%, 100%, Managed
                                                            ha['p'] = 'select'  # platform
                                                            ha['options'] = ['Off', 'Solar', '25%', '50%', '75%', '100%', 'Man']
                                                            options['EVMAXCURRENT'] = 16
                                                            options['EVMAXPOWER'] = 6000
                                                            options['EVSTARTPOWER'] = 1200
                                                            options['EVSTOPTIME'] = 90
                                                            options['EVAUTOSTART'] = 1
                                                            options['EVMAXPOWER2'] = 0
                                                            options['EVMAXPOWERTIME'] = 0
                                                            options['EVMAXPOWERTIME2'] = 0
                                                            options['EVWAITTIME'] = 6
                                                            options['EVMETERTYPE'] = 0
                                                            options['EVMINVOLTAGE'] = 207
                                                            # Create virtual device EVMAXCURRENT, devID 0x104

                                                            manager.parseConfiguration(self.devID+0x100, DB.PORTTYPE_CUSTOM, DB.PORTOPT_DIMMER, f"P{port+0x100:03x} EV MaxCurrent", {}, {'p': 'number', 'min': 0, 'max':36, 'step':1, 'unit_of_measurement': 'A'}, [], "", options['EVMAXCURRENT'])
                                                            manager.parseConfiguration(self.devID+0x200, DB.PORTTYPE_CUSTOM, DB.PORTOPT_DIMMER, f"P{port+0x200:03x} EVMAXPOWER", {}, {'p': 'number', 'min': 1000, 'max':25000, 'step':100, 'unit_of_measurement': 'W'}, [], "", options['EVMAXPOWER'])
                                                            manager.parseConfiguration(self.devID+0x300, DB.PORTTYPE_CUSTOM, DB.PORTOPT_DIMMER, f"P{port+0x300:03x} EVSTARTPOWER", {}, {'p': 'number', 'min': 800, 'max':25000, 'step':100, 'unit_of_measurement': 'W'}, [], "", options['EVSTARTPOWER'])
                                                            manager.parseConfiguration(self.devID+0x400, DB.PORTTYPE_CUSTOM, DB.PORTOPT_DIMMER, f"P{port+0x400:03x} EVSTOPTIME", {}, {'p': 'number', 'min': 5, 'max':600, 'step':1, 'unit_of_measurement': 's'}, [], "", options['EVSTOPTIME'])
                                                            manager.parseConfiguration(self.devID+0x500, DB.PORTTYPE_CUSTOM, DB.PORTOPT_DIMMER, f"P{port+0x500:03x} EVAUTOSTART", {}, {'p': 'number', 'min': 0, 'max':2, 'step':1, 'unit_of_measurement': ' '}, [], "", options['EVAUTOSTART'])
                                                            manager.parseConfiguration(self.devID+0x600, DB.PORTTYPE_CUSTOM, DB.PORTOPT_DIMMER, f"P{port+0x600:03x} EVMAXPOWER2", {}, {'p': 'number', 'min': 0, 'max':25000, 'step':100, 'unit_of_measurement': 'W'}, [], "", options['EVMAXPOWER2'])
                                                            manager.parseConfiguration(self.devID+0x700, DB.PORTTYPE_CUSTOM, DB.PORTOPT_DIMMER, f"P{port+0x700:03x} EVMAXPOWERTIME", {}, {'p': 'number', 'min': 0, 'max':43200, 'step':1, 'unit_of_measurement': 's'}, [], "", options['EVMAXPOWERTIME'])
                                                            manager.parseConfiguration(self.devID+0x800, DB.PORTTYPE_CUSTOM, DB.PORTOPT_DIMMER, f"P{port+0x800:03x} EVMAXPOWERTIME2", {}, {'p': 'number', 'min': 0, 'max':43200, 'step':1, 'unit_of_measurement': 's'}, [], "", options['EVMAXPOWERTIME2'])
                                                            manager.parseConfiguration(self.devID+0x900, DB.PORTTYPE_CUSTOM, DB.PORTOPT_DIMMER, f"P{port+0x900:03x} EVWAITTIME", {}, {'p': 'number', 'min': 3, 'max':60, 'step':1, 'unit_of_measurement': 's'}, [], "", options['EVWAITTIME'])
                                                            manager.parseConfiguration(self.devID+0xa00, DB.PORTTYPE_CUSTOM, DB.PORTOPT_DIMMER, f"P{port+0xa00:03x} EVMETERTYPE", {}, {'p': 'number', 'min': 0, 'max':3, 'step':1, 'unit_of_measurement': ' '}, [], "", options['EVMETERTYPE'])
                                                            manager.parseConfiguration(self.devID+0x10A-4, DB.PORTTYPE_CUSTOM, DB.PORTOPT_DIMMER, f"P{port+0x106:03x} EV MinVoltage", {}, {'p': 'number', 'min': 180, 'max':450, 'step':1, 'unit_of_measurement': 'V'}, [], "", options['EVMINVOLTAGE'])
                                                    elif portType == DB.PORTTYPE_IN_COUNTER:
                                                        # counter or kWh ?
                                                        # ha['device_class'] = 'energy'
                                                        # ha['state_class'] = 'total_increasing'
                                                        # ha['unit_of_measurement'] = 'kWh'
                                                        options['DIVIDER'] = 2000   # Default: 1kW = 2000 pulses => 1 pulse = 0.0005Wh
                                                    elif portType == DB.PORTTYPE_IN_ANALOG:
                                                        # Analog input
                                                        if port == 7 and (self.devAddr == 0xff51 or Modules[self.frameAddr][DB.LASTTYPE] == 'DomBusTH'):
                                                            options['A'] = 0.000612695
                                                            ha['suggested_display_precision'] = 2
                                                                  
                                                    manager.parseConfiguration(self.devID, portType, portOpt, f"P{port:02x} {portName}", options, ha)
                                                    # log(DB.LOG_DEBUG, f"DomBusDevice({self.devID:08x}, {portType:x}, {portOpt:x}, P{port:02x} {portName}, {portConf}, {Options}, {ha})")
                                                    # Devices[self.devID] = DomBusDevice(self.devID, portType, portOpt, f"P{port:02x} {portName}", portConf, Options, ha)
                                                    # Devices[self.devID].updateFromBus(DB.UPDATE_VALUE | DB.UPDATE_CONFIG, 0)
                                                    options.clear()
                                                    ha.clear()

                                        port+=1;
                        elif cmd==DB.CMD_SET:
                            # received a ACK to a SET command: check status
                            if self.devID in Devices:
                                # I sent a SET command, and received the ACK
                                d = Devices[self.devID]
                                if (d.portType & (DB.PORTTYPE_OUT_DIGITAL | DB.PORTTYPE_OUT_RELAY_LP | DB.PORTTYPE_OUT_DIMMER | DB.PORTTYPE_OUT_FLASH | DB.PORTTYPE_OUT_ANALOG)) or (d.portType == DB.PORTTYPE_CUSTOM and (d.portOpt==DB.PORTOPT_SELECT or d.portOpt == DB.PORTOPT_DIMMER)):
                                    # Update device state taking ACK value (1 byte)
                                    # UPDATE_ACK is also used to confirm a "set" command from HA:  HA sends a set command, and get back a state that confirm the new status
                                    d.value = arg
                                    d.value2valueHA()   # update valueHA 
                                    # log(DB.LOG_DEBUG, f"Received SET+ACK: value={d.value} valueHA={d.valueHA}")
                                    d.updateFromBus(DB.UPDATE_ACK, 0)
                                # TODO: update value by using ACK also for other port types?
                        # ACK was managed.
                        # if more frames from frameAddr => program send()
                        if self.frameAddr in self.txQueue and len(self.txQueue[self.frameAddr])>0:
                            self.send()
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
                                        try:
                                            value = int(Devices[self.devID].value) & 0xff    # TODO: manage counter, temperature, and other values 16-32bits
                                        except Exception:
                                            value = 0
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
                                        if d.ha['p'] == 'sensor' and 'device_class' in d.ha:
                                            if d.ha['device_class'] == 'temperature' and value != 0:
                                                if 'FUNCTION' in d.options:
                                                    Ro=10000.0  # 20230703: float (was int)
                                                    To=25.0
                                                    temp=0.0  #default temperature # 20230703: float (was int)
                                                    if (d.options['FUNCTION']=='3950'):
                                                        #value=0..65535
                                                        beta=3950
                                                        if value == 65535: value=65534  #Avoid division by zero
                                                        r = value * Ro / (65535 - value)
                                                        temp = math.log(r / Ro) / beta      # log(R/Ro) / beta
                                                        temp += 1.0 / (To + 273.15)
                                                        temp = (1.0 / temp) - 273.15
                                                else:
                                                    temp = value / 10.0 - 273.1
                                                
                                                # compute the averaged temperature and save it in d.Options[]
                                                if abs(d.lastValue - temp)<1.5:
                                                    # compute the average value
                                                    temp = (d.lastValue*5 + temp) / 6
                                                value = round(temp, 1)
                                            elif d.ha['device_class'] == 'power':
                                                # EV GRID, transmitting only power (not energy)
                                                # check if value is negative
                                                if (value&0x8000):
                                                    value=value-65536   # negative power
                                    elif cmdLen == 5 or cmdLen == 6:
                                        value = arg*256 + arg2
                                        value2 = arg3*256 + arg4
                                        if d.portType == DB.PORTTYPE_IN_COUNTER:
                                            counterValue = value2   # pass value and value2 to updateFromBus() that will compute the current power

                                    
                                    elif cmdLen == 7 or cmdLen == 8:
                                        # transmitted power (int16) + energy (uint32)
                                        value = arg*256 + arg2
                                        value2 = (arg3<<24) + (arg4<<16) + (arg5<<8) + arg6
                                        #kWh?
                                        if d.portType == DB.PORTTYPE_CUSTOM and (d.portOpt == DB.PORTOPT_IMPORT_ENERGY or d.portOpt == DB.PORTOPT_EXPORT_ENERGY): #kWh
                                            #value=Watt, signed
                                            #value2=N*10Wh
                                            if (value&0x8000):
                                                value=value-65536   # negative power
                                            if (value2 & 0x80000000):
                                                value2 = value2 - 0x100000000   # negative energy
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
            else:
                # frame not addressed to me
                if cmd == DB.CMD_DCMD and src != 0 and src != 0xffff and dst != 0 and arg<DB.DCMD_OUT_CMDS['MAX']: #DCMD command addressed to another device
                    log(DB.LOG_INFO,f"DCMD command from {src:04x} to {dst:04x}: port={port:02x} cmd={DB.DCMD_OUT_CMDS_Names[arg]} cmdLen={cmdLen}")
                    if len(buses)>1 and ((self.busID << 16) + dst) not in Modules:
                        # in case that more than 1 bus are attached and DCMD destination is not in the current bus, route frame to another bus
                        for bus in buses:
                            frameAddr = ((bus << 16) + dst)
                            if bus != self.busID and frameAddr in Modules:
                                # Frame must be transmitted to another bus => use the right class for txQueueAdd
                                buses[bus]['protocol'].txQueueAdd(frameAddr + (self.busID << 40) + (src << 24), cmd, cmdLen, cmdAck, port, [arg] if cmdAck else [arg, arg2, arg3], 1, 1)   # frameAddr=(bus|src|busID|dst)
                                buses[bus]['protocol'].send()   # start sending frame on the other bus
                                
                        
            frameIdx = frameIdx + cmdLen + 1
        self.send()

                
    def moduleUpdate(self, what: int = 0):
        """
            Update Modules[self.devID], used to store which Modules have been RXed
            moduleUpdate(1) when a packet is RXed
            moduleUpdate(2) when a packet is being TXed
        """
        global saveDataTimeout

        if self.frameAddr not in Modules:
            Modules[self.frameAddr] = [0, 0, int(time.time())+3-DB.PERIODIC_STATUS_INTERVAL, 0, 'N.A.', 'N.A.']
            setSaveDataTimeout()
            
        if what & 1: # RX packet
            Modules[self.frameAddr][DB.LASTRX] = time.time()

        if what & 2:  # TX packet
            Modules[self.frameAddr][DB.LASTTX] = int(time.time()*1000)

        if saveDataTimeout != 0 and datetime.datetime.now() > saveDataTimeout:
            # Must save Modules and Devices structures on filesystem
            saveData()
            saveDataTimeout = 0

    def txQueueAddConfig16(self, frameAddr, port, subcmd, value):
        """Send a CMD_CONFIG with a SUBCMD and 16bit value"""
        log(DB.LOG_DEBUG,f"Calling txQueueAdd({self.frameAddr:06x}, {DB.CMD_CONFIG}, 4, 0, {port}, [{subcmd}, {((value>>8)&0xff)}, {(value&0xff)}], DB.TX_RETRY, 1)")
        self.txQueueAdd(frameAddr, DB.CMD_CONFIG, 4, 0, port, [subcmd, ((value>>8)&0xff), (value&0xff)], DB.TX_RETRY, 1)

    def txQueueAdd(self, frameAddr, cmd, cmdLen, cmdAck, port, args, retries, now):
        # add a command in the tx queue for the specified module (frameAddr)
        # frameAddr may be srcbus|src|dstbus|dst  (48bit) in case that a DCMD command must be transmitted from one bus to another one
        # if that command already exists, update it
        # cmdLen=length of data after command (port+args[])
        sec=int(time.time())
        ms=int(time.time()*1000)
        self.moduleUpdate(2) # Update Modules[frameAddr]
        if len(self.txQueue)==0 or frameAddr not in self.txQueue:
            #create self.txQueue[frameAddr]
            self.txQueue[frameAddr]=[[cmd, cmdLen, cmdAck, port, args, retries]]
            # log(DB.LOG_DEBUG, f"txQueueAdd(): frameAddr does not exist! frameAddr={frameAddr:06x} cmd={cmd:02x} ack={cmdAck} len={cmdLen} port={port:02x}")
            Modules[frameAddr&0xffffff][DB.LASTRETRY] = 0 # Init retry value for this module (no frames were in the queue)
        else:
            found=0
            for f in self.txQueue[frameAddr]:
                #f=[cmd,cmdlen,cmdAck,port,args[]]
                if (f[DB.TXQ_CMD]==cmd and f[DB.TXQ_CMDLEN]==cmdLen and f[DB.TXQ_PORT]==port and (cmd!=DB.CMD_CONFIG or len(args)==0 or args[0]==f[DB.TXQ_ARGS][0])): #if CMD_CONFIG, also check that SUBCMD is the same
                    #command already in txQueue: update values
                    # log(DB.LOG_DEBUG, f"txQueueAdd(): frame already exist: frameAddr={frameAddr:06x} cmd={cmd:02x} ack={cmdAck} len={cmdLen} port={port:02x}")
                    f[DB.TXQ_CMDACK]=cmdAck
                    f[DB.TXQ_ARGS]=args
                    if (f[DB.TXQ_RETRIES]<retries):
                        f[DB.TXQ_RETRIES]=retries
                    found=1
                    break
            if (found==0):
                self.txQueue[frameAddr].append([cmd,cmdLen,cmdAck,port,args,retries])
                # log(DB.LOG_DEBUG, f"txQueueAdd(): add frame to the queue: frameAddr={frameAddr:06x} cmd={cmd:02x} ack={cmdAck} len={cmdLen} port={port:02x}")
            #txQueueRetry: don't modify it... transmit when retry time expires (maybe now or soon)
        if now:
            Modules[frameAddr&0xffffff][DB.LASTTX] = 0 # Transmit now

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
                    # log(DB.LOG_DEBUG, f"txQueueRemove(): remove frame from the queue: frameAddr={frameAddr:06x} cmd={cmd:02x} port={port:02x} arg1={arg1:02x}")
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
        # frameAddr normally is 010004  (module addr 4, busID 1)
        # but may be something like 021201010004 (packet from address 1201 of bus 2 to 0004 of bus 1    

        timeNextTx = 0  # next transmission time (since Epoch), in ms            
        tx = 0
        sec = int(time.time())
        ms = int(time.time() * 1000)

        for frameAddr in self.txQueue:
            if len(self.txQueue[frameAddr])>0:
                module = Modules[frameAddr & 0xffffff]
                # timeSinceLastTx = ms-module[DB.LASTTX]        #number of milliseconds since last TXed frame
                # timeLastTx = module[DB.LASTTX]
                module[DB.LASTRETRY]                         #number of retry (0,1,2,3...): used to compute the retry period
                if module[DB.LASTRETRY] > DB.TX_RETRY:
                    module[DB.LASTRETRY] = DB.TX_RETRY
                timeNextRetry = module[DB.LASTTX] + (DB.TX_RETRY_TIME << (module[DB.LASTRETRY]+1)) # time for the next transmission, for this module
                if timeNextRetry <= ms:
                    # Must transmit now
                    tx=1
                    self.txbuffer = bytearray()
                    self.txbuffer.append(DB.PREAMBLE)
                    self.txbuffer.append((frameAddr >> 8) & 0xff)       #dstAddr
                    self.txbuffer.append(frameAddr & 0xff)
                    self.txbuffer.append((frameAddr >> 32) & 0xff)      #master address or src address (DCMD)
                    self.txbuffer.append((frameAddr >> 24) & 0xff)
                    self.txbuffer.append(0)                  #length
                    txbufferIndex=DB.FRAME_HEADER
                    # transmit ACK first: build a new queue with all ACK and commands for the selected module frameAddr
                    txQueueNow = []
                    # Transmit ACK first, then commands
                    for txq in self.txQueue[frameAddr][:]:    #iterate a copy of self.txQueue[frameAddr]
                        (cmd, cmdLen, cmdAck, port, args, retry) = txq
                        if cmdAck != 0:
                            # ACK transmitted first
                            txQueueNow.append(txq)
                    for txq in self.txQueue[frameAddr][:]:    #iterate a copy of txQueue[frameAddr]
                        (cmd, cmdLen, cmdAck, port, args, retry) = txq
                        if cmdAck==0: 
                            # Command to be transmitted
                            txQueueNow.append(txq)

                    for txq in txQueueNow:    #iterate txQueueNow
                        #[cmd,cmdLen,cmdAck,port,[*args]]
                        (cmd, cmdLen, cmdAck, port, args, retry) = txq
                        if (txbufferIndex+cmdLen+2>=DB.FRAME_LEN_MAX):
                            #frame must be truncate (TX fifo is full)
                            # if other frame exists, send() must be invoked at the receiving of the ACK
                            break
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
                        if (cmdAck != 0 or retry<=1):
                            self.txQueue[frameAddr].remove(txq)
                        else:
                            txq[DB.TXQ_RETRIES] = retry-1   #command, no ack: decrement retry
                            # set time for the next retransmission
                            if timeNextTx == 0 or timeNextTx < (ms + DB.TX_RETRY_TIME << (module[DB.LASTRETRY]+1)):
                                timeNextTx = ms + (DB.TX_RETRY_TIME << (module[DB.LASTRETRY]+1))

                    self.txbuffer[DB.FRAME_LEN] = txbufferIndex - DB.FRAME_HEADER
                    module[DB.LASTRETRY] += 1    #increment RETRY to multiply the retry period * 2
                    if (module[DB.LASTRETRY] >= DB.TX_RETRY):
                        module[DB.LASTRETRY] = 4;
                    txbufferIndex += 1  # add 1 to txbufferIndex to include checksum in the frame length
                    self._checksum(self.txbuffer, txbufferIndex)
                    self.txbuffer.append(self.checksumValue)

                    # TODO SerialConn.Send(frameAddr, self.txbuffer)    # frameAddr contains the busID, self.txbuffer the frame ready to be transmitted
                    self.transport.write(self.txbuffer[:txbufferIndex])
                    self.dump(self.txbuffer, txbufferIndex, "TX", (frameAddr >> 16) & 0xff, DB.FRAME_OK)
                    Modules[frameAddr&0xffffff][DB.LASTTX] = ms
                else:
                    # if timeNextRetry > ms: must wait!
                    if timeNextTx==0 or timeNextRetry < timeNextTx:
                        timeNextTx = timeNextRetry

                        
        """
            TODO: remove modules that are not received since a long time ???
            else: #No frame to be TXed for this frameAddr
                #check that module is active
                timeSinceLastRx = sec-module[DB.LASTRX]       #number of seconds since last RXed frame
                if timeSinceLastRx > DB.MODULE_ALIVE_TIME:
                    # too long time since last RX from this module: remove it from Modules
                    if frameAddr: 
                        log(DB.LOG_INFO,f"Remove module {frameAddr:06x} because it's not alive")
                        delmodules.append(frameAddr)
                        # also remove any cmd in the self.txQueue
                        log(DB.LOG_INFO,f"Remove txQueue for {frameAddr:06x}")
                        self.txQueueRemove(frameAddr,255,255,0)
                        # TODO: set device as not available

        for d in delmodules:    #remove module address of died modules (that do not answer since long time (MODULE_ALIVE_TIME))
            if d in Modules:
                del Modules[d]
        """


        if tx == 0: #nothing has been transmitted: send outputs status for device with older lastStatus

            # Check if any DCMD frame from a dombus module to another one...
                    
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
                self.txOutputsStatus(olderFrameAddr)

        if timeNextTx != 0 and timeNextTx > ms:
            # another frame must be transmitted at this time (in ms): timeNextTx
            if self.retryTime == 0 or self.retryTime < ms:
                # create a task that wait for the retry time and then execute send() again
                self.retryTime = timeNextTx
                asyncio.create_task(self._retrySend(timeNextTx - ms))
                    

    async def _retrySend(self, waitTime):
        """Wait for waitTime (in milliseconds), then execute send() again"""
        if waitTime>0:
            waitTime /= 1000    # Convert in seconds
            await asyncio.sleep(waitTime)
            self.retryTime = 0
            self.send()

class DomBusManager:
    def __init__(self):
        self.loop = asyncio.get_event_loop()
        self.mqttConnected = False
        self.mqttPublishQueue = Queue() # Queue for MQTT messages
        self.selectedBus = 1        # default bus selected for command line interface (telnet)
        self.selectedModule = 0     # address of module selected by CLI (telnet)
        self.retryConnection = 10   # Seconds to wait before retrying to open serial connections

        self.commands = {
            'help':     {
                'cmd': self.cmd_help,     
                'help': 'Print this help. Type "help CMD" to get info about the specified cmd' },
            'refresh':   {
                'cmd': self.cmd_refresh,
                'help': 'Send list of all devices to the domotic controller\r\nWith command "refresh reset" all DomBus entities are removed and created as new\r\n so you can loose configuration, entity name, ...',   },
            'showbus':  {
                'cmd': self.cmd_showbus,
                'help': 'Show the list of available buses\r\nSpecify a bus to show modules attached to that bus, e.g. "showbus 1"' }, 
            'showmodule':   { 
                'cmd': self.cmd_showmodule, 
                'help': 'Show data about the specified module: e.g. "showmodule ffe3"' },
            'rmmodule':   { 
                'cmd': self.cmd_rmmodule, 
                'help': 'Remove a module from DomBusGateway and MQTT controller (Home Assistant, ...):\r\ne.g. "rmmodule ffe3"' },
            'setport':  {
                'cmd': self.cmd_setport,
                'help': 'Configure the specified port: "showbus" and "showmodule" commands have to be invoked\r\nto select the module to be configured. Examples:\r\n"setport 01 IN_ANALOG,A=0.00042" to set port 1 as analog input, specifying the A coefficient\r\n"setport 02 IN_DIGITAL,INVERTED" to set port 2 as digital input with inverted logic\r\n(On when port 2 is pulled to GND, Off when left open)\r\n"setport c p=binary_sensor,device_class=window" to set entity platform and class' },
            'quit':   { 
                'cmd': self.cmd_quit, 
                'help': 'Exit from telnet session' },
        }

    async def check_buses(self):
        """Check serial ports and start connections. Restart serial connection in case of failure"""
        while True:            
            for bus in buses:
                if 'protocol' not in buses[bus] or buses[bus]['protocol'] is None:
                    await manager.add_bus(busID=bus, port=buses[bus]['serialPort'], baudrate=115200)
                    log(DB.LOG_INFO, f"check_buses(): start connection to serial port {buses[bus]['serialPort']}, bus {bus}")

            await asyncio.sleep(self.retryConnection)



#    async def add_bus(self, busID, port, baudrate=115200):
#        """Add a new serial bus. Used until 2025-09-22"""
#        if busID in buses and 'protocol' in buses[busID]:
#            raise ValueError(f"Bus ID {busID} already exists.")
#
#        def on_data_received(busID, data):
#            """Callback for handling received data."""
#            # Parse and handle the message here
#        
#        log(DB.LOG_INFO, f"Connecting DomBus {busID} on port {port} {baudrate}bps ...")
#        transport, protocol = await serial_asyncio.create_serial_connection(
#            self.loop,
#            lambda: DomBusProtocol(busID, on_data_received),
#            port,
#            baudrate=baudrate,
#        )
#        buses[busID]['protocol'] = protocol
#        log(DB.LOG_DEBUG, f"Bus {busID} added on port {port}.")
#
#

    async def add_bus(self, busID, port, baudrate=115200):
        """Task that add a new serial bus."""
        def on_data_received(busID, data):
            """Callback for handling received data."""
            # Parse and handle the message here
        
        try:
            log(DB.LOG_INFO, f"Connecting DomBus {busID} on port {port} {baudrate}bps ...")
            transport, protocol = await serial_asyncio.create_serial_connection(
                self.loop,
                lambda: DomBusProtocol(busID, on_data_received),
                port,
                baudrate=baudrate,
            )
        except Exception as e:
            log(DB.LOG_INFO, f"Error connecting DomBus bus {busID} on port {port}: {e}. Retry in {self.retryConnection}s")
            buses[busID]['protocol'] = None
        else:
            log(DB.LOG_DEBUG, f"Bus {busID} added on port {port}.")
            buses[busID]['protocol'] = protocol


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
        options = SubscribeOptions(noLocal=True)
        if mqttversion == 'old':
            async with mqtt['client'].messages() as messages:
                await mqtt['client'].subscribe(topics, options=options)  # Subscribe to all topics
                log(DB.LOG_INFO, f"Subscribed to topics {topics}")

                async for message in messages:
                    if str(message.topic)[-6:] != '/state' and '"_sender": "dbp"' not in message.payload.decode():  # ignore msg generated by me, and state messages (only commands should be received)
                        log(DB.LOG_MQTTRX, f"Received on {message.topic}: {message.payload.decode()}")
                        # check topic  /dombus/platform/devID/set
                        # check topic  /dombus/platform/devID/state  Off
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
                            log(DB.LOG_MQTTRX, "Received topic not in valid format")
#            else:
#                log(DB.LOG_DEBUG, f"Received ignored msg from {message.topic}: {message.payload.decode()}")

        else:
            #aiomqtt, new version of asyncio_mqtt
            await mqtt['client'].subscribe(topics, options=options)  # Subscribe to all topics
            log(DB.LOG_INFO, f"Subscribed to topics {topics}")

            async for message in mqtt['client'].messages:
                if str(message.topic)[-6:] != '/state' and '"_sender": "dbp"' not in message.payload.decode():  # ignore msg generated by me, and state messages (only commands should be received)
                    log(DB.LOG_MQTTRX, f"Received on {message.topic}: {message.payload.decode()}")
                    # check topic  /dombus/platform/devID/set
                    # check topic  /dombus/platform/devID/state  Off
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
                        log(DB.LOG_MQTTRX, "Received topic not in valid format")
#            else:
#                log(DB.LOG_DEBUG, f"Received ignored msg from {message.topic}: {message.payload.decode()}")
   

    async def _mqttPublishFromQueue(self):
        """Process the publish queue asynchronously."""
        while self.mqttConnected:
            topic, message = await self.loop.run_in_executor(None, self.mqttPublishQueue.get)
            # Publish the message
            log(DB.LOG_MQTTTX, f"Publish to {topic}: {message}")
            try:
                await mqtt['client'].publish(topic, message, qos=1)
            except Exception as e:
                log(DB.LOG_ERR, f"MQTT error while publishing a message: {e}\nRestart MQTT")
                # Reconnect to MQTT broker
                await self.mqttDisconnect()
                await self.add_mqtt()
            else:
                self.mqttPublishQueue.task_done()

    def mqttPublish(self, topic: str, payload: any):
        """Send message to a queue, to send it asyncronously"""
        if isinstance(payload, (dict, list)):
            payload['_sender'] = 'dbp'  # add a tag to identify msg sent by me, to ignore loopback mqtt commands 
            message = json.dumps(payload)
        else:
            message = str(payload)
        self.mqttPublishQueue.put((topic, message))

    def isPrivateIP(self, ip_str):
        """Check if IP is in private ranges"""
        try:
            ip = ipaddress.ip_address(ip_str)
            return ip.is_loopback or ip.is_private
        except ValueError:
            return False

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
        # if telnet connection from private/localhost IP => no password required
        if self.isPrivateIP(clientIP)==False and 'password' in telnet and len(telnet['password'])>0:
            # handle remote connections from non-local IP address asking for a password.
            for i in range (1, 4):
                writer.write(b"Password required for external connection: ")
                password = await reader.readline()
                if password.decode().strip() == telnet['password']:
                    i=0; break
                log(DB.LOG_INFO, f"Telnet: {clientIP} entered a wrong password: {password.decode().strip()}")
                await asyncio.sleep(i)
            if i != 0:
                # close telnet connection
                del telnet['clients'][writer]
                writer.close()
                await writer.wait_closed() 

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
                line = 0
                for message in data.decode().split('\n'):
                    if line == 0 or message.strip() != '':
                        log(DB.LOG_TELNET, f"Received {message.strip()}")
                        if not writer:
                            # Connection closed by "quit" command?
                            break
                        await self.handleCmd(message.strip(), writer) # parse commands
                    line += 1

        except ConnectionResetError:
            log(DB.LOG_INFO, f"Telnet connection closed by {clientIP}")
        except Exception as e:
            log(DB.LOG_INFO, f"Telnet connection error or quit command: {e}")
        finally:
            del telnet['clients'][writer]
            writer.close()
            await writer.wait_closed()


    async def handleCmd(self, message, writer):
        """Handle commands received from telnet port"""
        cmd = message.split(maxsplit=2) # ['show', 'module', '0xffe3 on bus 1']
        if len(cmd) >= 1:
            if cmd[0] in self.commands:
                await self.commands[cmd[0]]['cmd'](cmd[1:], writer)
            else:
                writer.write(f'Invalid command {cmd[0]}: please type "help" for a list of commands\r\n> '.encode()) 
        writer.write(b'\r\n> ')
        await writer.drain()


    async def cmd_help(self, args, writer):
        """Send back an help text"""
        if args and args[0] in self.commands:
            writer.write(f'{self.commands[ args[0] ][ "help" ]}\r\n'.encode())
        else:
            writer.write(f'This interface permits to check and set configuration for a DomBus network of home automation modules.\r\nAvailable commands:\r\n'.encode())
            for cmd in self.commands:
                hs=re.sub('\r\n', '\r\n           ', self.commands[ cmd ][ 'help' ])
                writer.write(f'{cmd:10} {hs}\r\n\r\n'.encode())

    async def cmd_refresh(self, args, writer):
        """Send whole list of devices to the domotic controller"""
        # cmd_refresh() => send all devices
        # cmd_refresh(["reset"]) => remove and create again all devices
        # cmd_refres( args, writer ) => send or recreate all devices with output on telnet session
        dlist = []
        for dev in Devices: # sort by devID
            bisect.insort(dlist, dev)
        for dev in dlist:
            d = Devices[dev]
            if (dev >> 16) in Modules:
                resetReq = None
                if args and args[0]:
                    resetReq = args[0]  # refresh reset => send "reset" as 4th parameter to remove previous entity and create a new one
                if writer:
                    writer.write(f'Sending configuration refresh for device {d.devIDname} portType={d.portType:08x} platform={d.ha["p"]}...\r\n'.encode())
                d.updateFromBus(DB.UPDATE_CONFIG, None, None, resetReq)
                d.updateFromBus(DB.UPDATE_VALUE, d.value, d.counterValue)
            else:
                if writer:
                    writer.write(f'Skip sending configuration for device {d.devIDname}: module {(dev >> 16):06x} not alive or not received yet!\r\n'.encode())
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
                writer.write(f'- {b:02x}: {buses[b]["serialPort"]:20} {"CONNECTED" if "protocol" in buses[b] else "DISCONNECTED"}\r\n'.encode())


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

    async def cmd_rmmodule(self, args, writer):
        """Remove a module for the selected bus"""
        for arg in args:
            try:
                addr = int(arg, 16)
            except ValueError:
                writer.write(f'Invalid module address: {arg}. Must be like "ffe3" or "1" or "123c"!\r\n'.encode())
            else:
                frameAddr = None
                if addr == 0 or addr == 0xffff:
                    writer.write(b'Invalid address: cannot be 0 or ffff\r\n')
                elif addr < 0xffff:
                    frameAddr = (self.selectedBus << 16) + addr
                elif addr < 0xffffff:
                    frameAddr = addr
                else:
                    writer.write(b'Invalid address: should be between 1 and fffe (only addr) or between 10001 to fffffe (with bus number)\r\n')
                # Check that module frameAddr exists
                if frameAddr:
                    if frameAddr not in Modules:
                        writer.write(f'Module with address {(frameAddr & 0xffff):x} does not exist in bus {(frameAddr >> 16):x}\r\n'.encode())
                    else:
                        # Module exists: delete all devices
                        for d in list(Devices.keys()):
                            if (d >> 16) == frameAddr:
                                # Matches 
                                writer.write(f'Removing port {(d & 0xffff):x} for device {(frameAddr&0xffff):x} on bus (frameAddr>>16)...\r\n'.encode())
                                if mqtt['enabled'] != 0:
                                    self.mqttPublish(Devices[d].topicConfig, "") # Remove entity from HA
                                    if Devices[d].topic2Config:
                                        self.mqttPublish(Devices[d].topic2Config, "") # Remove associated entity from HA
                                del Devices[d]
                        del Modules[frameAddr]
                        # Debugging...
                        writer.write(b'Current devices:\r\n')
                        for d in list(Devices.keys()):
                            writer.write(f'{d:x}\r\n'.encode())
                        setSaveDataTimeout()


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
            devID = (self.selectedBus << 32) + (self.selectedModule << 16) + port
            if devID in Devices:
                # Device exists: check new configuration 
                portType = None
                portOpt = None
                portName = None
                options = {}
                ha = {}
                dcmd = []
                dcmdConf = ''
                
                # check telnet keywords:
                for c in args[1].split(','):
                    try:
                        cmd=c.split('=')[0]
                        val=c.split('=')[1]
                    except Exception:
                        val = None
                    cmdu = cmd.upper()
                    log(DB.LOG_DEBUG,f"cmd={cmd} val={val}")
                    # c='DCMD(Pulse)=ff37.1:Toggle'
                    # cmd='DCMD(Pulse)'
                    # cmdu='DCMD(PULSE)'
                    # val='ff37.1:Toggle'
                    if cmdu in DB.PORTTYPES:
                        log(DB.LOG_DEBUG,f"New portType {cmdu}")
                        portType = DB.PORTTYPES[cmdu]
                    elif cmdu in DB.PORTOPTS:
                        log(DB.LOG_DEBUG,f"New portOpt {cmdu}")
                        portOpt = DB.PORTOPTS[cmdu]
                    elif cmdu in DB.OPTIONS_NAMES and val is not None:
                        log(DB.LOG_DEBUG,f"New option {cmdu}")
                        options[cmdu] = val
                    elif cmd.lower() in DB.HA_NAMES and val is not None:
                        log(DB.LOG_DEBUG,f"New ha attribute {cmd.lower()}")
                        ha[cmd.lower()] = val
                    elif cmdu[:5] == "DCMD(":
                        # parse DCMD configuration
                        errmsg=''
                        d = [ DB.DCMD_IN_EVENTS['NONE'], 0, 0, 0, 0, DB.DCMD_OUT_CMDS['NONE'], 0 ] #temp list to store a DCMD command
                        opt = re.sub("ERROR=.*", "", c) #remove any Error=blablabla from the command
                        optu = opt.upper()
                        inputs = re.search(r'DCMD\((.+)\)=(.+\..+:.+)', optu)
                        if inputs:
                            #syntax of DCMD command semms to be ok
                            inArr = inputs.group(1).split(':')    #inArr=['Value','0','20.5'] (inputs)
                            outArr=inputs.group(2).split(':')   #
                            if (len(inArr)>=1):
                                log(DB.LOG_INFO,f"DCMD: {opt} Input event={inArr} Output command={outArr}")
                                if (inArr[0] in DB.DCMD_IN_EVENTS):
                                    d[0]=DB.DCMD_IN_EVENTS[inArr[0]]
                                    d[1]=0
                                    d1ok=0
                                    d[2]=0
                                    d2ok=0
                                    if (len(inArr)>=2):
                                        # inArr[1] contains a temperature, humidity, voltage,... convert this value to a integer representation used by DomBus
                                        try:
                                            d[1]=float(inArr[1])
                                        except:
                                            errmsg+="ValueLow should be a number, like 20.5. "
                                            d[1]=0
                                        else:
                                            d1ok=1

                                        try:
                                            d[2]=float(inArr[2])
                                        except:
                                            errmsg+="ValueHigh should be a number, like 21.2. "
                                            d[2]=0
                                        else:
                                            d2ok=1
                                        if (inArr[0]=='VALUE'):
                                            #convert d[1] and d[2] in temperature, RH, voltage, value according to the sensor type and A and B parameters
                                            if (d1ok):
                                                d[1]=convertValueToDombus(Devices[Unit],d[1])
                                            if (d2ok):
                                                d[2]=convertValueToDombus(Devices[Unit],d[2])
                                            log(DB.LOG_DEBUG,f"d[1]={d[1]} d[2]={d[2]}")
                                    if (len(outArr)>=2):
                                        if (outArr[1] in DB.DCMD_OUT_CMDS):
                                            #outArr[0]=101.4
                                            #outArr[1]=ON
                                            hwaddrport=outArr[0].split('.')
                                            #TODO: ALL.BLIND
                                            d[3]=int(hwaddrport[0],16)
                                            d[4]=int(hwaddrport[1],16)
                                            d[5]=int(DB.DCMD_OUT_CMDS[outArr[1]])
                                            d[6]=0    #outValue
                                            if (len(outArr)>=3):
                                                #outArr[2]=30m
                                                # From 0 to 60s => 31.25ms resolution      0=0, 1920=60s
                                                # From 1m to 1h with 1s resolution         1921=61s, 3540+1920=5460=1h
                                                # From 1h to 1d with 1m resolution         5461=1h+1m, 1380+5460=6840=24h
                                                # From 1d to forever with 1h resolution    6841=25h
                                                if (outArr[2].isnumeric()):
                                                    #value * 31.5ms
                                                    d[6]=int(outArr[2])
                                                else:
                                                    outValue=(outArr[2][:-1])
                                                    outUM=outArr[2][-1:]
                                                    #value in seconds
                                                    if (outValue.isnumeric()):
                                                        outValue=int(outValue)
                                                        if (outUM=='S'):    #seconds
                                                            if (outValue<=60):
                                                                d[6]=outValue*32
                                                            elif (outValue<=3600):
                                                                d[6]=1920+(outValue-60)
                                                        elif (outUM=='M'): #minutes
                                                            if (outValue<=1):
                                                                d[6]=outValue*60*32
                                                            elif (outValue<=60):
                                                                d[6]=1920+(outValue-1)*60
                                                            elif (outValue<=1440):
                                                                d[6]=5460+(outValue-60)
                                                        elif (outUM=='H'):  #hours
                                                            if (outValue<=1):
                                                                d[6]=outValue*5460
                                                            elif(outValue<=24):
                                                                d[6]=5460+(outValue-1)*60
                                                            else:
                                                                d[6]=6840+(outValue-24)
                                                        elif (outUM=='D'):
                                                            d[6]=6840+(outValue-1)*24
                                                        if (d[6]>65535):
                                                            d[6]=1826*24+6840 #max 5 years = 1826 days
                                                            errmsg+='Max time = 1826 days;'
                                            dcmd.append(d)  #add record to dcmd[]
                                        else:
                                            errmsg="Command not recognized;"
                                            log(DB.LOG_WARN,f"DCMD: Command {outArr[1]} not recognized, possible commands={list(DCMD_OUT_CMDS)}")
                                            log(DB.LOG_DEBUG,"DCMD: {opt}")
                                    else:
                                        errmsg="At least HWADDR.PORT:COMMAND expected after =;"
                                        log(DB.LOG_WARN,"DCMD: Address.Port:Command : invalid syntax. Address.Port="+outArr[0]+" ,Command="+outArr[1])
                                        log(DB.LOG_DEBUG,"DCMD: "+opt)
                                else:
                                    errmsg="Event not recognized inside ();"
                                    log(DB.LOG_WARN,"DCMD: Event not recognized: event="+inArr[0]+" , possible events="+str(list(DCMD_IN_EVENTS.keys())))
                                    log(DB.LOG_DEBUG,"DCMD: "+opt)
                            else:
                                errmsg="At least 1 parameter expected inside ();"
                                log(DB.LOG_WARN,"DCMD: no parameters specified inside ()")
                                log(DB.LOG_DEBUG,"DCMD: "+opt)
                        else:
                            errmsg="Invalid syntax;"
                            log(DB.LOG_WARN,"DCMD: invalid syntax")
                            log(DB.LOG_DEBUG,"DCMD: "+opt)
                        if (len(errmsg)>0):
                            opt+=':Error='+errmsg+': Valid command is like DCMD(Value:0:20.5)=101.1:ON:30m'
                            #reset values inside the current DCMD array
                        # DCMD is OK
                        if dcmdConf != '': dcmdConf += ','
                        dcmdConf+=opt
######
                    else:
                        log(DB.LOG_DEBUG,f"Ignoring {cmd}")
                    
                self.parseConfiguration(devID, portType, portOpt, portName, options, ha, dcmd, dcmdConf, None, writer) 
            else:
                if self.selectedModule == 0 or (devID>>16) not in Modules: 
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
        devIDbase = (self.selectedBus << 32) + (self.selectedModule << 16)
        for p in range(1, 512):
            devID = devIDbase + p
            if devID in Devices:
                writer.write(f'- {Devices[devID].portName}: {Devices[devID].portConf}\r\n'.encode())

    def removeModule(self, devID):
        """Remove the module with specified devID from DomBusGateway and from MQTT"""


    def parseConfiguration(self, devID, portType, portOpt, portName, options:dict, ha:dict, dcmd: list = [], dcmdConf: str = '', value:int = None, writer = None):
        """Received options and ha dicts: check configuration ond call updateDeviceConfig to update both Device and DomBus module"""
        # confString: "ID=01ff37_01,IN_DIGITAL,INVERTED,DCMD(Pulse)=01ff36_07:Toggle,DCMD(Pulse1)=01ff36_08:Toggle"
        optionsNew = {}
        haNew = {}
        cal = None
        d = None

        if devID in Devices:
            d = Devices[devID]

        if d and d.portType == portType:
            # device already exist and portType not changed by the user => update options and ha dictionary
            optionsNew = d.options.copy()
            haNew = d.ha.copy()
            self.dcmd = {}
            self.dcmdConf = ''
        else:
            # new device
            optionsNew['A'] = 1
            optionsNew['B'] = 0
            if portType in DB.PORTTYPES_HA:
                haNew = DB.PORTTYPES_HA[portType].copy()
        optionsNew.update(options)
        haNew.update(ha)    # merge existing/standard configuration with parameters set by the user

        # Now check parameters #TODO
        if 'DIVIDER' in optionsNew:
            optionsNew['A'] = 1 / float(optionsNew['DIVIDER'])
        if 'A' in optionsNew:
            optionsNew['A'] = float(optionsNew['A'])
        if 'B' in optionsNew:
            optionsNew['B'] = float(optionsNew['B'])
        if 'PRECISION' in optionsNew:
            try:
                precision = int(optionsNew['PRECISION'])
            except:
                log(DB.LOG_ERR, f"Invalid precision: should be a positive number indicating the number of digits after the decimal point")
            else:                
                optionsNew['PRECISION'] = precision

        # Create device, if not exist
        if not d:
            # device object does not exist => create it
            log(DB.LOG_INFO,"[parseConfiguration] Creating new device...")
            d = DomBusDevice(devID, portType, portOpt, portName, optionsNew, haNew) # Create device object with minimal configuration
            Devices[devID] = d 

        if d.busID in buses and 'protocol' in buses[d.busID]:
            # Serial port is active
            # Update MQTT and DomBus module
            log(DB.LOG_DEBUG,"[parseConfiguration] Calling updateDeviceConfig...")
            d.updateDeviceConfig(portType, portOpt, cal, dcmd, dcmdConf, optionsNew, haNew, value)  # Update configuration (setting CAL, DCMD, device_class, ...)
        else:
            log(DB.LOG_INFO, "[parseConfiguration] Serial port for the associated device is not active now! Cannot configure DomBus module")
            if writer:
                writer.write(b"Serial port for the associated device is not active now! Cannot configure DomBus module\r\n")

    def cmd_quit(self, args, writer):
        """Exit from telnet session"""
        writer.close()

def sigtermHandler(signum, frame):
    """Manage the TERM signal"""
    saveData()
    log(DB.LOG_INFO, "Exit!")
    sys.exit(0)

def saveData(): 
    """Save Modules, Devices dictionaries"""
    log(DB.LOG_INFO,"####### Saving Modules and Devices data... #######")
    with open(modulesPath, 'w', encoding='utf-8') as f:
        json.dump(Modules, f, indent=2)
    with open(devicesPath, 'w', encoding='utf-8') as f:
        json.dump({k: v.to_dict() for k, v in Devices.items()}, f, indent=2)

####################################################################### main() #################################################################################

if __name__ == "__main__":
    async def main():
        global manager, debugLevel
        manager = DomBusManager()

        signal.signal(signal.SIGTERM, sigtermHandler)

#        for bus in buses:
#            try: 
#                await manager.add_bus(busID=bus, port=buses[bus]['serialPort'], baudrate=115200)
#            except Exception as e:
#                log(DB.LOG_ERR, f"Error opening serial port {buses[bus]['serialPort']}: {e}")
        asyncio.create_task(manager.check_buses()) # Check serial ports and start connection even in case of failure


        if mqtt['enabled'] != 0:
            # await manager.add_mqtt()
            asyncio.create_task(manager.add_mqtt())

        if telnet['enabled'] != 0:
            # listen to TCP port waiting for connections and commands
            asyncio.create_task(manager.addTelnetServer())
        
        await manager.cmd_refresh(None, None) # Send all devices to HA
        await asyncio.Event().wait()

    ############### main ################
    # parsing args...
    parser = argparse.ArgumentParser(prog='DomBusGateway', description='DomBus 2 MQTT bridge')

    parser.add_argument('--data_dir', '-dd', type=str, default='',
            help='Data dir for persistent data (Devices and Modules): default "/data" in case of add-on or docker container, "data" in case of DomBusGateway running as a deaemon')
    parser.add_argument('--debug_level', '-dl', type=int, default=-1,
            help='Debug level: 0=OFF, 1=Errors, 3=Warnings, 7=Info, 15=Debug, +16=RX, +32=TX, +64=DCMD, +256=MQTTRX, +512=MQTTTX, +65536=Telnet')
    parser.add_argument('--bus1_port', '-b1', type=str, default='',
            help='Serial port for bus1, for example /dev/ttyUSB0')
    parser.add_argument('--bus2_port', '-b2', type=str, default='',
            help='Serial port for bus2, for example /dev/ttyUSB1')
    parser.add_argument('--bus3_port', '-b3', type=str, default='',
            help='Serial port for bus3, for example /dev/ttyUSB2')
    parser.add_argument('--bus4_port', '-b4', type=str, default='',
            help='Serial port for bus4, for example /dev/ttyUSB3')
    parser.add_argument('--mqtt_host', '-mh', type=str, default='',
            help='Hostname or IP address of the MQTT broker, for example homeassistant.local')
    parser.add_argument('--mqtt_port', '-mp', type=int, default=-1,
            help='TCP port of the MQTT broker, for example 1883')
    parser.add_argument('--mqtt_user', '-mu', type=str, default='',
            help='Username that can access the MQTT broker, for example dombus. On HAOS, a user must be created with this name')
    parser.add_argument('--mqtt_pass', '-ms', type=str, default='',
            help='Password for the user accessing the MQTT broker')
    parser.add_argument('--telnet_pass', '-ts', type=str, default='',
            help='Password for telnet from remote connections')

    args = parser.parse_args()
    if args.data_dir and args.data_dir != '':       dataDir = args.data_dir
    if args.debug_level and args.debug_level>=0:    debugLevel = args.debug_level
    if args.bus1_port and args.bus1_port != '':
        if 1 not in buses: buses[1]={}     
        buses[1]['serialPort']=args.bus1_port
        if args.bus2_port and args.bus2_port != 'null':
            if 2 not in buses: buses[2]={}     
            buses[2]['serialPort']=args.bus2_port
            if args.bus3_port and args.bus3_port != 'null':
                if 3 not in buses: buses[3]={}     
                buses[3]['serialPort']=args.bus3_port
                if args.bus4_port and args.bus4_port != 'null':
                    if 4 not in buses: buses[4]={}     
                    buses[4]['serialPort']=args.bus4_port
    if args.mqtt_host and args.mqtt_host != '':
        mqtt['host'] = args.mqtt_host
    if args.mqtt_port and args.mqtt_port>0:
        mqtt['port'] = args.mqtt_port
    if args.mqtt_user and args.mqtt_user != '':
        mqtt['user'] = args.mqtt_user
    if args.mqtt_pass and args.mqtt_pass != '':
        mqtt['pass'] = args.mqtt_pass
    if args.telnet_pass and args.telnet_pass != '':
        telnet['password'] = args.telnet_pass

    # logging
    if logFile: 
        logHandler = RotatingFileHandler(
            logFile,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,               # Keep 5 rotated logs
            encoding="utf-8"
        )
    else:
        logHandler=logging.StreamHandler(sys.stdout)

    logging.basicConfig(
        handlers=[logHandler],
        level=logging.INFO,
        format="%(asctime)s - %(message)s"
    )
    """handlers=[logHandler],"""

    # check that data directory exists
    dataPath = Path(dataDir)
    dataPath.mkdir(parents=True, exist_ok=True)

    modulesPath = dataPath / 'Modules.json'
    devicesPath = dataPath / 'Devices.json'

    # load saved data
    tempdict = {}
    if modulesPath.exists():
        with open(modulesPath, 'r', encoding='utf-8') as f:
            tempdict = json.load(f)
            Modules = {int(k): v for k, v in tempdict.items()}
    else:
        log(DB.LOG_WARN, f"Modules data file {dataDir}/Modules.json does not exist")
    if devicesPath.exists():
        with open(devicesPath, 'r', encoding='utf-8') as f:
            tempdict = json.load(f)
            Devices = {int(k): DomBusDevice.from_dict(v) for k, v in tempdict.items()}
    else:
        log(DB.LOG_WARN, f"Devices data file {dataDir}/Devices.json does not exist")
    del tempdict

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log(DB.LOG_INFO, "Keyboard interrupt => exit")
    except Exception as e:
        log(DB.LOG_INFO, f"Receive exception: {e}")

    if saveDataTimeout: saveData()  # save Modules, Devices, ...         


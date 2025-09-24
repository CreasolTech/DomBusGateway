# DomBusGateway basic configuration
# DO NOT MODIFY BECAUSE IT MAY BE OVERWRITTEN BY git pull
# INSTEAD, MODIFY THE FILE local/dombusgateway_conf_local.py

import dombusgateway_const as DB # constants

datadir = 'data'    # directory where Devices configuration and other data will be saved    

# Debugging level (it's possible to combine more items): 
# DB.LOG_NONE   => Nothing
# DB.LOG_ERR    => Errors
# DB.LOG_WARN   => Warnings + Errors
# DB.LOG_INFO   => Info + Warnings + Errors
# DB.LOG_DEBUG  => Debug + Info + Warnings + Errors
# DB.LOG_DUMPRX => Dump RX frames on DomBus buses
# DB.LOG_DUMPTX => Dump TX frames on DomBus buses
# DB.LOG_DUMPDCMD => Dump DCDM frames exchanged between modules
# DB.LOG_MQTTRX => Dump messages received from MQTT broker
# DB.LOG_MQTTTX => Dump messages transmitted to MQTT broker
# DB.LOG_TELNET => Dump messages received from telnet socket
# Example: debugLevel = (DB.LOG_DEBUG | DB.LOG_DUMPRX | DB.LOG_DUMPTX | DB.LOG_DUMPDCMD)
# Example: debugLevel = (DB.LOG_DEBUG | DB.LOG_DUMPRX | DB.LOG_DUMPTX | DB.LOG_DUMPDCMD | DB.LOG_MQTTRX)
#debugLevel = (DB.LOG_DEBUG | DB.LOG_DUMPRX | DB.LOG_DUMPTX | DB.LOG_DUMPDCMD | DB.LOG_MQTTRX | DB.LOG_MQTTTX)
#debugLevel = (DB.LOG_DEBUG | DB.LOG_DUMPDCMD | DB.LOG_MQTTRX | DB.LOG_MQTTTX | DB.LOG_DUMPTX | DB.LOG_DUMPRX | DB.LOG_TELNET)
debugLevel = (DB.LOG_DEBUG | DB.LOG_DUMPRX | DB.LOG_DUMPTX | DB.LOG_DUMPDCMD | DB.LOG_TELNET)

logFile = "/var/log/dombusgateway/info.log"
# logFile = None      # print log to stdout    

# Dombus buses (1 or more serial RS485 buses attached to DomBus modules
buses = {
    1: { 'serialPort': '/dev/ttyUSB0', }, # first bus serving ground floor
#    2: { 'serialPort': '/dev/ttyUSBdombus2', }, # second bus serving 2nd floor
}

# If more than one serial port is used, it's better to identify the USB ports connected to the USB/RS485 adapters: check info below
"""
Assuming to use Linux (Debian, Ubuntu, Raspbian, ...), it may happen that more RS485/USB adapters are connected to the same computer, 
but it's important to identify the serial port in a persisten way to avoid troubles: if they have the same vendor id, product id and serial number, 
you have to follow the step-by-step procedure: assuming that ttyUSB0 is used as dombus #1, and ttyUSB1 as dombus #2

    find the devpath for the bus #1, corresponding with ttyUSB0 in this example, running the command 
      udevadm info -a /dev/ttyUSB0|egrep 'ATTRS.(idVendor|idProduct|devpath)'|head -n3

    Assuming that result is

     ATTRS{devpath}=="1.5"
     ATTRS{idProduct}=="7523"
     ATTRS{idVendor}=="1a86"

    create/edit the file /etc/udev/rules.d/99-serial-ports.rules adding the line

    SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", ATTRS{devpath}=="1.5", SYMLINK+="ttyUSBdombus1"

    to set that the USB/RS485 adapter plugged to the USB port 1.5 should be named /dev/ttyUSBdombus1
    Repeat the steps above for the next RS485/USB serial adapters, to set the device to ttyUSBdombus2, ....

    Run the command    systemctl restart udev   to load the new configuration, then unplug and plug again the RS485/USB adapters

"""

# MQTT parameters: set mqttEnabled = 0 to disable this feature
mqtt = {
    'enabled':      1,                  # 0 => disabled, 1 => enabled
    'host':         '127.0.0.1',        # IP address or hostname for the MQTT broker (default '127.0.0.1')
    'port':         1883,               # MQTT broker port (default 1883)
    'user':         'domoticz',         # MQTT username
    'pass':         'secret',           # MQTT password
    'topic':        'dombus',           # MQTT topic for the domotic controller
    'topicConfig':  'homeassistant',    # MQTT topic for the domotic controller
    'publishInterval':  300             # Republish entity values every 300 seconds, if they were not changed.
}

telnet = {
    'enabled':      1,                  # 0 => telnet port not enabled, 1 => enabled
    'port':         8023,               # port to listen
    'address':      '0.0.0.0',        # interface to bind to. '127.0.0.1' => localhost, '192.168.x.y' => LAN, '0.0.0.0' => all interfaces
}

try:
    from local.dombusgateway_conf_local import *
except:
    print("Local configuration file local/dombusgateway_conf_local.py does not exist: loading default configuration")

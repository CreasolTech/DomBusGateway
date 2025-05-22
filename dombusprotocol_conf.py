# DomBusProtocol configuration (may be modified by the user)
import dombusprotocol_const as DB # constants

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
debugLevel = (DB.LOG_DEBUG | DB.LOG_DUMPDCMD | DB.LOG_MQTTRX | DB.LOG_MQTTTX | DB.LOG_DUMPTX | DB.LOG_TELNET)

datadir = 'data'    # directory where Devices configuration and other data will be saved    

# Dombus buses (1 or more serial RS485 buses attached to DomBus modules
buses = {
    1: { 'serialPort': '/dev/ttyUSB1', },
    # 2: { 'serialPort': '/dev/ttyUSB1', },
}

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
    'address':      '127.0.0.1',        # interface to bind to. '127.0.0.1' => localhost, '192.168.x.y' => LAN, '0.0.0.0' => all interfaces
}

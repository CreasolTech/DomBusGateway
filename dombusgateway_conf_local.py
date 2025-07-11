# Here you can put your local configuration, overwriting the default configuration in dombusgateway_conf.py
# We'll try to never change this file, so you can update your local files using the "git pull" command in a safe mode.
# ** Before updating, anyway, please make a copy of your dombusgateway_conf_local.py **
# The following configuration overwrites default configuration in dombusgateway_conf.py , where you can find detail description of each parameter

#debugLevel = (DB.LOG_DEBUG | DB.LOG_DUMPRX | DB.LOG_DUMPTX | DB.LOG_DUMPDCMD | DB.LOG_MQTTRX | DB.LOG_MQTTTX)

# Dombus buses (1 or more serial RS485 buses attached to DomBus modules
# Please read dombusgateway_conf.py to know how to make serial devices static, unchangeable at reboot

buses = {
    1: { 'serialPort': '/dev/ttyUSBdombus1', },
    2: { 'serialPort': '/dev/ttyUSBdombus2', },
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


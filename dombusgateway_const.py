#DomBus constants for DomBus protocol rev.2
#
# ======================== Protocol 2 ========================
# 1B   2B         2B         1B     1B            1B   bytes string (odd length) 1B             1B    odd length                                    1B
# 0x3a dstAddr[2] srcAddr[2] length cmd|ACK|len/2 port parameters[1,3,5,7,9,11] cmd2|ACK|len2/2 port2 parameters2 cmd3|ACK|len3/2 port3 parameters3 CHECKSUM
# PREAMBLE DST    SRC 
# length = payload length, excluding checksum

FRAME_LEN_MIN=10    #Min length of frame for protocol 2 (including CMD + PORT + 1BYTE DATA)
FRAME_LEN_MAX=31    #max length for TX (devices cannot handle long frames)
FRAME_LEN=5
FRAME_HEADER=6
PREAMBLE=0x3a           #Preamble for protocol 2
CMD_LEN_MASK=0x07
CMD_MASK=0xf0
CMD_ACK=0x08

FRAME_OK = 0                # Frame OK
FRAME_INVALID_CHECKSUM = 1  # Invalid checksum

#DEBUG TX_RETRY=10                     #max number of retries
TX_RETRY=1                     #max number of retries
TX_RETRY_TIME=80                # ms: retry every TX_RETRY_TIME * 2^retry
PERIODIC_STATUS_INTERVAL=300    #seconds: refresh output status to device every 5 minutes
MODULE_ALIVE_TIME=900           #if no frame is received in this time, module is considered dead (and periodic output status will not be transmitted)

LASTRX=0        # first field in modules[]
LASTTX=1        # second field in modules[]
LASTSTATUS=2    # third field in modules[]
LASTRETRY=3     # forth field in modules[]: number of retries (used to compute the tx period)
LASTTYPE=4      # Modules field containing Type of module (e.g. DomBus31)
LASTFW=5        # Modules field containing Firmware version (e.g. 02j1)    

UPDATE_VALUE = 1                # Request update a device value (bitmask)
UPDATE_ACK = 2                  # Received ACK to a SET command => Send back to the controller the updated state   
UPDATE_CONFIG = 4               # Request update a device configuration (bitmask)
UPDATE_DCMD = 8                 # Request DCMD propagation (bitmask)


CMD_CONFIG=0x00                 #Config port
CMD_GET=0x10                    #Get status
CMD_SET=0x20                    #Set outputs/values
CMD_DCMD_CONFIG=0xe0            #Send DCMD configuration
CMD_DCMD=0xf0                   #Receive DCMD command from Dombus

SUBCMD_CALIBRATE=0x00           #Send calibration value to a temperature/humidity sensor
SUBCMD_SET=0x01                 #Send parameter 1 (16bit value)
SUBCMD_SET1=0x01                #Send parameter 1 (16bit value)
SUBCMD_SET2=0x02                #Send parameter 2 (16bit value)
SUBCMD_SET3=0x03                #Send parameter 3 (16bit value)
SUBCMD_SET4=0x04                #Send parameter 4 (16bit value)
SUBCMD_SET5=0x05                #Send parameter 5 (16bit value)
SUBCMD_SET6=0x06                #Send parameter 6 (16bit value)
SUBCMD_SET7=0x07                #Send parameter 7 (16bit value)
SUBCMD_SET8=0x08                #Send parameter 8 (16bit value)
SUBCMD_SET9=0x09                #Send parameter 9 (16bit value)
SUBCMD_SET10=0x0a               #Send parameter 10 (16bit value)
SUBCMD_SET11=0x0b               #Send parameter 11 (16bit value)
SUBCMD_SETMAX=0x10              #Send parameter 16

PORTTYPE_DISABLED=0x0000        #port not used
PORTTYPE_OUT_DIGITAL=0x0002     #digital, opto or relay output
PORTTYPE_OUT_RELAY_LP=0x0004    #relay output with lowpower PWM
PORTTYPE_OUT_LEDSTATUS=0x0008   #output used as led status
PORTTYPE_OUT_DIMMER=0x0010      #dimmer output, 0-100%
PORTTYPE_OUT_BUZZER=0x0020      #buzzer outputs (2 ports used as buzzer output, in push-pull)
PORTTYPE_OUT_FLASH=0x0020       #flash output, led, buzzer: same as OUT_BUZZER
PORTTYPE_IN_AC=0x0040           #input AC 50Hz (with optocoupler)
PORTTYPE_IN_DIGITAL=0x0080      #input digital
PORTTYPE_IN_ANALOG=0x0100       #input analog (ADC)
PORTTYPE_IN_TWINBUTTON=0x0200   #2 buttons connected to a single input through a resistor
PORTTYPE_IN_COUNTER=0x0400      #input pulses that increase a counter (incremental)
PORTTYPE_1WIRE=0x1000           #1 wire
PORTTYPE_SENSOR_DISTANCE=0x2000 #distance measurement (send a pulse and measure echo delay)
PORTTYPE_SENSOR_TEMP=0x4000     #Temperature
PORTTYPE_SENSOR_HUM=0x8000      #Relative Humidity
PORTTYPE_SENSOR_TEMP_HUM=0xc000 #Temp+Hum
PORTTYPE_SENSOR_ALARM=0x20000   #Triple biased alarm sensor
PORTTYPE_OUT_BLIND=0x01000000   #Blind output, close command (next port of DomBus device will be automatically used as Blind output, open command)
PORTTYPE_OUT_ANALOG=0x02000000  #0-10V output, 1% step, 0-100
PORTTYPE_CUSTOM=0x80000000      #custom port with only 1 function

PORTOPT_NONE=0x0000             #No options
PORTOPT_INVERTED=0x0001         #Logical inverted: MUST BE 1
PORTOPT_PULLUP=0x0002           #pullup enabled
PORTOPT_PULLDOWN=0x0004         #pulldown enabled
#.....
#note: since version
PORTOPT_SELECT=0x0002         #Custom port configured as a selection switch to show/set different values
PORTOPT_DIMMER=0x0004           #Dimmer slide
PORTOPT_LATCHING_RELAY=0x0008   #Latching relay, managed as normal On/Off switch
PORTOPT_EV3PSELECT=0x00fe     #Relay 2 of EVSE module used to enable 3phase 
PORTOPT_ADDRESS=0x0100          #Modbus device address
PORTOPT_IMPORT_ENERGY=0x0102    #Total import energy in Wh*10 [32bit]
PORTOPT_EXPORT_ENERGY=0x0104    #Total export energy in Wh*10 [32bit]
PORTOPT_VOLTAGE=0x0106          #Voltage in Volt/10
PORTOPT_POWER_FACTOR=0x0108     #Power factore 1/1000
PORTOPT_FREQUENCY=0x010a        #Frequency Hz/100
PORTOPT_CURRENT=0x010c

PORT_TYPENAME={PORTTYPE_OUT_DIGITAL:"Switch", PORTTYPE_OUT_RELAY_LP:"Switch", PORTTYPE_OUT_LEDSTATUS:"Switch", PORTTYPE_OUT_DIMMER:"Dimmer", PORTTYPE_OUT_BUZZER:"Selector Switch", PORTTYPE_OUT_FLASH:"Selector Switch", PORTTYPE_IN_AC:"Switch", PORTTYPE_IN_DIGITAL:"Switch", PORTTYPE_IN_ANALOG:"Voltage", PORTTYPE_IN_TWINBUTTON:"Selector Switch", PORTTYPE_IN_COUNTER:"Counter Incremental", PORTTYPE_SENSOR_HUM:"Humidity", PORTTYPE_SENSOR_TEMP:"Temperature", PORTTYPE_SENSOR_TEMP_HUM:"Temp+Hum", PORTTYPE_SENSOR_DISTANCE:"Distance", PORTTYPE_OUT_BLIND:"Switch", PORTTYPE_OUT_ANALOG:"Dimmer", PORTTYPE_CUSTOM:"Dimmer"}
    
PORTTYPES={
        "DISABLED":0x0000,          # port not used
        "OUT_DIGITAL":0x0002,       # relay output
        "OUT_RELAY_LP":0x0004,      # relay output
        "OUT_LEDSTATUS":0x0008,     # output used as led status
        "OUT_DIMMER":0x0010,        # dimmer output
        "OUT_FLASH":0x0020,         # buzzer output or flash or led flashing
        "OUT_BUZZER":0x0020,        # buzzer output (2 ports, push-pull)
        "IN_AC":0x0040,             # input AC 50Hz (with optocoupler)
        "IN_DIGITAL":0x0080,        # input digital
        "IN_ANALOG":0x0100,         # input analog (ADC)
        "IN_TWINBUTTON":0x0200,     # 2 buttons connected to a single input through a resistor
        "IN_COUNTER":0x0400,        # pulse counter
        "DISTANCE":0x2000,          # measure distance in mm
        "TEMPERATURE":0x4000,       # temperature
        "HUMIDITY":0x8000,          # relative humidity
        "TEMP+HUM":0xc000,          # temp+hum
        "SENSOR_ALARM":0x20000,     # Triple-biased sensor alarm
        "OUT_BLIND":0x01000000,     # blind with up/down/stop command
        "OUT_ANALOG":0x02000000,    # 0-10V output, 0-100, 1% step
        "CUSTOM":0x80000000,        # Custom port (enabled only if PORTOPT is specified)
        }

PORTTYPES_NAME = {
    0x00000000: "DISABLED",
    0x00000002: "OUT_DIGITAL",
    0x00000004: "OUT_RELAY_LP",
    0x00000008: "OUT_LEDSTATUS",
    0x00000010: "OUT_DIMMER",
    0x00000020: "OUT_FLASH",
    0x00000040: "IN_AC",
    0x00000080: "IN_DIGITAL",
    0x00000100: "IN_ANALOG",
    0x00000200: "IN_TWINBUTTON",
    0x00000400: "IN_COUNTER",
    0x00002000: "DISTANCE",
    0x00004000: "TEMPERATURE",
    0x00008000: "HUMIDITY",
    0x0000C000: "TEMP+HUM",
    0x00020000: "SENSOR_ALARM",
    0x01000000: "OUT_BLIND",
    0x02000000: "OUT_ANALOG",
    0x80000000: "CUSTOM",
}

PORTTYPES_HA = {
    0x00000000: {},
    0x00000002: {'p': 'switch', 'device_class': 'outlet'},
    0x00000004: {'p': 'switch', 'device_class': 'outlet'},
    0x00000008: {'p': 'light'},
    0x00000010: {'p': 'number', 'min': 0, 'max':100, 'step':1, 'unit_of_measurement': '%'},
    0x00000020: {'p': 'select', 'options': [ 'OFF', '1', '2', '3', '4', '5' ]}, # OUT_FLASH or OUT_BUZZER (the same)
    0x00000040: {'p': 'binary_sensor', 'device_class': 'power'},
    0x00000080: {'p': 'binary_sensor', 'device_class': 'door'},
    0x00000100: {'p': 'sensor', 'device_class': 'voltage', 'icon': 'mdi:current-dc', 'unit_of_measurement': 'V'},
    0x00000200: {'p': 'cover'}, # TWINBUTTON
    0x00000400: {'p': 'sensor', 'device_class': 'power', 'state_class': 'measurement', 'unit_of_measurement': 'W'},
    0x00002000: {'p': 'sensor', 'device_class': 'distance'},
    0x00004000: {'p': 'sensor', 'device_class': 'temperature', 'unit_of_measurement': '°C', 'suggested_display_precision': 1},
    0x00008000: {'p': 'sensor', 'device_class': 'humidity', 'unit_of_measurement': '%', 'suggested_display_precision': 0},
    0x0000C000: {'p': 'sensor', 'device_class': 'temperature'},
    0x00020000: {'p': 'binary_sensor', 'device_class': 'door', 'payload_on': 'open', 'payload_off': 'closed'},
    0x01000000: {'p': 'cover'},
    0x02000000: {'p': 'number', 'device_class': 'voltage', 'min': 0, 'max':10, 'step':0.1, 'unit_of_measurement': 'V'},
    0x80000000: {},
}


PORTOPTS={
        "NORMAL":0x0000,            # no options defined
        "INVERTED":0x0001,          # input or output is inverted (logic 1 means the corresponding GPIO is at GND
        "PULLUP":0x0002,
        "PULLDOWN":0x0004,
        # options for CUSTOM device only
        "SELECTOR":0x0002,            # Selection switch
        "DIMMER":0x0004,            # Dimmer
        "EV3PSELECT":0x00fe,      # EVSE 3PSELECT
        }

PORTOPTS_NAME={
    0x0000: 'NORMAL',
    0x0001: 'INVERTED',
    0x0002: 'PULLUP',
    0x0004: 'PULLDOWN',
    0x00fe: 'EV3PSELECT',
    }
    
SENSOR_ALARM_NAME = [ 'Closed', 'Open', 'Masked', 'Tampered', 'Shorted' ]   # state name for triple-biased alarm sensor

OPTIONS_NAMES = [ 'A', 'B', 'PRECISION', 'DIVIDER', 'OPPOSITE', 'FUNCTION', 'HWADDR', 'ADDR' ]

HA_NAMES = [ 'p', 'device_class', 'unit_of_measurement', 'payload_on', 'payload_off', 'min', 'max', 'step', 'options', 'icons' ]        

DCMD_IN_EVENTS={
        "NONE":     0,
        "OFF":      1,
        "ON":       2,
        "PULSE":    3,      #short pulse
        "PULSE1":   4,      #1s pulse
        "PULSE2":   5,      #2s pulse
        "PULSE4":   6,      #4s pulse
        "DIMMER":   7,      #Dimming control
        "VALUE":    8,      #value (sensor, voltage, ...)
        "ONUP":     9,      #Twinbutton UP
        "PULSEUP":  10,
        "PULSEUP1": 11,
        "PULSEUP2": 12,
        "PULSEUP4": 13,
        "PULSE3":   14,
        "PULSEUP3": 15,
        "MAX":      16,      #max number of events
        }

DCMD_OUT_CMDS={
        "NONE":     0,
        "OFF":      1,      #Turn off output
        "ON":       2,      #turn ON output
        "TOGGLE":   3,      #toggle output ON -> OFF -> ON -> ....
        "DIMMER":   4,      #set value
        "DOWN":     5,      #Blind DOWN
        "UP":       6,      #Blind UP
        "MAX":      7,      #Max number of commands
        }



TXQ_CMD=0
TXQ_CMDLEN=1
TXQ_CMDACK=2
TXQ_PORT=3
TXQ_ARGS=4
TXQ_RETRIES=5

LOG_NONE    =   0x00
LOG_ERR     =   0x01
LOG_WARN    =   0x03    # 2+1
LOG_INFO    =   0x07    # 4+2+1
LOG_DEBUG   =   0x0f    # 8+4+2+1
LOG_DUMPRX  =   0x10    # Log Rx frames from DomBus
LOG_DUMPTX  =   0x20    # Log Tx frames from DomBus
LOG_DUMPDCMD =  0x40    # Log DCMD commands
LOG_MQTTRX  =   0x100   # Log MQTT RX commands
LOG_MQTTTX  =   0x200   # Log MQTT TX commands
LOG_TELNET  =   0x10000 # Log TELNET messages

LOGNAME = {
    LOG_NONE:       '           ',
    LOG_ERR:        '[ERROR]    ',
    LOG_WARN:       '[WARNING]  ',
    LOG_INFO:       '[INFO]     ',
    LOG_DEBUG:      '[DEBUG]    ',
    LOG_DUMPRX:     '[DUMPRX]   ',
    LOG_DUMPTX:     '[DUMPTX]   ',
    LOG_DUMPDCMD:   '[DUMPDCMD] ',
    LOG_MQTTRX:     '[MQTTRX]   ',
    LOG_MQTTTX:     '[MQTTTX]   ',
    LOG_TELNET:     '[TELNET]   ',
}



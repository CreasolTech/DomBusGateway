#!/usr/bin/env bash
# DomBusGateway install file
# Designed by Creasol www.creasol.it
# Install the dombusgateway service, that is a bridge between DomBus network of domotic modules and MQTT with AutoDiscovery.
# Can be used to manage one or more DomBus module (EV charging system, solar tracking, relays, inputs, outputs, sensors, ...) with
# any industrial / home automation system supporting MQTT, like Home Assistant, Node-RED, OpenHAB, ioBroker, ...

# DomBusGateway is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.

INSTALLDIR="/opt"

function installPkg() {
	if [ "$INSTALL" == "apt" ]; then
		for pkg in $*; do 
			if `dpkg -s $pkg >/dev/null 2>/dev/null` ; then
				echo "*** Package $pkg already installed!"
			else
				echo "*** Installing $pkg... "
				apt -y -f --allow-remove-essential install $pkg
			fi
		done
	fi
}

function wait() {
	echo $*
	echo "*** Press a key to continue..."
	read x
}

echo -n "*** Checking if apt exists... "
INSTALL=apt
command -v apt
if [ $? -ne 0 ]; then
	echo "NO!"
	echo "*** ERROR: This system does not use apt. Please send a email to tech@creasol.it with information about your system"
	exit
fi

installPkg git gpw

PASS=`gpw 1 11`
	
echo -n "*** Checking if mosquitto is installed... "
command -v mosquitto
if [ $? -ne 0 ]; then
	echo "NO!"
	installPkg mosquitto
fi
if [ ! -r /etc/mosquitto/passwd ]; then
	echo "*** mosquitto passwd /etc/mosquitto/passwd does not exist"
	echo "password_file /etc/mosquitto/passwd" > /etc/mosquitto/conf.d/password_file.conf
	> /etc/mosquitto/passwd
fi
if [ -z `egrep ^dombus: /etc/mosquitto/passwd 2>/dev/null` ]; then  
	echo "*** Creating mosquitto user dombus with random generated password $PASS ..."
	mosquitto_passwd -b /etc/mosquitto/passwd dombus "$PASS"
fi

echo "*** Installing python dependencies... "
installPkg python3-pip python3-paho-mqtt python3-asyncio-mqtt python3-serial-asyncio

if [ ! -r "${INSTALLDIR}" ]; then
	mkdir "${INSTALLDIR}"
fi
cd  $INSTALLDIR

if [ ! -r "${INSTALLDIR}/DomBusGateway" ]; then
	echo "*** Clone DomBusGateway repository..."
	git clone https://github.com/CreasolTech/DomBusGateway
fi
cd "${INSTALLDIR}/DomBusGateway"
chown -R dombus *
chmod 700 dombusgateway.py

echo -n "*** Check if dombus user exists... "
id dombus	# check if user already exists
if [ $? -ne 0 ]; then 
	echo "NO!"
	echo "Creating system user 'dombus'... "
	useradd -r -d /opt/DomBusGateway -c 'DomBus gateway user' -G dialout,mosquitto -s /usr/sbin/nologin dombus
else
	echo "Yes"
	echo "User dombus already exist! Ok"
fi


if [ ! -r /etc/systemd/system/dombusgateway.service ]; then
	echo "Creating dombusgateway systemd service..."
	cp dombusgateway.service /etc/systemd/system

	echo "Enabling dombusgateway systemd service..."
	systemctl enable dombusgateway
else
	echo "Service dombusgateway already exists! Ok"
fi

echo "Running dombusgateway service..."
systemctl start dombusgateway


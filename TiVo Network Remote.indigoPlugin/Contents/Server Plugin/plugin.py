#! /usr/bin/env python
# -*- coding: utf-8 -*-
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
# TiVo Network Remote Control by RogueProeliator <rp@rogueproeliator.com>
# 	Indigo plugin designed to allow control of Series 3+ TiVo devices via control
#	pages using TiVo's built-in telnet interface designed for home automation
#	(Creston) systems.
#	
#	Command structure based on work done via the TiVo Community and documented
#	here: http://www.tivo.com/assets/images/abouttivo/resources/downloads/brochures/TiVo_TCP_Network_Remote_Control_Protocol_073108.pdf
#
#	Version 1.0:
#		Initial release of the plugin
#	Version 1.1:
#		Plugin converted to RPFramework
#		Added debug level options & menu item toggle
#		Added channel tracking device state
#		Added channel selector state/actions 
#	Version 1.1.6:
#		Added Standby IR code
#		Changed version check URL
#	Version 1.2.8:
#		Added better auto-discovery of the TiVo name and software version
#		Implement auto-reconnect for disconnected/failed connections
#	Version 2.0.1:
#		Updated API to use Indigo 7 API calls
#
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////


#/////////////////////////////////////////////////////////////////////////////////////////
# Python imports
#/////////////////////////////////////////////////////////////////////////////////////////
import os
import random
import re
import select
import socket
import string
import struct
import telnetlib

import RPFramework
import tivoRemoteDevice


#/////////////////////////////////////////////////////////////////////////////////////////
# Constants and configuration variables
#/////////////////////////////////////////////////////////////////////////////////////////
# beacon template for use when finding TiVo devices or for when attempting to get more
# information about them (name/version)
ANNOUNCE = """tivoconnect=1
method=%(method)s
platform=pc
identity=remote-%(port)x
services=TiVoMediaServer:%(port)d/http
"""


#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
# Plugin
#	Primary Indigo plugin class that is universal for all devices (TiVo instances) to be
#	controlled
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
class Plugin(RPFramework.RPFrameworkPlugin.RPFrameworkPlugin):

	#/////////////////////////////////////////////////////////////////////////////////////
	# Class construction and destruction methods
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# Constructor called once upon plugin class creation; setup the device tracking
	# variables for later use
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
		# RP framework base class's init method
		super(Plugin, self).__init__(pluginId, pluginDisplayName, pluginVersion, pluginPrefs, managedDeviceClassModule=tivoRemoteDevice)
	
	
	#/////////////////////////////////////////////////////////////////////////////////////
	# Data Validation functions... these functions allow the plugin or devices to validate
	# user input
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will be called to validate the information entered into the Device
	# configuration GUI from within Indigo
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def validateDeviceConfigUiEx(self, valuesDict, deviceTypeId, devId):	
		# check to see if there are already devices created for this plugin using the same
		# IP address
		for dev in indigo.devices.iter(u'self'):
			if devId != dev.id:
				if dev.pluginProps.get(u'tivoIPAddress') == valuesDict[u'tivoIPAddress']:
					errorMsgDict = indigo.Dict()
					errorMsgDict[u'tivoIPAddress'] = u'Device "' + dev.name + u'" already set to use this IP Address. You cannot have two Indigo devices attached to the same TiVo device.'
					return (False, valuesDict, errorMsgDict)
		
		# user input is all valid
		return (True, valuesDict)
		
		
	#/////////////////////////////////////////////////////////////////////////////////////
	# Configuration and Action Dialog Callbacks
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-	
	# This routine will be called from the user executing the menu item action to send
	# an arbitrary command code to the Onkyo receiver
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-	
	def sendArbitraryCommand(self, valuesDict, typeId):
		try:
			deviceId = valuesDict.get(u'targetDevice', u'0')
			commandCode = valuesDict.get(u'commandToSend', u'').strip()
		
			if deviceId == u'' or deviceId == u'0':
				# no device was selected
				errorDict = indigo.Dict()
				errorDict[u'targetDevice'] = u'Please select a device'
				return (False, valuesDict, errorDict)
			elif commandCode == u'':
				errorDict = indigo.Dict()
				errorDict[u'commandToSend'] = u'Enter command to send'
				return (False, valuesDict, errorDict)
			else:
				# send the code using the normal action processing...
				actionParams = indigo.Dict()
				actionParams[u'commandCode'] = commandCode
				self.executeAction(pluginAction=None, indigoActionId=u'sendArbitraryCommand', indigoDeviceId=int(deviceId), paramValues=actionParams)
				return (True, valuesDict)
		except:
			self.exceptionLog()
			return (False, valuesDict)

		
	#/////////////////////////////////////////////////////////////////////////////////////
	# Utility / helper routines
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called back to the plugin when the GUI configuration loads... it
	# should allow for selecting a TiVo device via a drop-down
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def findTiVoDevices(self, filter="", valuesDict=None, typeId="", targetId=0):
		tcd_id = re.compile('TiVo_TCD_ID: (.*)\r\n').findall
		tcds = {}

		# we must setup a listening server in order to listen for the TiVo returns, but
		# the port does not matter... find an available one
		hsock = socket.socket()
		attempts = 0
		while True:
			port = random.randint(0x8000, 0xffff)
			try:
				hsock.bind(('', port))
				break
			except:
				attempts += 1
				if attempts == 7:
					# can't bind to a port... return an empty list
					return []
		hsock.listen(5)

		# broadcast an announcement so that the TiVos will respond
		method = 'broadcast'
		try:
			usock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
			usock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
			usock.sendto(ANNOUNCE % locals(), ('255.255.255.255', 2190))
			usock.close()
		except:
			hsock.close()
			# the announcement broadcast failed.
			return []   

		# collect the queries made in response; these return quickly
		while True:
			isock, junk1, junk2 = select.select([hsock], [], [], 1)
			if not isock:
				break
			client, address = hsock.accept()
			message = client.recv(1500)
			client.close()
			tcd = tcd_id(message)[0]
			if tcd[0] >= '6' and tcd[:3] != '649':  # only support series 3 & 4 TiVos are supported
				tcds[tcd] = address[0]
		hsock.close()

		# unfortunately the HTTP requests don't include the machine names, 
		# so we find them by making direct TCD connections to each TiVo
		tivos = []
		for tcd, address in tcds.items():
			name, version = self.getTiVoNameAndVersion(address)
			tivos.append((address, RPFramework.RPFrameworkUtils.to_unicode(name) + u' (v' + RPFramework.RPFrameworkUtils.to_unicode(version) + u')'))
		return tivos
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will exchange TiVo Connect Discovery beacons in order to extract the
	# name and software version
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def getTiVoNameAndVersion(self, address):
		method = 'connected'
		port = 0
		our_beacon = ANNOUNCE % locals()
		machine_name = re.compile('machine=(.*)\n').findall
		swversion = re.compile('swversion=(\d*.\d*)').findall

		try:
			tsock = socket.socket()
			tsock.connect((address, 2190))

			tsock.sendall(struct.pack('!I', len(our_beacon)) + our_beacon)
			length = struct.unpack('!I', self.receiveBytesFromSocket(tsock, 4))[0]
			tivo_beacon = self.receiveBytesFromSocket(tsock, length)

			tsock.close()

			self.logger.threaddebug(u'Received beacon: ' + tivo_beacon)
			name = machine_name(tivo_beacon)[0]
			version = float(swversion(tivo_beacon)[0])
		except:
			name = address
			version = 0.0
			if self.debug == True:
				self.exceptionLog()
		return name, version
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# Reads the specified number of bytes from the socket
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-	
	def receiveBytesFromSocket(self, sock, length):
		block = ''
		while len(block) < length:
			add = sock.recv(length - len(block))
			if not add:
				break
			block += add
		return block
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine may be used by plugins to perform any upgrades specific to the plugin;
	# it will be called following the framework's update processing
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def performPluginUpgrade(self, oldVersion, newVersion):
		if oldVersion == u'':
			pluginBasePath = os.getcwd()
			jsonFilePath = os.path.join(pluginBasePath, "json.py")
			if os.path.exists(jsonFilePath):
				os.remove(jsonFilePath)
				self.logger.debug(u'Removed obsolete json.py file')
				
			jsonCompiledFilePath = os.path.join(pluginBasePath, "json.pyc")
			if os.path.exists(jsonCompiledFilePath):
				os.remove(jsonCompiledFilePath)
				self.logger.debug(u'Removed obsolete json.pyc file')
		
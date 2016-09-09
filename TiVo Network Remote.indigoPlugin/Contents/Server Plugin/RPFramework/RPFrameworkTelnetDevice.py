#! /usr/bin/env python
# -*- coding: utf-8 -*-
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
# RPFrameworkTelnetDevice by RogueProeliator <adam.d.ashe@gmail.com>
# 	This class is a concrete implementation of the RPFrameworkDevice as a device which
#	communicates via a telnet session
#	
#	THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# 	IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# 	FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# 	AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# 	LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# 	OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# 	SOFTWARE.
#
#	Version 0:
#		Initial release of the device framework
#	Version 4:
#		Added ability to connect to serial ports... contains breaking changes!
#	Version 8:
#		Added ability to connect to sockets directly
#		Removed plugin version check (moved to plugin level command queue)
#	Version 14:
#		Changed the serial connection readline to support Python v2.6
#	Version 16:
#		Set error state on server when a connection times out or fails
#	Version 17:
#		Added unicode support
#		Changed exception logging to use the logErrorMessage routine
#		Added ability to specify 0 as the polling interval (<= 0 turns off polling)
#	Version 18:
#		Changed error trapping to include EOFError as a re-connectable error
#
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////

#/////////////////////////////////////////////////////////////////////////////////////////
# Python imports
#/////////////////////////////////////////////////////////////////////////////////////////
import functools
import httplib
import indigo
import Queue
import os
import re
import serial
import string
import socket
import sys
import threading
import telnetlib
import time
import urllib

import RPFrameworkPlugin
import RPFrameworkCommand
import RPFrameworkDevice
import RPFrameworkUtils


#/////////////////////////////////////////////////////////////////////////////////////////
# Constants and configuration variables
#/////////////////////////////////////////////////////////////////////////////////////////
CONNECTIONTYPE_TELNET = 1
CONNECTIONTYPE_SERIAL = 2
CONNECTIONTYPE_SOCKET = 3

GUI_CONFIG_COMMANDREADTIMEOUT = u'commandReadTimeout'

GUI_CONFIG_ISCONNECTEDSTATEKEY = u'telnetConnectionDeviceStateBoolean'
GUI_CONFIG_CONNECTIONSTATEKEY = u'telnetConnectionDeviceStateName'
GUI_CONFIG_EOL = u'telnetConnectionEOLString'
GUI_CONFIG_SENDENCODING = u'telnetConnectionStringEncoding'
GUI_CONFIG_REQUIRES_LOGIN_DP = u'telnetConnectionRequiresLoginProperty'
GUI_CONFIG_STATUSPOLL_INTERVALPROPERTY = u'updateStatusPollerIntervalProperty'
GUI_CONFIG_STATUSPOLL_ACTIONID = u'updateStatusPollerActionId'

GUI_CONFIG_SERIALPORT_PORTNAME = u'serialPortName'
GUI_CONFIG_SERIALPORT_BAUDRATE = u'serialPortBaud'
GUI_CONFIG_SERIALPORT_PARITY = u'serialPortParity'
GUI_CONFIG_SERIALPORT_BYTESIZE = u'serialPortByteSize'
GUI_CONFIG_SERIALPORT_STOPBITS = u'serialPortStopBits'
GUI_CONFIG_SERIALPORT_READTIMEOUT = u'telnetDeviceReadTimeout'
GUI_CONFIG_SERIALPORT_WRITETIMEOUT = u'telnetDeviceWriteTimeout'

GUI_CONFIG_SOCKET_CONNECTIONTIMEOUT = u'socketConnectionTimeout'

GUI_CONFIG_TELNETDEV_EMPTYQUEUE_SPEEDUPCYCLES = u'emptyQueueReducedWaitCycles'

CMD_WRITE_TO_DEVICE = u'writeToTelnetConn'


#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
# RPFrameworkTelnetDevice
#	This class is a concrete implementation of the RPFrameworkDevice as a device which
#	communicates via a telnet session
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
class RPFrameworkTelnetDevice(RPFrameworkDevice.RPFrameworkDevice):
	
	#/////////////////////////////////////////////////////////////////////////////////////
	# Class construction and destruction methods
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# Constructor called once upon plugin class receiving a command to start device
	# communication. Defers to the base class for processing but initializes params
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def __init__(self, plugin, device, connectionType=CONNECTIONTYPE_TELNET):
		super(RPFrameworkTelnetDevice, self).__init__(plugin, device)
		self.connectionType = connectionType
		
		
	#/////////////////////////////////////////////////////////////////////////////////////
	# Processing and command functions
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is designed to run in a concurrent thread and will continuously monitor
	# the commands queue for work to do.
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def concurrentCommandProcessingThread(self, commandQueue):
		try:
			# retrieve the keys and settings that will be used during the command processing
			# for this telnet device
			isConnectedStateKey = self.hostPlugin.getGUIConfigValue(self.indigoDevice.deviceTypeId, GUI_CONFIG_ISCONNECTEDSTATEKEY, u'')
			connectionStateKey = self.hostPlugin.getGUIConfigValue(self.indigoDevice.deviceTypeId, GUI_CONFIG_CONNECTIONSTATEKEY, u'')
			self.hostPlugin.logger.threaddebug(u'Read device state config... isConnected: "' + RPFrameworkUtils.to_unicode(isConnectedStateKey) + u'"; connectionState: "' + RPFrameworkUtils.to_unicode(connectionStateKey) + u'"')
			telnetConnectionInfo = self.getDeviceAddressInfo()
		
			# establish the telenet connection to the telnet-based which handles the primary
			# network remote operations
			self.hostPlugin.logger.debug(u'Establishing connection to ' + RPFrameworkUtils.to_unicode(telnetConnectionInfo[0]))
			ipConnection = self.establishDeviceConnection(telnetConnectionInfo)
			self.failedConnectionAttempts = 0
			self.hostPlugin.logger.debug(u'Connection established')
			
			# update the states on the server to show that we have established a connectionStateKey
			self.indigoDevice.setErrorStateOnServer(None)
			if isConnectedStateKey != u'':
				self.indigoDevice.updateStateOnServer(key=isConnectedStateKey, value=u'true')
			if connectionStateKey != u'':
				self.indigoDevice.updateStateOnServer(key=connectionStateKey, value=u'Connected')
				
			# retrieve any configuration information that may have been setup in the
			# plugin configuration and/or device configuration	
			lineEndingToken = self.hostPlugin.getGUIConfigValue(self.indigoDevice.deviceTypeId, GUI_CONFIG_EOL, u'\r')
			lineEncoding = self.hostPlugin.getGUIConfigValue(self.indigoDevice.deviceTypeId, GUI_CONFIG_SENDENCODING, u'ascii')
			commandResponseTimeout = float(self.hostPlugin.getGUIConfigValue(self.indigoDevice.deviceTypeId, GUI_CONFIG_COMMANDREADTIMEOUT, u'0.5'))
			
			telnetConnectionRequiresLoginDP = self.hostPlugin.getGUIConfigValue(self.indigoDevice.deviceTypeId, GUI_CONFIG_REQUIRES_LOGIN_DP, u'')
			telnetConnectionRequiresLogin = (RPFrameworkUtils.to_unicode(self.indigoDevice.pluginProps.get(telnetConnectionRequiresLoginDP, u'False')).lower() == u'true')
			
			updateStatusPollerPropertyName = self.hostPlugin.getGUIConfigValue(self.indigoDevice.deviceTypeId, GUI_CONFIG_STATUSPOLL_INTERVALPROPERTY, u'updateInterval')
			updateStatusPollerInterval = int(self.indigoDevice.pluginProps.get(updateStatusPollerPropertyName, u'90'))
			updateStatusPollerNextRun = None
			updateStatusPollerActionId = self.hostPlugin.getGUIConfigValue(self.indigoDevice.deviceTypeId, GUI_CONFIG_STATUSPOLL_ACTIONID, u'')
			
			emptyQueueReducedWaitCycles = int(self.hostPlugin.getGUIConfigValue(self.indigoDevice.deviceTypeId, GUI_CONFIG_TELNETDEV_EMPTYQUEUE_SPEEDUPCYCLES, u'200'))
			
			# begin the infinite loop which will run as long as the queue contains commands
			# and we have not received an explicit shutdown request
			continueProcessingCommands = True
			lastQueuedCommandCompleted = 0
			while continueProcessingCommands == True:
				# process pending commands now...
				while not commandQueue.empty():
					lenQueue = commandQueue.qsize()
					self.hostPlugin.logger.threaddebug(u'Command queue has ' + RPFrameworkUtils.to_unicode(lenQueue) + u' command(s) waiting')
					
					# the command name will identify what action should be taken... we will handle the known
					# commands and dispatch out to the device implementation, if necessary, to handle unknown
					# commands
					command = commandQueue.get()
					if command.commandName == RPFrameworkCommand.CMD_INITIALIZE_CONNECTION:
						# specialized command to instanciate the thread/telnet connection
						# safely ignore this... just used to spin up the thread
						self.hostPlugin.logger.threaddebug(u'Create connection command de-queued')
						
						# if the device supports polling for status, it may be initiated here now that
						# the connection has been established; no additional command will come through
						if telnetConnectionRequiresLogin == False:
							commandQueue.put(RPFrameworkCommand.RPFrameworkCommand(RPFrameworkCommand.CMD_UPDATE_DEVICE_STATUS_FULL, parentAction=updateStatusPollerActionId))
						
					elif command.commandName == RPFrameworkCommand.CMD_TERMINATE_PROCESSING_THREAD:
						# a specialized command designed to stop the processing thread indigo
						# the event of a shutdown
						continueProcessingCommands = False
						
					elif command.commandName == RPFrameworkCommand.CMD_PAUSE_PROCESSING:
						# the amount of time to sleep should be a float found in the
						# payload of the command
						try:
							pauseTime = float(command.commandPayload)
							self.hostPlugin.logger.threaddebug(u'Initiating sleep of ' + RPFrameworkUtils.to_unicode(pauseTime) + u' seconds from command.')
							time.sleep(pauseTime)
						except:
							self.hostPlugin.logger.error(u'Invalid pause time requested')
							
					elif command.commandName == RPFrameworkCommand.CMD_UPDATE_DEVICE_STATUS_FULL:
						# this command instructs the plugin to update the full status of the device (all statuses
						# that may be read from the device should be read)
						if updateStatusPollerActionId != u'':
							self.hostPlugin.logger.debug(u'Executing full status update request...')
							self.hostPlugin.executeAction(None, indigoActionId=updateStatusPollerActionId, indigoDeviceId=self.indigoDevice.id, paramValues=None)
							if updateStatusPollerInterval > 0:
								updateStatusPollerNextRun = time.time() + updateStatusPollerInterval
						else:
							self.hostPlugin.logger.threaddebug(u'Ignoring status update request, no action specified to update device status')
					
					elif command.commandName == RPFrameworkCommand.CMD_UPDATE_DEVICE_STATE:
						# this command is to update a device state with the payload (which may be an
						# eval command)
						newStateInfo = re.match('^\{ds\:([a-zA-Z\d]+)\}\{(.+)\}$', command.commandPayload, re.I)
						if newStateInfo is None:
							self.hostPlugin.logger.error(u'Invalid new device state specified')
						else:
							# the new device state may include an eval statement...
							updateStateName = newStateInfo.group(1)
							updateStateValue = newStateInfo.group(2)
							if updateStateValue.startswith(u'eval'):
								updateStateValue = eval(updateStateValue.replace(u'eval:', u''))
							
							self.hostPlugin.logger.debug(u'Updating state "' + RPFrameworkUtils.to_unicode(updateStateName) + u'" to: ' + RPFrameworkUtils.to_unicode(updateStateValue))
							self.indigoDevice.updateStateOnServer(key=updateStateName, value=updateStateValue)
					
					elif command.commandName == CMD_WRITE_TO_DEVICE:
						# this command initiates a write of data to the device
						self.hostPlugin.logger.debug(u'Sending command: ' + command.commandPayload)
						writeCommand = command.commandPayload + lineEndingToken
						ipConnection.write(writeCommand.encode(lineEncoding))
						self.hostPlugin.logger.threaddebug(u'Write command completed.')
					
					else:
						# this is an unknown command; dispatch it to another routine which is
						# able to handle the commands (to be overridden for individual devices)
						self.handleUnmanagedCommandInQueue(ipConnection, command)
						
					# determine if any response has been received from the telnet device...
					responseText = RPFrameworkUtils.to_unicode(self.readLine(ipConnection, lineEndingToken, commandResponseTimeout))
					if responseText != u'':
						self.hostPlugin.logger.threaddebug("Received: " + responseText)
						self.handleDeviceResponse(responseText.replace(lineEndingToken, u''), command)
						
					# if the command has a pause defined for after it is completed then we
					# should execute that pause now
					if command.postCommandPause > 0.0 and continueProcessingCommands == True:
						self.hostPlugin.logger.threaddebug(u'Post Command Pause: ' + RPFrameworkUtils.to_unicode(command.postCommandPause))
						time.sleep(command.postCommandPause)
					
					# complete the dequeuing of the command, allowing the next
					# command in queue to rise to the top
					commandQueue.task_done()
					lastQueuedCommandCompleted = emptyQueueReducedWaitCycles
					
				# continue with empty-queue processing unless the connection is shutting down...
				if continueProcessingCommands == True:
					# check for any pending data coming IN from the telnet connection; note this is after the
					# command queue has been emptied so it may be un-prompted incoming data
					responseText = RPFrameworkUtils.to_unicode(self.readIfAvailable(ipConnection, lineEndingToken, commandResponseTimeout))
					if responseText != u'':
						self.hostPlugin.logger.threaddebug(u'Received w/o Command: ' + responseText)
						self.handleDeviceResponse(responseText.replace(lineEndingToken, u''), None)
				
					# when the queue is empty, pause a bit on each iteration
					if lastQueuedCommandCompleted > 0:
						time.sleep(self.emptyQueueProcessingThreadSleepTime/2)
						lastQueuedCommandCompleted = lastQueuedCommandCompleted - 1
					else:
						time.sleep(self.emptyQueueProcessingThreadSleepTime)
				
					# check to see if we need to issue an update...
					if updateStatusPollerNextRun is not None and time.time() > updateStatusPollerNextRun:
						commandQueue.put(RPFrameworkCommand.RPFrameworkCommand(RPFrameworkCommand.CMD_UPDATE_DEVICE_STATUS_FULL, parentAction=updateStatusPollerActionId))
				
		# handle any exceptions that are thrown during execution of the plugin... note that this
		# should terminate the thread, but it may get spun back up again
		except SystemExit:
			# the system is shutting down communications... we can kill access now by allowing
			# the thread to expire
			pass
		except (socket.timeout, EOFError):
			# this is a standard timeout/disconnect
			if self.failedConnectionAttempts == 0 or self.hostPlugin.debug == True:
				self.hostPlugin.logger.error(u'Connection timed out for device ' + RPFrameworkUtils.to_unicode(self.indigoDevice.id))
				
			if connectionStateKey != u'':
				self.indigoDevice.updateStateOnServer(key=connectionStateKey, value=u'Unavailable')
				connectionStateKey = u''  # prevents the finally from re-updating to disconnected
				
			# this really is an error from the user's perspective, so set that state now
			self.indigoDevice.setErrorStateOnServer(u'Connection Error')
				
			# check to see if we should attempt a reconnect
			self.scheduleReconnectionAttempt()
		except socket.error, e:
			# this is a standard socket error, such as a reset... we can attempt to recover from this with
			# a scheduled reconnect
			if self.failedConnectionAttempts == 0 or self.hostPlugin.debug == True:
				self.hostPlugin.logg.error(u'Connection failed for device ' + RPFrameworkUtils.to_unicode(self.indigoDevice.id) + u': ' + RPFrameworkUtils.to_unicode(e))

			if connectionStateKey != u'':
				self.indigoDevice.updateStateOnServer(key=connectionStateKey, value=u'Unavailable')
				connectionStateKey = u''  # prevents the finally from re-updating to disconnected
				
			# this really is an error from the user's perspective, so set that state now
			self.indigoDevice.setErrorStateOnServer(u'Connection Error')
				
			# check to see if we should attempt a reconnect
			self.scheduleReconnectionAttempt()
		except:
			self.indigoDevice.setErrorStateOnServer(u'Error')
			self.hostPlugin.logger.exception(u'Error during background processing')
		finally:			
			# update the device's connection state to no longer connected...
			self.hostPlugin.logger.debug(u'Closing connection to device')
			if isConnectedStateKey != u'':
				self.indigoDevice.updateStateOnServer(key=isConnectedStateKey, value=u'false', clearErrorState=False)
			if connectionStateKey != u'':
				self.indigoDevice.updateStateOnServer(key=connectionStateKey, value=u'Disconnected', clearErrorState=False)
			
			# execute the close of the connection now
			if not ipConnection is None:
				ipConnection.close()
				ipConnection = None

	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine should return a touple of information about the connection - in the
	# format of (ipAddress/HostName, portNumber)
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def getDeviceAddressInfo(self):
		if self.connectionType == CONNECTIONTYPE_TELNET:
			return (u'', 0)
		else:
			portName = RPFrameworkUtils.to_unicode(self.hostPlugin.substituteIndigoValues(self.hostPlugin.getGUIConfigValue(self.indigoDevice.deviceTypeId, GUI_CONFIG_SERIALPORT_PORTNAME, ""), self, None))
			baudRate = int(self.hostPlugin.substituteIndigoValues(self.hostPlugin.getGUIConfigValue(self.indigoDevice.deviceTypeId, GUI_CONFIG_SERIALPORT_BAUDRATE, "115200"), self, None))
			parity = eval("serial." + self.hostPlugin.substituteIndigoValues(self.hostPlugin.getGUIConfigValue(self.indigoDevice.deviceTypeId, GUI_CONFIG_SERIALPORT_PARITY, "PARITY_NONE"), self, None))
			byteSize = eval("serial." + self.hostPlugin.substituteIndigoValues(self.hostPlugin.getGUIConfigValue(self.indigoDevice.deviceTypeId, GUI_CONFIG_SERIALPORT_BYTESIZE, "EIGHTBITS"), self, None))
			stopBits = eval("serial." + self.hostPlugin.substituteIndigoValues(self.hostPlugin.getGUIConfigValue(self.indigoDevice.deviceTypeId, GUI_CONFIG_SERIALPORT_STOPBITS, "STOPBITS_ONE"), self, None))
			timeout = float(self.hostPlugin.substituteIndigoValues(self.hostPlugin.getGUIConfigValue(self.indigoDevice.deviceTypeId, GUI_CONFIG_SERIALPORT_READTIMEOUT, "1.0"), self, None))
			writeTimeout = float(self.hostPlugin.substituteIndigoValues(self.hostPlugin.getGUIConfigValue(self.indigoDevice.deviceTypeId, GUI_CONFIG_SERIALPORT_WRITETIMEOUT, "1.0"), self, None))
			return (portName, (baudRate, parity, byteSize, stopBits, timeout, writeTimeout))
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine should return a touple of information about the connection - in the
	# format of (ipAddress/HostName, portNumber)
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def establishDeviceConnection(self, connectionInfo):
		if self.connectionType == CONNECTIONTYPE_TELNET:
			return telnetlib.Telnet(connectionInfo[0], connectionInfo[1])
		elif self.connectionType == CONNECTIONTYPE_SERIAL:
			return self.hostPlugin.openSerial(self.indigoDevice.name, connectionInfo[0], baudrate=connectionInfo[1][0], parity=connectionInfo[1][1], bytesize=connectionInfo[1][2], stopbits=connectionInfo[1][3], timeout=connectionInfo[1][4], writeTimeout=connectionInfo[1][5])
		elif self.connectionType == CONNECTIONTYPE_SOCKET:
			commandSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			commandSocket.settimeout(int(self.hostPlugin.getGUIConfigValue(self.indigoDevice.deviceTypeId, GUI_CONFIG_SOCKET_CONNECTIONTIMEOUT, "5")))
			commandSocket.connect((connectionInfo[0], connectionInfo[1]))
			commandSocket.setblocking(0)
			return commandSocket
		else:
			raise u'Invalid connection type specified'
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine should be overridden in individual device classes whenever they must
	# handle custom commands that are not already defined
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def handleUnmanagedCommandInQueue(self, ipConnection, rpCommand):
		pass
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine should attempt to read a line of text from the connection, using the
	# provided timeout as the upper-limit to wait
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def readLine(self, connection, lineEndingToken, commandResponseTimeout):
		if self.connectionType == CONNECTIONTYPE_TELNET:
			return RPFrameworkUtils.to_unicode(connection.read_until(lineEndingToken, commandResponseTimeout))
		elif self.connectionType == CONNECTIONTYPE_SERIAL:
			# Python 2.6 changed the readline signature to not include a line-ending token,
			# so we have to "manually" re-create that here
			#return connection.readline(None)
			lineRead = u''
			lineEndingTokenLen = len(lineEndingToken)
			while True:
				c = connection.read(1)
				if c:
					lineRead += c
					if lineRead[-lineEndingTokenLen:] == lineEndingToken:
						break
				else:
					break
			return RPFrameworkUtils.to_unicode(lineRead)
			
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine should attempt to read a line of text from the connection only if there
	# is an indication of waiting data (there is no waiting until a specified timeout)
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def readIfAvailable(self, connection, lineEndingToken, commandResponseTimeout):
		if self.connectionType == CONNECTIONTYPE_TELNET:
			return RPFrameworkUtils.to_unicode(connection.read_eager())
		elif connection.inWaiting() > 0:
			return RPFrameworkUtils.to_unicode(self.readLine(connection, lineEndingToken, commandResponseTimeout))
		else:
			return u''
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will process any response from the device following the list of
	# response objects defined for this device type. For telnet this will always be
	# a text string
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def handleDeviceResponse(self, responseText, rpCommand):
		# loop through the list of response definitions defined in the (base) class
		# and determine if any match
		for rpResponse in self.hostPlugin.getDeviceResponseDefinitions(self.indigoDevice.deviceTypeId):
			if rpResponse.isResponseMatch(responseText, rpCommand, self, self.hostPlugin):
				self.hostPlugin.logger.threaddebug(u'Found response match: ' + rpResponse.responseId)
				rpResponse.executeEffects(responseText, rpCommand, self, self.hostPlugin)
				
		
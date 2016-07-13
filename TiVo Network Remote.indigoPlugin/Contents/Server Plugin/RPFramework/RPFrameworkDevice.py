#! /usr/bin/env python
# -*- coding: utf-8 -*-
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
# RPFrameworkDevice by RogueProeliator <adam.d.ashe@gmail.com>
# 	Base class for all RogueProeliator's devices created by plugins for Perceptive
#	Automation's Indigo software.
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
#		Added support for child devices
#	Version 8:
#		Added support for reconnection attempts via plugin's command queue
#	Version 13:
#		Added ability to specify new device states that are added via upgrades; if any
#		of these states don't exist at device started, the device states will be reloaded
#		via a call to stateListOrDisplayStateIdChanged
#	Version 17:
#		Added unicode support
#		Changed error messages to the new plugin-based logErrorMessage
#
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////

#/////////////////////////////////////////////////////////////////////////////////////////
# Python imports
#/////////////////////////////////////////////////////////////////////////////////////////
import functools
import indigo
import Queue
import random
import threading
import time

import RPFrameworkCommand
import RPFrameworkPlugin
import RPFrameworkThread
import RPFrameworkUtils


#/////////////////////////////////////////////////////////////////////////////////////////
# Constants and configuration variables
#/////////////////////////////////////////////////////////////////////////////////////////


#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
# RPFrameworkDevice
#	Base class for Indigo plugin devices that provides standard functionality such as
#	multi-threaded communications and attribute management
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
class RPFrameworkDevice(object):
	
	#/////////////////////////////////////////////////////////////////////////////////////
	# Class construction and destruction methods
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# Constructor called once upon plugin class receiving a command to start device
	# communication. The plugin will call other commands when needed, simply zero out the
	# member variables
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def __init__(self, plugin, device):
		self.hostPlugin = plugin
		self.indigoDevice = device
		self.childDevices = dict()
		self.deviceInstanceIdentifier = random.getrandbits(16)

		self.dbConn = None
		self.commandQueue = Queue.Queue()
		self.concurrentThread = None
		
		self.failedConnectionAttempts = 0
		self.emptyQueueProcessingThreadSleepTime = 0.1
		
		self.upgradedDeviceStates = list()
		self.upgradedDeviceProperties = list()
		
	
	#/////////////////////////////////////////////////////////////////////////////////////
	# Validation and GUI functions
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called to retrieve a dynamic list of elements for an action (or
	# other ConfigUI based) routine
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def getConfigDialogMenuItems(self, filter, valuesDict, typeId, targetId):
		return []
		
		
	#/////////////////////////////////////////////////////////////////////////////////////
	# Public communication-interface methods methods
	#/////////////////////////////////////////////////////////////////////////////////////	
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This call will be made from the plugin in order to start the communications with the
	# hardware device... this will spin up the concurrent processing thread.
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def initiateCommunications(self, initializeConnect=True):
		# determine if this device is missing any properties that were added
		# during device/plugin upgrades
		propertiesDictUpdateRequired = False
		pluginPropsCopy = self.indigoDevice.pluginProps
		for newPropertyDefn in self.upgradedDeviceProperties:
			if not (newPropertyDefn[0] in pluginPropsCopy):
				self.hostPlugin.logDebugMessage(u'Triggering property update due to missing device property: ' + RPFrameworkUtils.to_unicode(newPropertyDefn[0]), RPFrameworkPlugin.DEBUGLEVEL_LOW)
				pluginPropsCopy[newPropertyDefn[0]] = newPropertyDefn[1]
				propertiesDictUpdateRequired = True
		if propertiesDictUpdateRequired == True:
			self.indigoDevice.replacePluginPropsOnServer(pluginPropsCopy)
	
		# determine if this device is missing any states that were defined in upgrades
		stateReloadRequired = False
		for newStateName in self.upgradedDeviceStates:
			if not (newStateName in self.indigoDevice.states):
				self.hostPlugin.logDebugMessage(u'Triggering state reload due to missing device state: ' + RPFrameworkUtils.to_unicode(newStateName), RPFrameworkPlugin.DEBUGLEVEL_LOW)
				stateReloadRequired = True	
		if stateReloadRequired == True:
			self.indigoDevice.stateListOrDisplayStateIdChanged();
		
		# start concurrent processing thread by injecting a placeholder
		# command to the queue
		if initializeConnect == True:
			self.queueDeviceCommand(RPFrameworkCommand.RPFrameworkCommand(RPFrameworkCommand.CMD_INITIALIZE_CONNECTION))

	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will shut down communications with the hardware device
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def terminateCommunications(self):
		self.hostPlugin.logDebugMessage(u'Initiating shutdown of communications with ' + RPFrameworkUtils.to_unicode(self.indigoDevice.name), RPFrameworkPlugin.DEBUGLEVEL_LOW)
		if not (self.concurrentThread is None) and self.concurrentThread.isAlive() == True:
			self.concurrentThread.terminate()
			self.concurrentThread.join()
		self.concurrentThread = None
		self.hostPlugin.logDebugMessage(u'Shutdown of communications with ' + RPFrameworkUtils.to_unicode(self.indigoDevice.name) + u' complete', RPFrameworkPlugin.DEBUGLEVEL_LOW)
		
		
	#/////////////////////////////////////////////////////////////////////////////////////
	# Queue and command processing methods
	#/////////////////////////////////////////////////////////////////////////////////////	
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# Add new command to queue, which is polled and emptied by 
	# concurrentCommandProcessingThread funtion
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def queueDeviceCommand(self, command):
		self.commandQueue.put(command)
		
		# if connection to the device has not started, or has timed out, then start up a
		# concurrent thread to handle communications
		if self.concurrentThread is None or self.concurrentThread.isAlive() == False:
			self.concurrentThread = RPFrameworkThread.RPFrameworkThread(target=functools.partial(self.concurrentCommandProcessingThread, self.commandQueue))
			self.concurrentThread.start()
			
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# Add new commands to queue as a list, ensuring that they are executed in-order
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def queueDeviceCommands(self, commandList):
		for rpCmd in commandList:
			self.queueDeviceCommand(rpCmd)
			
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is designed to run in a concurrent thread and will continuously monitor
	# the commands queue for work to do.
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def concurrentCommandProcessingThread(self, commandQueue):
		pass
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will process a device's reconnection attempt... note that by default
	# a device will NOT attempt to re-initialize communications; it must be enabled via
	# the GUI Configuration
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def scheduleReconnectionAttempt(self):
		self.hostPlugin.logDebugMessage(u'Scheduling reconnection attempt...', RPFrameworkPlugin.DEBUGLEVEL_MED)
		try:
			self.failedConnectionAttempts = self.failedConnectionAttempts + 1
			maxReconnectAttempts = int(self.hostPlugin.getGUIConfigValue(self.indigoDevice.deviceTypeId, RPFrameworkPlugin.GUI_CONFIG_RECONNECTIONATTEMPT_LIMIT, u'0'))
			if self.failedConnectionAttempts > maxReconnectAttempts:
				self.hostPlugin.logDebugMessage(u'Maximum reconnection attempts reached (or not allowed) for device ' + RPFrameworkUtils.to_unicode(self.indigoDevice.id), RPFrameworkPlugin.DEBUGLEVEL_LOW)
			else:
				reconnectAttemptDelay = int(self.hostPlugin.getGUIConfigValue(self.indigoDevice.deviceTypeId, RPFrameworkPlugin.GUI_CONFIG_RECONNECTIONATTEMPT_DELAY, u'60'))
				reconnectAttemptScheme = self.hostPlugin.getGUIConfigValue(self.indigoDevice.deviceTypeId, RPFrameworkPlugin.GUI_CONFIG_RECONNECTIONATTEMPT_SCHEME, RPFrameworkPlugin.GUI_CONFIG_RECONNECTIONATTEMPT_SCHEME_REGRESS)
			
				if reconnectAttemptScheme == RPFrameworkPlugin.GUI_CONFIG_RECONNECTIONATTEMPT_SCHEME_FIXED:
					reconnectSeconds = reconnectAttemptDelay
				else:
					reconnectSeconds = reconnectAttemptDelay * self.failedConnectionAttempts
				reconnectAttemptTime = time.time() + reconnectSeconds

				self.hostPlugin.pluginCommandQueue.put(RPFrameworkCommand.RPFrameworkCommand(RPFrameworkCommand.CMD_DEVICE_RECONNECT, commandPayload=(self.indigoDevice.id, self.deviceInstanceIdentifier, reconnectAttemptTime)))
				self.hostPlugin.logDebugMessage(u'Reconnection attempt scheduled for ' + RPFrameworkUtils.to_unicode(reconnectSeconds) + u' seconds', RPFrameworkPlugin.DEBUGLEVEL_MED)
		except e:
			self.hostPlugin.logErrorMessage(u'Failed to schedule reconnection attempt to device')			
		
		
	#/////////////////////////////////////////////////////////////////////////////////////
	# Device hierarchy (parent/child relationship) routines
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will generate the key to use in the managed child devices dictionary
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def getChildDeviceKeyByDevice(self, device):
		# the key into the dictionary will be specified by the GUI configuration variable
		# of THIS (parent) device... by default it will just be the child device's ID
		childDeviceKey = self.hostPlugin.substituteIndigoValues(self.hostPlugin.getGUIConfigValue(self.indigoDevice.deviceTypeId, RPFrameworkPlugin.GUI_CONFIG_CHILDDICTIONARYKEYFORMAT, u''), device, None)
		if childDeviceKey == u'':
			childDeviceKey = RPFrameworkUtils.to_unicode(device.indigoDevice.id)
		return childDeviceKey
	
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will add a new child device to the device; the parameter will be of
	# RPFrameworkDevice descendant
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def addChildDevice(self, device):
		self.hostPlugin.logDebugMessage(u'Adding child device ' + RPFrameworkUtils.to_unicode(device.indigoDevice.id) + u' to ' + RPFrameworkUtils.to_unicode(self.indigoDevice.id), RPFrameworkPlugin.DEBUGLEVEL_MED)
		
		# the key into the dictionary will be specified by the GUI configuration variable
		childDeviceKey = self.getChildDeviceKeyByDevice(device)
		self.hostPlugin.logDebugMessage(u'Created device key: ' + childDeviceKey, RPFrameworkPlugin.DEBUGLEVEL_HIGH)
			
		# add the device to the list of those managed by this device...
		self.childDevices[childDeviceKey] = device
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will remove a child device from the list of managed devices; note that
	# the plugin continues to handle all device lifecycle calls!
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def removeChildDevice(self, device):
		self.hostPlugin.logDebugMessage(u'Removing child device ' + RPFrameworkUtils.to_unicode(device.indigoDevice.id) + u' from ' + RPFrameworkUtils.to_unicode(self.indigoDevice.id), RPFrameworkPlugin.DEBUGLEVEL_MED)
		
		# the key into the dictionary will be specified by the GUI configuration variable
		childDeviceKey = self.getChildDeviceKeyByDevice(device)
		
		# remove the device...
		del self.childDevices[childDeviceKey]
		
		
	#/////////////////////////////////////////////////////////////////////////////////////
	# Utility routines
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will reload the Indigo device from the database; useful if we need to
	# get updated states or information 
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def reloadIndigoDevice(self):
		self.indigoDevice = indigo.devices[self.indigoDevice.id]
	
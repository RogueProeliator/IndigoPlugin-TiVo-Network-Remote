#! /usr/bin/env python
# -*- coding: utf-8 -*-
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
# RPFrameworkPlugin by RogueProeliator <adam.d.ashe@gmail.com>
# 	Base class for all RogueProeliator's plugins for Perceptive Automation's Indigo
#	home automation software.
#	
#	THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# 	IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# 	FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# 	AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# 	LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# 	OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# 	SOFTWARE.
#
#	Version 0 [10-18-2013]:
#		Initial release of the plugin framework
#	Version 1
#		Fixed default value of debug in case missing in upgraded devices (default Medium)
#	Version 2
#		Added SOAP operations to the RESTfulDevice className
#		Better set default value for the debug level (in plugin.py)
#	Version 3 [11-18-2013]:
#		Added Wake-On-LAN module for network devices
#		Added functions to aid in finding/selection uPNP devices
#		Added plugin config update when device dialog closes
#	Version 4:
#		Added support for child devices
#		Added support for execute conditions on action commands
#	Version 5:
#		Swapped deviceStartComm order to assign managed device to array prior to
#			initiating communications
#	Version 7:
#		Changed substitute to support plugin preferences with a "pp" prefix
#		Added database support
#		Added plugin-level guiConfiguration settings, used with GUI_CONFIG_PLUGINSETTINGS
#	Version 8 [5/2014]:
#		Added Plugin Config UI parameter validation
#		Added plugin-level command queue processing; moved update check to here
#	Version 9:
#		Added ability to handle unknown commands for the plugin "downstream"
#	Version 10:
#		Added parameter to plugin commands that allow re-queuing additional commands for
#		non-immediate execution
#	Version 11:
#		Added callback functions to support dimmer-based devices (passes action call to the
#		device like a normal action callback
#	Version 12:
#		Added support for shorter wait times in devices after a queued command executes
#		Added support for uiValue when updating states from effect processing
#	Version 13:
#		Added support for substituting Indigo List type property values (into string as action
#		comma-delimited string)
#	Version 14:
#		Switched init routine to complete RPFramework init prior to base class init
#		Added template-replace of MenuItems.xml for standard features
#		Added option to install UPnP debug tools to menu items
#		Added ability for UPnP selects to have multi-part values and targets
#		Added writePluginReport for writing out standard reports
#		Added trigger processing to the base plugin
#		Removed initial version check on startup - let the concurrent thread do that!
#	Version 15:
#		Added the parameter type ParamTypeOSFilePath to validate an existing filename
#	Version 16:
#		Fixed error when an action failed to validate (when executed through script)
#		Updated telnet devices to set the error state on the server when timing out / failed connection
#	Version 17:
#		Added unicode support
#		Added support for device parent properties during substitution
#		Added "requests" module to framework from source on GitHub
#		Added ability to dump device details to event log as part of the DEBUG menu items
#		Added logErrorMessage function to log friendly error messages and details for debug
#		Changed error messages to use the new logErrorMessage function
#	Version 18:
#		Added ability to specify updateExecCondition on effects within response nodes
#	Version 19:
#		Changed call to determine RPFrameworkConfig.xml file to use the os.getcwd() call
#	Version 20:
#		Changed updater to use the GitHub updater method
#		Updated init routine to lower logging level of requests library
#	Version 21 [September 2016]
#		Changed to new Python based logging for Indigo 7
#		Changed flag for including UPnP on the menu to be passed in to constructor
#	Version 22 [October 2016]
#		Removed XML file customization which was not working post-Beta 7
#	Version 23 [October 2018]
#		Added new version check against Plugin store
#	Version 24 [February 2019]
#		Modified version check to only execute against API 2.0 and below
#
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////

#/////////////////////////////////////////////////////////////////////////////////////////
# Python imports
#/////////////////////////////////////////////////////////////////////////////////////////
import indigo
import os
import re
import requests
import RPFrameworkCommand
from RPFrameworkIndigoAction import RPFrameworkIndigoActionDfn
import RPFrameworkDeviceResponse 
import RPFrameworkIndigoParam
import RPFrameworkNetworkingUPnP
from dataAccess import indigosql
import Queue
import shutil
import socket
from subprocess import call
import time
from urllib2 import urlopen
import xml.etree.ElementTree
import threading
import RPFrameworkUtils
import ConfigParser
import logging
from distutils.version import LooseVersion

#/////////////////////////////////////////////////////////////////////////////////////////
# Constants and configuration variables
#/////////////////////////////////////////////////////////////////////////////////////////
GUI_CONFIG_PLUGINSETTINGS = u'plugin'
GUI_CONFIG_PLUGIN_COMMANDQUEUEIDLESLEEP = u'pluginCommandQueueIdleSleep'
GUI_CONFIG_PLUGIN_DEBUG_SHOWUPNPOPTION = u'showUPnPDebug'
GUI_CONFIG_PLUGIN_DEBUG_UPNPOPTION_SERVICEFILTER = u'UPnPDebugServiceFilter'
GUI_CONFIG_PLUGIN_UPDATEDOWNLOADURL = u'pluginUpdateURL'

GUI_CONFIG_ADDRESSKEY = u'deviceAddressFormat'

GUI_CONFIG_UPNP_SERVICE = u'deviceUPNPServiceId'
GUI_CONFIG_UPNP_CACHETIMESEC = u'deviceUPNPSeachCacheTime'
GUI_CONFIG_UPNP_ENUMDEVICESFIELDID = u'deviceUPNPDeviceFieldId'
GUI_CONFIG_UPNP_DEVICESELECTTARGETFIELDID = u'deviceUPNPDeviceSelectedFieldId'

GUI_CONFIG_ISCHILDDEVICEID = u'deviceIsChildDevice'
GUI_CONFIG_PARENTDEVICEIDPROPERTYNAME = u'deviceParentIdProperty'
GUI_CONFIG_CHILDDICTIONARYKEYFORMAT = u'childDeviceDictionaryKeyFormat'

GUI_CONFIG_RECONNECTIONATTEMPT_LIMIT = u'reconnectAttemptLimit'
GUI_CONFIG_RECONNECTIONATTEMPT_DELAY = u'reconnectAttemptDelay'
GUI_CONFIG_RECONNECTIONATTEMPT_SCHEME = u'reconnectAttemptScheme'
GUI_CONFIG_RECONNECTIONATTEMPT_SCHEME_FIXED = u'fixed'
GUI_CONFIG_RECONNECTIONATTEMPT_SCHEME_REGRESS = u'regress'

GUI_CONFIG_DATABASE_CONN_ENABLED = u'databaseConnectionEnabled'
GUI_CONFIG_DATABASE_CONN_TYPE = u'databaseConnectionType'
GUI_CONFIG_DATABASE_CONN_DBNAME = u'databaseConnectionDBName'

DEBUGLEVEL_NONE = 0		# no .debug() logs will be shown in the Indigo log
DEBUGLEVEL_LOW = 1		# show .debug() logs in the Indigo log
DEBUGLEVEL_HIGH = 2		# show .ThreadDebug() log calls in the Indigo log

TRIGGER_UPDATEAVAILABLE_TYPEID = u'pluginUpdateAvailable'

#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
# RPFrameworkPlugin
#	Base class for Indigo plugins that provides standard functionality such as version
#	checking and validation functions
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
class RPFrameworkPlugin(indigo.PluginBase):
	
	#/////////////////////////////////////////////////////////////////////////////////////
	# Class construction and destruction methods
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# Constructor called once upon plugin class creation; setup the basic functionality
	# common to all plugins based on the framework
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs, daysBetweenUpdateChecks=1, managedDeviceClassModule=None, pluginSupportsUPNP=False):
		# flag the plugin as undergoing initialization so that we know the full
		# indigo plugin is not yet available
		self.pluginIsInitializing = True
		self.pluginSupportsUPNPDebug = pluginSupportsUPNP
		
		# call the base class' initialization to begin setup...
		indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
				
		# setup a custom logging format to make it easier to look through (this applies only to the plugin's
		# individual file handler
		loggingFormatString = logging.Formatter('%(asctime)s.%(msecs)03d\t%(levelname)-12s\t%(name)s.%(funcName)-25s %(msg)s', datefmt='%Y-%m-%d %H:%M:%S')
		self.plugin_file_handler.setFormatter(loggingFormatString)
				
		# determine what the user has set for the debug level; this will determine how we set
		# the python logging to show in the event log
		try:
			self.debugLevel = int(pluginPrefs.get(u'debugLevel', DEBUGLEVEL_NONE))
			if self.debugLevel < 0 or self.debugLevel > 2:
				self.debugLevel = DEBUGLEVEL_NONE
		except:
			self.debugLevel = DEBUGLEVEL_NONE
		
		# setup the logging level of the INDIGO logging handler to the selected level
		if self.debugLevel == DEBUGLEVEL_LOW:
			self.indigo_log_handler.setLevel(logging.DEBUG)
		elif self.debugLevel == DEBUGLEVEL_HIGH:
			self.indigo_log_handler.setLevel(logging.THREADDEBUG)
		else:
			self.indigo_log_handler.setLevel(logging.INFO)
			
		# show the debug message since we are in the middle of initializing the plugin base class
		self.logger.threaddebug(u'Initializing RPFrameworkPlugin')
		
		# create the generic device dictionary which will store a reference to each device that
		# is defined in indigo; the ID mapping will map the deviceTypeId to a class name
		self.managedDevices = dict()
		self.managedDeviceClassModule = managedDeviceClassModule
		self.managedDeviceClassMapping = dict()
		self.managedDeviceParams = dict()
		self.managedDeviceGUIConfigs = dict()
		
		# create a list of actions that are known to the base plugin (these will be processed
		# automatically when possible by the base classes alone)
		self.indigoActions = dict()
		self.deviceResponseDefinitions = dict()
		
		# the plugin defines the Events processing so that we can handle the update trigger,
		# if it exists
		self.indigoEvents = dict()
		
		# this list stores a list of enumerated devices for those devices which support
		# enumeration via uPNP
		self.enumeratedDevices = []
		self.lastDeviceEnumeration = time.time() - 9999
		
		# create the command queue that will be used at the device level
		self.pluginCommandQueue = Queue.Queue()
		
		# setup the plugin update checker... it will be disabled if the URL is empty or the
		# Indigo API is 2.1 or above as it will be built in... but it may be configured for
		# and version
		self.updateCheckPollEnabled = True
		if float(indigo.server.apiVersion) > 2.05:
			self.updateCheckPollEnabled = False
		self.secondsBetweenUpdateChecks = 86400
		self.nextUpdateCheck = time.time()
		self.latestReleaseFound = ''
		
		# create plugin-level configuration variables
		self.pluginConfigParams = []
		
		# parse the RPFramework plugin configuration XML provided for this plugin,
		# if it is present
		self.parseRPFrameworkConfig(pluginDisplayName.replace(u' Plugin', u''))
		
		# perform any upgrade steps if the plugin is running for the first time after
		# an upgrade
		oldPluginVersion = pluginPrefs.get(u'loadedPluginVersion', u'')
		if oldPluginVersion != unicode(pluginVersion):
			self.performPluginUpgradeMaintenance(oldPluginVersion, unicode(pluginVersion))
		
		# initialization is complete...
		self.pluginIsInitializing = False
	
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will parse the RPFrameworkConfig.xml file that is present in the
	# plugin's directory, if it is present
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def parseRPFrameworkConfig(self, pluginName):
		indigoBasePath = indigo.server.getInstallFolderPath()
		pluginBasePath = os.getcwd()
		pluginConfigPath = os.path.join(pluginBasePath, "RPFrameworkConfig.xml")
		
		if os.path.exists(pluginConfigPath):
			self.logger.debug(u'Beginning processing of RPFrameworkConfig.xml file')
			try:
				# read in the XML using the XML ElementTree implementation/module
				configDom = xml.etree.ElementTree.parse(pluginConfigPath)
				pluginConfigNode = configDom.getroot().find("pluginConfig")
				
				# read in any plugin-level parameter definitions
				pluginParamNode = pluginConfigNode.find("pluginParams")
				if pluginParamNode != None:
					for pluginParam in pluginParamNode:
						rpPluginParam = self.readIndigoParamNode(pluginParam)
						self.pluginConfigParams.append(rpPluginParam)
						self.logger.threaddebug(u'Found plugin param: ' + rpPluginParam.indigoId)
				
				# read in any plugin-level guiConfigSettings
				pluginGuiConfigNode = pluginConfigNode.find("guiConfiguration")
				if pluginGuiConfigNode != None:
					for guiConfigSetting in pluginGuiConfigNode:
						self.logger.threaddebug(u'Found plugin setting: ' + guiConfigSetting.tag + u'=' + guiConfigSetting.text)
						self.putGUIConfigValue(GUI_CONFIG_PLUGINSETTINGS, guiConfigSetting.tag, guiConfigSetting.text)
				
				# determine if any device mappings are present
				deviceMappings = pluginConfigNode.find("deviceMapping")
				if deviceMappings != None:
					for deviceMapping in deviceMappings.findall("device"):
						indigoId = RPFrameworkUtils.to_unicode(deviceMapping.get('indigoId'))
						className = RPFrameworkUtils.to_unicode(deviceMapping.get('className'))
						self.managedDeviceClassMapping[indigoId] = className
						self.logger.threaddebug(u'Found device mapping; id: ' + indigoId + u' to class: ' + className)
				else:
					self.logger.threaddebug(u'No device mappings found')
					
				# read in any device definition information such as device properties for
				# validation and retrieval
				devicesNode = pluginConfigNode.find("devices")
				if devicesNode != None:
					for deviceDfn in devicesNode.findall("device"):
						indigoDeviceId = RPFrameworkUtils.to_unicode(deviceDfn.get("indigoId"))
						
						# process all of the parameters for this device
						deviceParamsNode = deviceDfn.find("params")
						if deviceParamsNode != None:
							paramsList = list()
							for deviceParam in deviceParamsNode.findall("param"):
								rpDevParam = self.readIndigoParamNode(deviceParam)
								self.logger.threaddebug(u'Created device parameter for managed device "' + indigoDeviceId + u'": ' + rpDevParam.indigoId)
								paramsList.append(rpDevParam)
							self.managedDeviceParams[indigoDeviceId] = paramsList
							
						# process any GUI configurations -- these are settings that affect how the
						# plugin appears to Indigo users
						guiConfigNode = deviceDfn.find("guiConfiguration")
						if guiConfigNode != None:
							for guiConfigSetting in guiConfigNode:
								self.logger.threaddebug(u'Found device setting: ' + guiConfigSetting.tag + u'=' + guiConfigSetting.text)
								self.putGUIConfigValue(indigoDeviceId, guiConfigSetting.tag, guiConfigSetting.text)
								
						# process any device response definitions... these define what the plugin will do
						# when a response is received from the device (definition is agnostic of type of device,
						# though they may be handled differently in code)
						deviceResponsesNode = deviceDfn.find("deviceResponses")
						if deviceResponsesNode != None:
							for devResponse in deviceResponsesNode.findall("response"):
								responseId = RPFrameworkUtils.to_unicode(devResponse.get("id"))
								responseToActionId = RPFrameworkUtils.to_unicode(devResponse.get("respondToActionId"))
								criteriaFormatString = RPFrameworkUtils.to_unicode(devResponse.find("criteriaFormatString").text)
								matchExpression = RPFrameworkUtils.to_unicode(devResponse.find("matchExpression").text)
								self.logger.threaddebug(u'Found device response: ' + responseId)
									
								# create the object so that effects may be added from child nodes
								devResponseDefn = RPFrameworkDeviceResponse.RPFrameworkDeviceResponse(responseId, criteriaFormatString, matchExpression, responseToActionId)
								
								# add in any effects that are defined
								effectsListNode = devResponse.find("effects")
								if effectsListNode != None:
									for effectDefn in effectsListNode.findall("effect"):
										effectType = eval(u'RPFrameworkDeviceResponse.' + RPFrameworkUtils.to_unicode(effectDefn.get("effectType")))
										effectUpdateParam = RPFrameworkUtils.to_unicode(effectDefn.find("updateParam").text)
										effectValueFormat = RPFrameworkUtils.to_unicode(effectDefn.find("updateValueFormat").text)
										
										effectValueFormatExVal = u''
										effectValueFormatExNode = effectDefn.find("updateValueExFormat")
										if effectValueFormatExNode != None:
											effectValueFormatExVal = RPFrameworkUtils.to_unicode(effectValueFormatExNode.text)
										
										effectValueEvalResult = RPFrameworkUtils.to_unicode(effectDefn.get("evalResult")).lower() == "true"
										
										effectExecCondition = u''
										effectExecConditionNode = effectDefn.find("updateExecCondition")
										if effectExecConditionNode != None:
											effectExecCondition = RPFrameworkUtils.to_unicode(effectExecConditionNode.text)
										
										self.logger.threaddebug(u'Found response effect: Type=' + effectType + u'; Param: ' + effectUpdateParam + u'; ValueFormat=' + RPFrameworkUtils.to_unicode(effectValueFormat) + u'; ValueFormatEx=' + effectValueFormatExVal + u'; Eval=' + RPFrameworkUtils.to_unicode(effectValueEvalResult) + u'; Condition=' + effectExecCondition)
										devResponseDefn.addResponseEffect(RPFrameworkDeviceResponse.RPFrameworkDeviceResponseEffect(effectType, effectUpdateParam, effectValueFormat, effectValueFormatExVal, effectValueEvalResult, effectExecCondition))
								
								# add the definition to the plugin's list of response definitions
								self.addDeviceResponseDefinition(indigoDeviceId, devResponseDefn)
						
				# attempt to read any actions that will be automatically processed by
				# the framework
				managedActions = pluginConfigNode.find("actions")
				if managedActions != None:
					for managedAction in managedActions.findall("action"):
						indigoActionId = RPFrameworkUtils.to_unicode(managedAction.get('indigoId'))
						rpAction = RPFrameworkIndigoActionDfn(indigoActionId)
						self.logger.threaddebug(u'Found managed action: ' + indigoActionId)
						
						# process/add in the commands for this action
						commandListNode = managedAction.find("commands")
						if commandListNode != None:
							for commandDefn in commandListNode.findall("command"):
								commandNameNode = commandDefn.find("commandName")
								commandFormatStringNode = commandDefn.find("commandFormat")
								
								commandExecuteCondition = u''
								commandExecuteConditionNode = commandDefn.find("commandExecCondition")
								if commandExecuteConditionNode != None:
									commandExecuteCondition = RPFrameworkUtils.to_unicode(commandExecuteConditionNode.text)
								
								commandRepeatCount = u''
								commandRepeatCountNode = commandDefn.find("commandRepeatCount")
								if commandRepeatCountNode != None:
									commandRepeatCount = RPFrameworkUtils.to_unicode(commandRepeatCountNode.text)
									
								commandRepeatDelay = u''
								commandRepeatDelayNode = commandDefn.find("commandRepeatDelay")
								if commandRepeatDelayNode != None:
									commandRepeatDelay = RPFrameworkUtils.to_unicode(commandRepeatDelayNode.text)
								
								rpAction.addIndigoCommand(RPFrameworkUtils.to_unicode(commandNameNode.text), RPFrameworkUtils.to_unicode(commandFormatStringNode.text), commandRepeatCount, commandRepeatDelay, commandExecuteCondition)
							
						paramsNode = managedAction.find("params")
						if paramsNode != None:
							self.logger.threaddebug(u'Processing ' + RPFrameworkUtils.to_unicode(len(paramsNode)) + u' params for action')
							for actionParam in paramsNode.findall("param"):
								rpParam = self.readIndigoParamNode(actionParam)
								self.logger.threaddebug(u'Created parameter for managed action "' + rpAction.indigoActionId + u'": ' + rpParam.indigoId)
								rpAction.addIndigoParameter(rpParam)
						self.addIndigoAction(rpAction)
				self.logger.debug(u'Successfully completed processing of RPFrameworkConfig.xml file')
			except:
				self.logger.critical(u'Plugin Config: Error reading RPFrameworkConfig.xml file at: ' + pluginConfigPath)
		else:
			self.logger.warning(u'RPFrameworkConfig.xml not found at ' + pluginConfigPath + u', skipping processing')
			
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will read in a parameter definition from the given XML node, returning
	# a RPFrameworkIndigoParam object fully filled in from the node
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def readIndigoParamNode(self, paramNode):
		paramIndigoId = RPFrameworkUtils.to_unicode(paramNode.get("indigoId"))
		paramType = eval(u'RPFrameworkIndigoParam.' + RPFrameworkUtils.to_unicode(paramNode.get('paramType')))
		paramIsRequired = (paramNode.get("isRequired").lower() == "true")
		rpParam = RPFrameworkIndigoParam.RPFrameworkIndigoParamDefn(paramIndigoId, paramType, isRequired=paramIsRequired)
		
		minValueNode = paramNode.find("minValue")
		if minValueNode != None:
			minValueString = minValueNode.text
			if rpParam.paramType == RPFrameworkIndigoParam.ParamTypeFloat:
				rpParam.minValue = float(minValueString)
			else:
				rpParam.minValue = int(minValueString)
		
		maxValueNode = paramNode.find("maxValue")
		if maxValueNode != None:
			maxValueString = maxValueNode.text
			if rpParam.paramType == RPFrameworkIndigoParam.ParamTypeFloat:
				rpParam.maxValue = float(maxValueString)
			else:
				rpParam.maxValue = int(maxValueString)
				
		validationExpressionNode = paramNode.find("validationExpression")
		if validationExpressionNode != None:
			rpParam.validationExpression = RPFrameworkUtils.to_unicode(validationExpressionNode.text)
				
		defaultValueNode = paramNode.find("defaultValue")
		if defaultValueNode != None:
			if rpParam.paramType == RPFrameworkIndigoParam.ParamTypeFloat:
				rpParam.defaultValue = float(defaultValueNode.text)
			elif rpParam.paramType == RPFrameworkIndigoParam.ParamTypeInteger:
				rpParam.defaultValue = int(defaultValueNode.text)
			elif rpParam.paramType == RPFrameworkIndigoParam.ParamTypeBoolean:
				rpParam.defaultValue = (defaultValueNode.text.lower() == "true")
			else:
				rpParam.defaultValue = defaultValueNode.text
				
		invalidMessageNode = paramNode.find("invalidValueMessage")
		if invalidMessageNode != None:
			rpParam.invalidValueMessage = RPFrameworkUtils.to_unicode(invalidMessageNode.text)
	
		return rpParam
	
	
	
	#/////////////////////////////////////////////////////////////////////////////////////
	# Indigo control methods
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# startup is called by Indigo whenever the plugin is first starting up (by a restart
	# of Indigo server or the plugin or an update
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def startup(self):
		pass
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# shutdown is called by Indigo whenever the entire plugin is being shut down from
	# being disabled, during an update process or if the server is being shut down
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def shutdown(self):
		pass
		
		
		
	#/////////////////////////////////////////////////////////////////////////////////////
	# Indigo device life-cycle call-back routines
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called whenever the plugin should be connecting / communicating with
	# the physical device... here is where we will begin tracking the device as well
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def deviceStartComm(self, dev):
		self.logger.debug(u'Entering deviceStartComm for ' + dev.name + u'; ID=' +  RPFrameworkUtils.to_unicode(dev.id))
		
		# create the plugin device object and add it to the managed list
		newDeviceObject = self.createDeviceObject(dev)
		self.managedDevices[dev.id] = newDeviceObject
		newDeviceObject.initiateCommunications()
		
		# this object may be a child object... if it is then we need to see if its
		# parent has already been created (and if so add it to that parent)
		isChildDeviceType = self.getGUIConfigValue(dev.deviceTypeId, GUI_CONFIG_ISCHILDDEVICEID, u'false').lower() == 'true'
		if isChildDeviceType == True:
			self.logger.threaddebug(u'Device is child object, attempting to find parent')
			parentDeviceId = int(dev.pluginProps[self.getGUIConfigValue(dev.deviceTypeId, GUI_CONFIG_PARENTDEVICEIDPROPERTYNAME, u'')])
			self.logger.threaddebug(u'Found parent ID of device ' + RPFrameworkUtils.to_unicode(dev.id) + u': ' + RPFrameworkUtils.to_unicode(parentDeviceId))
			if parentDeviceId in self.managedDevices:
				self.logger.threaddebug(u'Parent object found, adding this child device now')
				self.managedDevices[parentDeviceId].addChildDevice(newDeviceObject)
				
		# this object could be a parent object whose children have already been created; we need to add those children
		# to this parent object now
		for foundDeviceId in self.managedDevices:
			foundDevice = self.managedDevices[foundDeviceId]
			if self.getGUIConfigValue(foundDevice.indigoDevice.deviceTypeId, GUI_CONFIG_ISCHILDDEVICEID, u'false').lower() == u'true' and int(foundDevice.indigoDevice.pluginProps[self.getGUIConfigValue(foundDevice.indigoDevice.deviceTypeId, GUI_CONFIG_PARENTDEVICEIDPROPERTYNAME, u'')]) == dev.id:
				self.logger.threaddebug(u'Found previously-created child object for parent; child ID: ' + RPFrameworkUtils.to_unicode(foundDevice.indigoDevice.id))
				newDeviceObject.addChildDevice(foundDevice)

		self.logger.debug(u'Exiting deviceStartComm for ' + dev.name)
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine must be implemented in ancestor classes in order to return the device
	# object that is to be created/managed
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def createUnManagedDeviceObject(self, device):
		raise u'createUnManagedDeviceObject not implemented'
	def createDeviceObject(self, device):
		if not (self.managedDeviceClassModule == None) and device.deviceTypeId in self.managedDeviceClassMapping:
			deviceClass = getattr(self.managedDeviceClassModule, self.managedDeviceClassMapping[device.deviceTypeId])
			return deviceClass(self, device)
		else:
			return self.createUnManagedDeviceObject(device)
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called whenever the plugin should cease communicating with the
	# hardware, breaking the connection
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def deviceStopComm(self, dev):
		self.logger.debug(u'Entering deviceStopComm for ' + RPFrameworkUtils.to_unicode(dev.name) + u'; ID=' +  RPFrameworkUtils.to_unicode(dev.id))
		
		# dequeue any pending reconnection attempts...
		
		# first remove the device from the parent if this is a child device...
		isChildDeviceType = self.getGUIConfigValue(dev.deviceTypeId, GUI_CONFIG_ISCHILDDEVICEID, u'false').lower() == u'true'
		if isChildDeviceType == True:
			self.logger.threaddebug(u'Device is child object, attempting to remove from parent...')
			parentDeviceId = int(dev.pluginProps[self.getGUIConfigValue(dev.deviceTypeId, GUI_CONFIG_PARENTDEVICEIDPROPERTYNAME, u'')])
			if parentDeviceId in self.managedDevices:
				self.logger.threaddebug(u'Removing device from parent ID: ' + RPFrameworkUtils.to_unicode(parentDeviceId))
				self.managedDevices[parentDeviceId].removeChildDevice(self.managedDevices[dev.id])
		
		# remove the primary managed object
		self.managedDevices[dev.id].terminateCommunications()
		del self.managedDevices[dev.id]			
		
		self.logger.debug(u'Exiting deviceStopComm for ' + RPFrameworkUtils.to_unicode(dev.name))
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called whenever the server is defining an event / trigger setup
	# by the user
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def triggerStartProcessing(self, trigger):
		self.logger.threaddebug(u'Registering trigger: ' + RPFrameworkUtils.to_unicode(trigger.id))
		
		# if the descendent class does not handle the trigger then we process it by
		# storing it against the trigger type
		if self.registerCustomTrigger(trigger) == False:
			triggerType = trigger.pluginTypeId
			if not (triggerType in self.indigoEvents):
				self.indigoEvents[triggerType] = dict()
			self.indigoEvents[triggerType][trigger.id] = trigger
			
		self.logger.debug(u'Registered trigger: ' + RPFrameworkUtils.to_unicode(trigger.id))
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine gives descendant plugins the chance to process the event
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def registerCustomTrigger(self, trigger):
		return False
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called whenever the server is un-registering a trigger
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def triggerStopProcessing(self, trigger):
		self.logger.threaddebug(u'Stopping trigger: ' + RPFrameworkUtils.to_unicode(trigger.id))
		
		# if the descendent class does not handle the unregistration then we process it by
		# removing it from the dictionary
		if self.registerCustomTrigger(trigger) == False:
			triggerType = trigger.pluginTypeId
			if triggerType in self.indigoEvents:
				if trigger.id in self.indigoEvents[triggerType]:
					del self.indigoEvents[triggerType][trigger.id]
		
		self.logger.debug(u'Stopped trigger: ' + RPFrameworkUtils.to_unicode(trigger.id))
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine gives descendant plugins the chance to unregister the event
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def unRegisterCustomTrigger(self, trigger):
		return False
		
		
	
	#/////////////////////////////////////////////////////////////////////////////////////
	# Asynchronous processing routines
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will run the concurrent processing thread used at the plugin (not
	# device) level - such things as update checks and device reconnections
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def runConcurrentThread(self):
		try:
			# read in any configuration values necessary...
			emptyQueueProcessingThreadSleepTime = float(self.getGUIConfigValue(GUI_CONFIG_PLUGINSETTINGS, GUI_CONFIG_PLUGIN_COMMANDQUEUEIDLESLEEP, u'20'))
			
			while True:
				# process pending commands now...
				reQueueCommandsList = list()
				while not self.pluginCommandQueue.empty():
					lenQueue = self.pluginCommandQueue.qsize()
					self.logger.threaddebug(u'Plugin Command queue has ' + RPFrameworkUtils.to_unicode(lenQueue) + u' command(s) waiting')
					
					# the command name will identify what action should be taken...
					reQueueCommand = False
					command = self.pluginCommandQueue.get()
					if command.commandName == RPFrameworkCommand.CMD_DEVICE_RECONNECT:
						# the command payload will be in the form of a tuple:
						#	(DeviceID, DeviceInstanceIdentifier, ReconnectTime)
						#	ReconnectTime is the datetime where the next reconnection attempt should occur
						timeNow = time.time()
						if timeNow > command.commandPayload[2]:
							if command.commandPayload[0] in self.managedDevices:
								if self.managedDevices[command.commandPayload[0]].deviceInstanceIdentifier == command.commandPayload[1]:
									self.logger.debug(u'Attempting reconnection to device ' + RPFrameworkUtils.to_unicode(command.commandPayload[0]))
									self.managedDevices[command.commandPayload[0]].initiateCommunications()
								else:
									self.logger.threaddebug(u'Ignoring reconnection command for device ' + RPFrameworkUtils.to_unicode(command.commandPayload[0]) + u'; new instance detected')
							else:
								self.logger.debug(u'Ignoring reconnection command for device ' + RPFrameworkUtils.to_unicode(command.commandPayload[0]) + u'; device not created')
						else:
							reQueueCommand = True
					
					elif command.commandName == RPFrameworkCommand.CMD_DEBUG_LOGUPNPDEVICES:
						# kick off the UPnP discovery and logging now
						self.logUPnPDevicesFoundProcessing()
					
					else:
						# allow a base class to process the command
						self.handleUnknownPluginCommand(command, reQueueCommandsList)
					
					# complete the dequeuing of the command, allowing the next
					# command in queue to rise to the top
					self.pluginCommandQueue.task_done()
					if reQueueCommand == True:
						self.logger.threaddebug(u'Plugin command queue not yet ready; requeuing for future execution')
						reQueueCommandsList.append(command)	
						
				# arbitrary time to check to see if we need to check for updates...
				# this shouldn't block unless it is time to check
				self.pollForAvailableUpdate()	
				
				# any commands that did not yet execute should be placed back into the queue
				for commandToRequeue in reQueueCommandsList:
					self.pluginCommandQueue.put(commandToRequeue)
				
				# sleep on an empty queue... note that this should not normally be as granular
				# as a device's communications! (value is in seconds)
				self.sleep(emptyQueueProcessingThreadSleepTime)
				
		except self.StopThread:
			# this exception is simply shutting down the thread... there is nothing
			# that we need to process
			pass
			
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will be called to handle any unknown commands at the plugin level; it
	# can/should be overridden in the plugin implementation (if needed)
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def handleUnknownPluginCommand(self, rpCommand, reQueueCommandsList):
		pass
	
	
	
	#/////////////////////////////////////////////////////////////////////////////////////
	# Indigo definitions helper functions
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will add a new action to the managed actions of the plugin
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def addIndigoAction(self, indigoAction):
		self.indigoActions[indigoAction.indigoActionId] = indigoAction
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will add a new device response to the list of responses that the plugin
	# can automatically handle
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def addDeviceResponseDefinition(self, deviceTypeId, responseDfn):
		if not (deviceTypeId in self.deviceResponseDefinitions):
			self.deviceResponseDefinitions[deviceTypeId] = list()
		self.deviceResponseDefinitions[deviceTypeId].append(responseDfn)
		
		
		
	#/////////////////////////////////////////////////////////////////////////////////////
	# Plugin updater methods... used to check for a new version of the plugin from a URL
	# based upon work by "berkinet" and "Travis" on the Indigo forums
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# this routine will poll for available updates, performing the check only if the next
	# check time has elapsed; it is designed such that it may be called however often by
	# the plugin or devices
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def pollForAvailableUpdate(self):
		# obtain the current date/time and determine if it is after the previously-calculated
		# next check run
		timeNow = time.time()
		if self.updateCheckPollEnabled and timeNow > self.nextUpdateCheck:
			self.checkVersionNow()
			
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# this routine will do the work of executing a check for a new version... it will do
	# the request in a synchronous manner, so should be executed from a separate thread
	# from the GUI thread
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def checkVersionNow(self):
		self.logger.debug(u'Version check initiated')
		try:
			# save the last check time (now) in the plugin's config and our class variable
			timeNow = time.time()
			self.pluginPrefs[u'updaterLastCheck'] = timeNow
			self.nextUpdateCheck = timeNow + self.secondsBetweenUpdateChecks
 			
 			current_version_url = "https://api.indigodomo.com/api/v2/pluginstore/plugin-version-info.json?pluginId={}".format(self.pluginId)
			store_detail_url = "https://www.indigodomo.com/pluginstore/{}/"
		
			# GET the url from the servers with a short timeout (avoids hanging the plugin)
			reply = requests.get(current_version_url, timeout=5)
			
			# This will raise an exception if the server returned an error
			reply.raise_for_status()

			# We now have a good reply so we get the json
			reply_dict = reply.json()
			plugin_dict = reply_dict["plugins"][0]

			# Make sure that the 'latestRelease' element is a dict (could be a string for built-in plugins).
			latest_release = plugin_dict["latestRelease"]
			if isinstance(latest_release, dict):
				# update the member variable (this is used for display purposes in dialogs)
				self.latestReleaseFound = latest_release["number"]
				self.logger.debug(u'Found version v{} versus current version v{}'.format(latest_release["number"], self.pluginVersion))				
			
				# Compare the current version with the one returned in the reply dict
				if LooseVersion(latest_release["number"]) > LooseVersion(self.pluginVersion):			
					# if execution made it this far then an update is available and we need to send
					# the user an update email, if so configured
					
					# always alert to the indigo log
					self.logger.info("A new version of the plugin (v{}) is available at: {}".format(latest_release["number"], store_detail_url.format(plugin_dict["id"])))
					
					emailAddress = self.pluginPrefs.get(u'updaterEmail', u'')
					if len(emailAddress) == 0:
						self.logger.debug(u'No email address for updates found in the config')
						return True
					else:
 						# if there's a checkbox in the config in addition to the email address text box
						# then let the checkbox decide if we should send emails or not
						if self.pluginPrefs.get(u'updaterEmailsEnabled', True) is False:
							return True

 						# get last version Emailed to the user
						lastVersionEmailed = self.pluginPrefs.get(u'updaterLastVersionEmailed', '0')
				
 						# if we already notified the user of this version then bail so that we don'time
						# duplicate the notification
						if lastVersionEmailed == latest_release["number"]:
							self.logger.threaddebug(u'Version notification already emailed to the user about this version')
							return True
					
 						# build the email subject and body for sending to the user
						updateSubject = "Version {} of {} Indigo Plugin available".format(latest_release["number"], self.pluginDisplayName)
						updateBody = "{} v{}\nReleased: {}\n{}\n\nTo update to the latest version of the application, please download the latest release available via the Indigo Plugin Store at {}.".format(
								self.pluginDisplayName, latest_release["number"], latest_release["releaseDate"], plugin_dict["githubRepoUrl"], store_detail_url.format(plugin_dict["id"]))
					
 						# Save this version as the last one emailed in the prefs
						self.pluginPrefs[u'updaterLastVersionEmailed'] = latest_release["number"]
 						indigo.server.sendEmailTo(emailAddress, subject=updateSubject, body=updateBody)
				
					# return true in order to indicate to any caller that an update
					# was found/processed
					return True

			# no update was available...
			return False
		except:
			if self.debugLevel > DEBUGLEVEL_NONE:
				self.logger.exception(u'Error checking for new plugin version.')
			else:
				self.logger.warning(u'Error checking for new plugin version.')
				
	
	
	#/////////////////////////////////////////////////////////////////////////////////////
	# Data Validation functions... these functions allow the plugin or devices to validate
	# user input
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will be called to validate the information entered into the Plugin
	# configuration file
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def validatePrefsConfigUi(self, valuesDict):
		# create an error message dictionary to hold validation issues foundDevice
		errorMessages = indigo.Dict()
		
		# check each defined parameter, if any exist...
		for param in self.pluginConfigParams:
			if param.indigoId in valuesDict:
				# a value is present for this parameter - validate it
				if param.isValueValid(valuesDict[param.indigoId]) == False:
					errorMessages[param.indigoId] = param.invalidValueMessage
					
		# return the validation results...
		if len(errorMessages) == 0:
			return (True, valuesDict)
		else:
			return (False, valuesDict, errorMessages)
	
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will be called when the user has closed the preference dialog
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def closedPrefsConfigUi(self, valuesDict, userCancelled):
		if not userCancelled:
			try:
				self.debugLevel = int(valuesDict.get(u'debugLevel', DEBUGLEVEL_NONE))
			except:
				self.debugLevel = DEBUGLEVEL_NONE
				
			# setup the logging level of the INDIGO logging handler to the selected level
			if self.debugLevel == DEBUGLEVEL_LOW:
				self.indigo_log_handler.setLevel(logging.DEBUG)
			elif self.debugLevel == DEBUGLEVEL_HIGH:
				self.indigo_log_handler.setLevel(logging.THREADDEBUG)
			else:
				self.indigo_log_handler.setLevel(logging.INFO)
			
			self.logger.debug(u'Plugin preferences updated')
			if self.debugLevel == DEBUGLEVEL_NONE:
				self.logger.info(u'Debugging disabled')
			else:
				self.logger.info(u'Debugging enabled... remember to turn off when done!')
			
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called in order to get the initial values for the menu actions
	# defined in MenuItems.xml. The default (as per the base) just returns a values and
	# error dictionary, both blank
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def getMenuActionConfigUiValues(self, menuId):
		valuesDict = indigo.Dict()
		errorMsgDict = indigo.Dict()
		
		if menuId == u'checkForUpdateImmediate':
			# we need to run the update during the launch and then show the results to the
			# user... watch for failures and do not let this go on (must time out) since
			# the dialog could get killed
			updateAvailable = self.checkVersionNow()
			valuesDict["currentVersion"] = RPFrameworkUtils.to_unicode(self.pluginVersion)
			valuesDict["latestVersion"] = self.latestReleaseFound
			
			# give the user a "better" message about the current status
			if self.latestReleaseFound == u'':
				valuesDict["versionCheckResults"] = u'3'
			elif updateAvailable == True:
				valuesDict["versionCheckResults"] = u'1'
			else:
				valuesDict["versionCheckResults"] = u'2'
		
		return (valuesDict, errorMsgDict)
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will be called to validate the information entered into the Device
	# configuration GUI from within Indigo (it will only validate registered params)
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def validateDeviceConfigUi(self, valuesDict, deviceTypeId, devId):
		# create an error message dictionary to hold any validation issues
		# (and their messages) that we find	
		errorMessages = indigo.Dict()
		
		# loop through each parameter for this device and validate one-by-one
		if deviceTypeId in self.managedDeviceParams:
			for param in self.managedDeviceParams[deviceTypeId]:
				if param.indigoId in valuesDict:
					# a parameter value is present, validate it now
					if param.isValueValid(valuesDict[param.indigoId]) == False:
						errorMessages[param.indigoId] = param.invalidValueMessage
					
				elif param.isRequired == True:
					errorMessages[param.indigoId] = param.invalidValueMessage
				
		# return the validation results...
		if len(errorMessages) == 0:
			# process any hidden variables that are used to show state information in
			# indigo or as a RPFramework config/storage
			valuesDict["address"] = self.substituteIndigoValues(self.getGUIConfigValue(deviceTypeId, GUI_CONFIG_ADDRESSKEY, u''), None, valuesDict)
			self.logger.threaddebug(u'Setting address of ' + RPFrameworkUtils.to_unicode(devId) + u' to ' + valuesDict["address"])
			
			return self.validateDeviceConfigUiEx(valuesDict, deviceTypeId, devId)
		else:
			return (False, valuesDict, errorMessages)
	
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will be called to validate any parameters not known to the plugin (not
	# automatically handled and validated); this will only be called once all known
	# parameters have been validated and it MUST return a valid tuple
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def validateDeviceConfigUiEx(self, valuesDict, deviceTypeId, devId):
		return (True, valuesDict)
	
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will validate an action Config UI popup when it is being edited from
	# within the Indigo client; if the action being validated is not a known action then
	# a callback to the plugin implementation will be made
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def validateActionConfigUi(self, valuesDict, typeId, actionId):	
		self.logger.threaddebug(u'Call to validate action: ' + RPFrameworkUtils.to_unicode(typeId))
		if typeId in self.indigoActions:
			actionDefn = self.indigoActions[typeId]
			managedActionValidation = actionDefn.validateActionValues(valuesDict)
			if managedActionValidation[0] == False:
				self.logger.threaddebug(u'Managed validation failed: ' + RPFrameworkUtils.to_unicode(managedActionValidation[1]) + RPFrameworkUtils.to_unicode(managedActionValidation[2]))
			return managedActionValidation
		else:
			return self.validateUnRegisteredActionConfigUi(valuesDict, typeId, actionId)
			
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called to retrieve a dynamic list of elements for an action (or
	# other ConfigUI based) routine
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def getConfigDialogMenu(self, filter=u'', valuesDict=None, typeId="", targetId=0):
		# the routine is designed to pass the call along to the device since most of the
		# time this is device-specific (such as inputs)
		self.logger.threaddebug(u'Dynamic menu requested for Device ID: ' + RPFrameworkUtils.to_unicode(targetId))
		if targetId in self.managedDevices:
			return self.managedDevices[targetId].getConfigDialogMenuItems(filter, valuesDict, typeId, targetId)
		else:
			self.logger.debug(u'Call to getConfigDialogMenu for device not managed by this plugin')
			return []
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called to retrieve a dynamic list of devices that are found on the
	# network matching the service given by the filter
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-	
	def getConfigDialogUPNPDeviceMenu(self, filter=u'', valuesDict=None, typeId=u'', targetId=0):
		self.updateUPNPEnumerationList(typeId)
		return self.parseUPNPDeviceList(self.enumeratedDevices)
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called whenever the user clicks the "Select" button on a device
	# dialog that asks for selecting from an list of enumerated devices
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-	
	def selectUPNPEnumeratedDeviceForUse(self, valuesDict, typeId, devId):
		menuFieldId = self.getGUIConfigValue(typeId, GUI_CONFIG_UPNP_ENUMDEVICESFIELDID, u'upnpEnumeratedDevices')
		targetFieldId = self.getGUIConfigValue(typeId, GUI_CONFIG_UPNP_DEVICESELECTTARGETFIELDID, u'httpAddress')
		if valuesDict[menuFieldId] != u'':
			# the target field may be just the address or may be broken up into multiple parts, separated
			# by a colon (in which case the menu ID value must match!)
			fieldsToUpdate = targetFieldId.split(u':')
			valuesSelected = valuesDict[menuFieldId].split(u':')
			
			fieldIdx = 0
			for field in fieldsToUpdate:
				valuesDict[field] = valuesSelected[fieldIdx]
				fieldIdx += 1
				
		return valuesDict
			
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called to parse out a uPNP search results list in order to createDeviceObject
	# an indigo-friendly menu; usually will be overridden in plugin descendants
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-	
	def parseUPNPDeviceList(self, deviceList):
		try:
			menuItems = []
			for networkDevice in deviceList:
				self.logger.threaddebug(u'Found uPnP Device: ' + RPFrameworkUtils.to_unicode(networkDevice))
				menuItems.append((networkDevice.location, networkDevice.server))
			return menuItems
		except:
			self.logger.warning(u'Error parsing UPNP devices found on the network')
			return []
	
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine should be overridden and should validate any actions which are not
	# already defined within the plugin class
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def validateUnRegisteredActionConfigUi(self, valuesDict, typeId, actionId):
		return (True, valuesDict)
	
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will validate whether or not an IP address is valid as a IPv4 addr
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def isIPv4Valid(self, ip):
		# Make sure a value was entered for the address... an IPv4 should require at least
		# 7 characters (0.0.0.0)
		ip = RPFrameworkUtils.to_unicode(ip)
		if len(ip) < 7:
			return False
			
		# separate the IP address into its components... this limits the format for the
		# user input but is using a fairly standard notation so acceptable
		addressParts = ip.split(u'.')	
		if len(addressParts) != 4:
			return False
				
		for part in addressParts:
			try:
				part = int(part)
				if part < 0 or part > 255:
					return False
			except ValueError:
				return False
				
		# if we make it here, the input should be valid
		return True
				
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will launch the help URL in a new browser window
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def launchForumURL(self, valuesDict, menuId):
		supportUrl = self.getGUIConfigValue(GUI_CONFIG_PLUGINSETTINGS, GUI_CONFIG_PLUGIN_UPDATEDOWNLOADURL, u'http://forums.indigodomo.com/viewforum.php?f=59')
		self.browserOpen(supportUrl)
		
		
	
	#/////////////////////////////////////////////////////////////////////////////////////
	# Action execution routines... these allow automatic processing of actions that are
	# known/managed/defined
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will do the work of processing/executing an action; it is assumed that
	# the plugin developer will only assign the action callback to this routine if it
	# should be handled
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def executeAction(self, pluginAction, indigoActionId=u'', indigoDeviceId=u'', paramValues=None):
		# ensure that the actionID specified by the action is a managed action that
		# we can automatically handle
		if pluginAction != None:
			indigoActionId = pluginAction.pluginTypeId
			indigoDeviceId = pluginAction.deviceId
			paramValues = pluginAction.props
		
		# ensure that action and device are both managed... if so they will each appear in
		# the respective member variable dictionaries
		if not indigoActionId in self.indigoActions:
			self.logger.error(u'Execute action called for non-managed action id: ' + RPFrameworkUtils.to_unicode(indigoActionId))
			return
		if not indigoDeviceId in self.managedDevices:
			self.logger.error(u'Execute action called for non-managed device id: ' + RPFrameworkUtils.to_unicode(indigoDeviceId))
			return
			
		# if execution made it this far then we have the action & device and can execute
		# that action now...
		self.indigoActions[indigoActionId].generateActionCommands(self, self.managedDevices[indigoDeviceId], paramValues)
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will toggled the debug setting on all devices managed... it is used to
	# allow setting the debug status w/o restarting the plugin
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def toggleDebugEnabled(self):
		if self.debugLevel == DEBUGLEVEL_NONE:
			self.debugLevel = DEBUGLEVEL_LOW
			self.indigo_log_handler.setLevel(logging.DEBUG)
			self.pluginPrefs["debugLevel"] = DEBUGLEVEL_LOW
			self.logger.info(u'Debug enabled (on Low) by user')
		else:
			self.debugLevel = DEBUGLEVEL_NONE
			self.indigo_log_handler.setLevel(logging.INFO)
			self.pluginPrefs["debugLevel"] = DEBUGLEVEL_NONE
			self.logger.info(u'Debug disabled by user')
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will be called when the user has created a request to log the UPnP
	# debug information to the Indigo log
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def logUPnPDevicesFound(self, valuesDict, typeId):
		# perform validation here... only real requirement is to have a "type" selected
		# and this should always be the case...
		errorsDict = indigo.Dict()
		
		# add a new command to the plugin's command queue for processing on a background
		# thread (required to avoid Indigo timing out the operation!)
		self.pluginCommandQueue.put(RPFrameworkCommand.RPFrameworkCommand(RPFrameworkCommand.CMD_DEBUG_LOGUPNPDEVICES, commandPayload=None))
		self.logger.info(u'Scheduled UPnP Device Search')
		
		# return back to the dialog to allow it to close
		return (True, valuesDict, errorsDict)
	
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine processing the logging of the UPnP devices once the plugin spools the
	# command on the background thread
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def logUPnPDevicesFoundProcessing(self):		
		try:
			# perform the UPnP search and logging now...
			self.logger.debug(u'Beginning UPnP Device Search')
			serviceTarget = u'ssdp:all'
			discoveryStarted = time.time()
			discoveredDeviceList = RPFrameworkNetworkingUPnP.uPnPDiscover(serviceTarget, timeout=6)
			
			# create an HTML file that contains the details for all of the devices found on the network
			self.logger.debug(u'UPnP Device Search completed... creating output HTML')
			deviceHtml = u'<html><head><title>UPnP Devices Found</title><style type="text/css">html,body { margin: 0px; padding: 0px; width: 100%; height: 100%; }\n.upnpDevice { margin: 10px 0px 8px 5px; border-bottom: solid 1px #505050; }\n.fieldLabel { width: 140px; display: inline-block; }</style></head><body>'
			deviceHtml += u"<div style='background-color: #3f51b5; width: 100%; height: 50px; border-bottom: solid 2px black;'><span style='color: #a1c057; font-size: 25px; font-weight: bold; line-height: 49px; padding-left: 3px;'>RogueProeliator's RPFramework UPnP Discovery Report</span></div>"
			deviceHtml += u"<div style='border-bottom: solid 2px black; padding: 8px 3px;'><span class='fieldLabel'><b>Requesting Plugin:</b></span>" + self.pluginDisplayName + u"<br /><span class='fieldLabel'><b>Service Query:</b></span>" + serviceTarget + u"<br /><span class='fieldLabel'><b>Date Run:</b></span>" + RPFrameworkUtils.to_unicode(discoveryStarted) + "</div>"	
		
			# loop through each device found...
			for device in discoveredDeviceList:
				deviceHtml += u"<div class='upnpDevice'><span class='fieldLabel'>Location:</span><a href='" + RPFrameworkUtils.to_unicode(device.location) + u"' target='_blank'>" + RPFrameworkUtils.to_unicode(device.location) + u"</a><br /><span class='fieldLabel'>USN:</span>" + RPFrameworkUtils.to_unicode(device.usn) + u"<br /><span class='fieldLabel'>ST:</span>" + RPFrameworkUtils.to_unicode(device.st) + u"<br /><span class='fieldLabel'>Cache Time:</span>" + RPFrameworkUtils.to_unicode(device.cache) + u"s"
				for header in device.allHeaders:
					headerKey = RPFrameworkUtils.to_unicode(header[0])
					if headerKey != u'location' and headerKey != u'usn' and headerKey != u'cache-control' and headerKey != u'st' and headerKey != u'ext':
						deviceHtml += u"<br /><span class='fieldLabel'>" + RPFrameworkUtils.to_unicode(header[0]) + u":</span>" + RPFrameworkUtils.to_unicode(header[1])
				deviceHtml += u"</div>"
		
			deviceHtml += u"</body></html>"
		
			# write out the file...
			self.logger.threaddebug(u"Writing UPnP Device Search HTML to file")
			tempFilename = self.getPluginDirectoryFilePath("tmpUPnPDiscoveryResults.html")
			upnpResultsHtmlFile = open(tempFilename, 'w')
			upnpResultsHtmlFile.write(RPFrameworkUtils.to_str(deviceHtml))
			upnpResultsHtmlFile.close()
		
			# launch the file in a browser window via the command line
			call(["open", tempFilename])
			self.logger.info(u'Created UPnP results temporary file at ' + RPFrameworkUtils.to_unicode(tempFilename))
		except:
			self.logger.error(u'Error generating UPnP report')
	
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will be called whenever the user has chosen to dump the device details
	# to the event log via the menuitem action
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def dumpDeviceDetailsToLog(self, valuesDict, typeId):
		errorsDict = indigo.Dict()
		devicesToDump = valuesDict.get(u'devicesToDump', None)
		
		if devicesToDump is None or len(devicesToDump) == 0:
			errorsDict[u'devicesToDump'] = u'Please select one or more devices'
			return (False, valuesDict, errorsDict)
		else:
			for deviceId in devicesToDump:
				self.logger.info(u'Dumping details for DeviceID: ' + RPFrameworkUtils.to_unicode(deviceId))
				dumpDev = indigo.devices[int(deviceId)]
				self.logger.info(unicode(dumpDev))
			return (True, valuesDict, errorsDict)
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine provides the callback for devices based off a Dimmer... since the call
	# comes into the plugin we will pass it off the device now
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def actionControlDimmerRelay(self, action, dev):
		# transform this action into our standard "executeAction" parameters so that the
		# action is processed in a standard way
		indigoActionId = RPFrameworkUtils.to_unicode(action.deviceAction)
		if indigoActionId == u'11':
			indigoActionId = u'StatusRequest'
		
		indigoDeviceId = dev.id
		paramValues = dict()
		paramValues["actionValue"] = RPFrameworkUtils.to_unicode(action.actionValue)
		self.logger.debug(u'Dimmer Command: ActionId=' + indigoActionId + u'; Device=' + RPFrameworkUtils.to_unicode(indigoDeviceId) + u'; actionValue=' + paramValues["actionValue"])
		
		self.executeAction(None, indigoActionId, indigoDeviceId, paramValues)
		
	
	
	#/////////////////////////////////////////////////////////////////////////////////////
	# Helper routines
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will perform a substitution on a string for all Indigo-values that
	# may be substituted (variables, devices, states, parameters, etc.)
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def substituteIndigoValues(self, input, rpDevice, actionParamValues):
		substitutedString = input
		if substitutedString is None:
			substitutedString = u''
		
		# substitute each parameter value called for in the string; this is done first so that
		# the parameter could call for a substitution
		apMatcher = re.compile(u'%ap:([a-z\d]+)%', re.IGNORECASE)
		for match in apMatcher.finditer(substitutedString):
			substitutedString = substitutedString.replace(RPFrameworkUtils.to_unicode(match.group(0)), RPFrameworkUtils.to_unicode(actionParamValues[match.group(1)]))
			
		# substitute device properties since the substitute method below handles states...
		dpMatcher = re.compile(u'%dp:([a-z\d]+)%', re.IGNORECASE)
		for match in dpMatcher.finditer(substitutedString):
			if type(rpDevice.indigoDevice.pluginProps.get(match.group(1), None)) is indigo.List:
				substitutedString = substitutedString.replace(RPFrameworkUtils.to_unicode(match.group(0)), u"'" + u','.join(rpDevice.indigoDevice.pluginProps.get(match.group(1))) + u"'")
			else:
				substitutedString = substitutedString.replace(RPFrameworkUtils.to_unicode(match.group(0)), RPFrameworkUtils.to_unicode(rpDevice.indigoDevice.pluginProps.get(match.group(1), u'')))
			
		# handle device states for any where we do not specify a device id
		dsMatcher = re.compile(u'%ds:([a-z\d]+)%', re.IGNORECASE)
		for match in dsMatcher.finditer(substitutedString):
			substitutedString = substitutedString.replace(RPFrameworkUtils.to_unicode(match.group(0)), RPFrameworkUtils.to_unicode(rpDevice.indigoDevice.states.get(match.group(1), u'')))
			
		# handle parent device properties (for child devices)
		if rpDevice != None:
			if self.getGUIConfigValue(rpDevice.indigoDevice.deviceTypeId, GUI_CONFIG_ISCHILDDEVICEID, u'false').lower() == 'true':
				parentDeviceId = int(rpDevice.indigoDevice.pluginProps[self.getGUIConfigValue(rpDevice.indigoDevice.deviceTypeId, GUI_CONFIG_PARENTDEVICEIDPROPERTYNAME, u'')])
				if parentDeviceId in self.managedDevices:
					parentRPDevice = self.managedDevices[parentDeviceId]
					pdpMatcher = re.compile(u'%pdp:([a-z\d]+)%', re.IGNORECASE)
					for match in pdpMatcher.finditer(substitutedString):
						if type(parentRPDevice.indigoDevice.pluginProps.get(match.group(1), None)) is indigo.List:
							substitutedString = substitutedString.replace(RPFrameworkUtils.to_unicode(match.group(0)), u"'" + u','.join(parentRPDevice.indigoDevice.pluginProps.get(match.group(1))) + u"'")
						else:
							substitutedString = substitutedString.replace(RPFrameworkUtils.to_unicode(match.group(0)), RPFrameworkUtils.to_unicode(parentRPDevice.indigoDevice.pluginProps.get(match.group(1), u'')))
			
		# handle plugin preferences
		ppMatcher = re.compile(u'%pp:([a-z\d]+)%', re.IGNORECASE)
		for match in ppMatcher.finditer(substitutedString):
			substitutedString = substitutedString.replace(RPFrameworkUtils.to_unicode(match.group(0)), RPFrameworkUtils.to_unicode(self.pluginPrefs.get(match.group(1), u'')))
			
		# perform the standard indigo values substitution...
		substitutedString = self.substitute(substitutedString)
		
		# return the new string to the caller
		return substitutedString
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will set a GUI configuration value given the device type, the key and
	# the value for the device
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def putGUIConfigValue(self, deviceTypeId, configKey, configValue):
		if not deviceTypeId in self.managedDeviceGUIConfigs:
			self.managedDeviceGUIConfigs[deviceTypeId] = dict()
		self.managedDeviceGUIConfigs[deviceTypeId][configKey] = configValue
	
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will retrieve a GUI config value for a device type and key; it allows
	# passing in a default value in case the value is not found in the settings
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def getGUIConfigValue(self, deviceTypeId, configKey, defaultValue=u''):
		if not deviceTypeId in self.managedDeviceGUIConfigs:
			return defaultValue
		elif configKey in self.managedDeviceGUIConfigs[deviceTypeId]:
			return self.managedDeviceGUIConfigs[deviceTypeId][configKey]
		else:
			self.logger.threaddebug(u'Returning default GUIConfigValue for ' + deviceTypeId + u':' + configKey)
			return defaultValue
			
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will retrieve the list of device response definitions for the given
	# device type
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def getDeviceResponseDefinitions(self, deviceTypeId):
		if deviceTypeId in self.deviceResponseDefinitions:
			return self.deviceResponseDefinitions[deviceTypeId]
		else:
			return ()
	
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will update the enumeratedDevices list of devices from the uPNP
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def updateUPNPEnumerationList(self, deviceTypeId):
		uPNPCacheTime = int(self.getGUIConfigValue(deviceTypeId, GUI_CONFIG_UPNP_CACHETIMESEC, u'180'))
		if time.time() > self.lastDeviceEnumeration + uPNPCacheTime or len(self.enumeratedDevices) == 0:
			serviceId = self.getGUIConfigValue(deviceTypeId, GUI_CONFIG_UPNP_SERVICE, u'ssdp:all')
			self.logger.debug(u'Performing uPnP search for: ' + serviceId)
			discoveredDevices = RPFrameworkNetworkingUPnP.uPnPDiscover(serviceId)
			self.logger.debug(u'Found ' + RPFrameworkUtils.to_unicode(len(discoveredDevices)) + u' devices')
			
			self.enumeratedDevices = discoveredDevices
			self.lastDeviceEnumeration = time.time()
			
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will get the full path to a file with the given name inside the plugin
	# directory; note this is specifically returning a string, not unicode, to allow
	# use of the IO libraries which require ascii
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def getPluginDirectoryFilePath(self, fileName, pluginName = None):
		if pluginName is None:
			pluginName = self.pluginDisplayName.replace(' Plugin', '')
		indigoBasePath = indigo.server.getInstallFolderPath()
		
		requestedFilePath = os.path.join(indigoBasePath, "Plugins/" + pluginName + ".indigoPlugin/Contents/Server Plugin/" + fileName)
		return RPFrameworkUtils.to_str(requestedFilePath)
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will write out a plugin report to a file; it is intended to give us a
	# standard routine and look/feel for generating reports from the plugins
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def writePluginReport(self, headerText, headerProperties, reportHtml, reportFilename, isRelativePath = True):
		reportHtmlHeader = u"<html><head><title>" + headerText + u"</title><style type='text/css'>html,body { margin: 0px; padding: 0px; width: 100%; height: 100%; }\n.upnpDevice { margin: 10px 0px 8px 5px; border-bottom: solid 1px #505050; }\n.fieldLabel { width: 140px; display: inline-block; }</style></head><body>"
		reportHtmlHeader += u"<div style='background-color: #3f51b5; width: 100%; height: 50px; border-bottom: solid 2px black;'><span style='color: #a1c057; font-size: 25px; font-weight: bold; line-height: 49px; padding-left: 3px;'>" + headerText + u"</span></div>"
		if len(headerProperties) > 0:
			reportHtmlHeader += u"<div style='border-bottom: solid 2px black; padding: 8px 3px;'>"
			for headerProp in headerProperties:
				reportHtmlHeader += u"<div><span class='fieldLabel'><b>" + RPFrameworkUtils.to_unicode(headerProp[0]) + u"</b></span>" + RPFrameworkUtils.to_unicode(headerProp[1]) + u"</div>"
			reportHtmlHeader += u"</div>"
			
		reportFooter = u"</body></html>"
		
		reportFullHtml = reportHtmlHeader + reportHtml + reportFooter
		
		if isRelativePath == True:
			reportFilename = self.getPluginDirectoryFilePath(reportFilename)
		reportOutputFile = open(reportFilename, 'w')
		reportOutputFile.write(RPFrameworkUtils.to_str(reportFullHtml))
		reportOutputFile.close()
		
		return reportFilename
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is called whenever the plugin is updating from an older version, as
	# determined by the plugin property and plugin version number
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def performPluginUpgradeMaintenance(self, oldVersion, newVersion):
		if oldVersion == u'':
			self.logger.info(u'Performing first upgrade/run of version ' + newVersion)
		else:
			self.logger.info(u'Performing upgrade from ' + oldVersion + ' to ' + newVersion)
			
		# execute the version-specific tasks
		if oldVersion == u'':
			# this is the first run of the plugin or the first run of the Indigo 7
			# version... remove unused Requests module if it is present
			pluginBasePath = os.getcwd()
			rpFrameworkRequestsPath = os.path.join(pluginBasePath, "RPFramework/requests")
			if os.path.isdir(rpFrameworkRequestsPath):
				try:
					self.logger.debug(u'Removing unused directory tree at ' + rpFrameworkRequestsPath)
					shutil.rmtree(rpFrameworkRequestsPath)
				except:
					self.logger.exception(u'Failed to remove legacy "requests" from RPFramework directory')
					
		# allow the descendant classes to perform their own upgrade options
		self.performPluginUpgrade(oldVersion, newVersion)
		
		# update the version flag within our plugin
		self.pluginPrefs['loadedPluginVersion'] = newVersion
		self.logger.debug(u'Completed plugin updating/installation for ' + newVersion)
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine may be used by plugins to perform any upgrades specific to the plugin;
	# it will be called following the framework's update processing
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def performPluginUpgrade(self, oldVersion, newVersion):
		pass
		
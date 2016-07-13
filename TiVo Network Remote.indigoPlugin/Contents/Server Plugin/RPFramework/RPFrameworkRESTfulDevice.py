#! /usr/bin/env python
# -*- coding: utf-8 -*-
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
# RPFrameworkRESTfulDevice by RogueProeliator <adam.d.ashe@gmail.com>
# 	This class is a concrete implementation of the RPFrameworkDevice as a device which
#	communicates via a REST style HTTP connection.
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
#	Version 5:
#		Added GET operation command processing to the PUT command processing
#		Added status polling (as found in the Telnet device) to the RESTFul device
#		Added better reading of GET operation values (was read twice before)
#	Version 7:
#		Added short error message w/ trace only if debug is on for GET/PUT/SOAP
#		Added support for device database
#		Added overridable error handling function
#	Version 8:
#		Removed update check as it is now at the plugin level
#	Version 10:
#		Added the DOWNLOAD_FILE command to save a file to disc from network (HTTP)
#	Version 12:
#		Added a shortened wait period after a command queue has recently emptied
#	Version 14:
#		Added custom header overridable function
#		Added JSON command
#		Changed handleDeviceResponse to get 3 arguments (reponse obj, text, command)
#		Fixed bug with the download file command when no authentication is enabled
#	Version 15:
#		Fixed bug with download file when issue occurs (null reference exception)
#	Version 17:
#		Added unicode support
#		Changed the GET operation to use requests
#		Changed the DOWNLOADFILE/DOWNLOADIMAGE operations to use requests
#		Changed command parameters for all requests to allow additional options
#		Added new handleDeviceTextResponse routine to handle response
#		Added requests' response object to the restful error call
#		Changed error logging to the new plugin-based logErrorMessage routine
#		Implemented POST operation via Requests
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
import string
import subprocess
import sys
import threading
import telnetlib
import time
import urllib
import urllib2
from urlparse import urlparse

import requests
import RPFrameworkPlugin
import RPFrameworkCommand
import RPFrameworkDevice
import RPFrameworkNetworkingWOL
import RPFrameworkUtils


#/////////////////////////////////////////////////////////////////////////////////////////
# Constants and configuration variables
#/////////////////////////////////////////////////////////////////////////////////////////
CMD_RESTFUL_PUT = u'RESTFUL_PUT'
CMD_RESTFUL_GET = u'RESTFUL_GET'
CMD_SOAP_REQUEST = u'SOAP_REQUEST'
CMD_JSON_REQUEST = u'JSON_REQUEST'
CMD_DOWNLOADFILE = u'DOWNLOAD_FILE'
CMD_DOWNLOADIMAGE = u'DOWNLOAD_IMAGE'

GUI_CONFIG_RESTFULSTATUSPOLL_INTERVALPROPERTY = u'updateStatusPollerIntervalProperty'
GUI_CONFIG_RESTFULSTATUSPOLL_ACTIONID = u'updateStatusPollerActionId'
GUI_CONFIG_RESTFULSTATUSPOLL_STARTUPDELAY = u'updateStatusPollerStartupDelay'

GUI_CONFIG_RESTFULDEV_EMPTYQUEUE_SPEEDUPCYCLES = u'emptyQueueReducedWaitCycles'


#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
# RPFrameworkRESTfulDevice
#	This class is a concrete implementation of the RPFrameworkDevice as a device which
#	communicates via a REST style HTTP connection.
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
class RPFrameworkRESTfulDevice(RPFrameworkDevice.RPFrameworkDevice):
	
	#/////////////////////////////////////////////////////////////////////////////////////
	# Class construction and destruction methods
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# Constructor called once upon plugin class receiving a command to start device
	# communication. Defers to the base class for processing but initializes params
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def __init__(self, plugin, device):
		super(RPFrameworkRESTfulDevice, self).__init__(plugin, device)
		
		
	#/////////////////////////////////////////////////////////////////////////////////////
	# Processing and command functions
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine is designed to run in a concurrent thread and will continuously monitor
	# the commands queue for work to do.
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def concurrentCommandProcessingThread(self, commandQueue):
		try:
			self.hostPlugin.logDebugMessage(u'Concurrent Processing Thread started for device ' + RPFrameworkUtils.to_unicode(self.indigoDevice.id), RPFrameworkPlugin.DEBUGLEVEL_MED)
		
			# obtain the IP or host address that will be used in connecting to the
			# RESTful service via a function call to allow overrides
			deviceHTTPAddress = self.getRESTfulDeviceAddress()
			if deviceHTTPAddress is None:
				indigo.server.log(u'No IP address specified for device ' + RPFrameworkUtils.to_unicode(self.indigoDevice.id) + u'; ending command processing thread.', isError=True)
				return
			
			# retrieve any configuration information that may have been setup in the
			# plugin configuration and/or device configuration
			updateStatusPollerPropertyName = self.hostPlugin.getGUIConfigValue(self.indigoDevice.deviceTypeId, GUI_CONFIG_RESTFULSTATUSPOLL_INTERVALPROPERTY, u'updateInterval')
			updateStatusPollerInterval = int(self.indigoDevice.pluginProps.get(updateStatusPollerPropertyName, u'90'))
			updateStatusPollerNextRun = None
			updateStatusPollerActionId = self.hostPlugin.getGUIConfigValue(self.indigoDevice.deviceTypeId, GUI_CONFIG_RESTFULSTATUSPOLL_ACTIONID, u'')
			emptyQueueReducedWaitCycles = int(self.hostPlugin.getGUIConfigValue(self.indigoDevice.deviceTypeId, GUI_CONFIG_RESTFULDEV_EMPTYQUEUE_SPEEDUPCYCLES, u'80'))
			
			# spin up the database connection, if this plugin supports databases
			self.dbConn = self.hostPlugin.openDatabaseConnection(self.indigoDevice.deviceTypeId)
			
			# begin the infinite loop which will run as long as the queue contains commands
			# and we have not received an explicit shutdown request
			continueProcessingCommands = True
			lastQueuedCommandCompleted = 0
			while continueProcessingCommands == True:
				# process pending commands now...
				while not commandQueue.empty():
					lenQueue = commandQueue.qsize()
					self.hostPlugin.logDebugMessage(u'Command queue has ' + RPFrameworkUtils.to_unicode(lenQueue) + u' command(s) waiting', RPFrameworkPlugin.DEBUGLEVEL_HIGH)
					
					# the command name will identify what action should be taken... we will handle the known
					# commands and dispatch out to the device implementation, if necessary, to handle unknown
					# commands
					command = commandQueue.get()
					if command.commandName == RPFrameworkCommand.CMD_INITIALIZE_CONNECTION:
						# specialized command to instanciate the concurrent thread
						# safely ignore this... just used to spin up the thread
						self.hostPlugin.logDebugMessage(u'Create connection command de-queued', RPFrameworkPlugin.DEBUGLEVEL_MED)
						
						# if the device supports polling for status, it may be initiated here now; however, we should implement a pause to ensure that
						# devices are created properly (RESTFul devices may respond too fast since no connection need be established)
						statusUpdateStartupDelay = float(self.hostPlugin.getGUIConfigValue(self.indigoDevice.deviceTypeId, GUI_CONFIG_RESTFULSTATUSPOLL_STARTUPDELAY, u'3'))
						if statusUpdateStartupDelay > 0.0:
							commandQueue.put(RPFrameworkCommand.RPFrameworkCommand(RPFrameworkCommand.CMD_PAUSE_PROCESSING, commandPayload=str(statusUpdateStartupDelay)))
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
							self.hostPlugin.logDebugMessage(u'Initiating sleep of ' + RPFrameworkUtils.to_unicode(pauseTime) + u' seconds from command.', RPFrameworkPlugin.DEBUGLEVEL_MED)
							time.sleep(pauseTime)
						except:
							indigo.server.log(u'Invalid pause time requested', isError=True)
							
					elif command.commandName == RPFrameworkCommand.CMD_UPDATE_DEVICE_STATUS_FULL:
						# this command instructs the plugin to update the full status of the device (all statuses
						# that may be read from the device should be read)
						if updateStatusPollerActionId != u'':
							self.hostPlugin.logDebugMessage(u'Executing full status update request...', RPFrameworkPlugin.DEBUGLEVEL_MED)
							self.hostPlugin.executeAction(None, indigoActionId=updateStatusPollerActionId, indigoDeviceId=self.indigoDevice.id, paramValues=None)
							updateStatusPollerNextRun = time.time() + updateStatusPollerInterval
						else:
							self.hostPlugin.logDebugMessage(u'Ignoring status update request, no action specified to update device status', RPFrameworkPlugin.DEBUGLEVEL_HIGH)
							
					elif command.commandName == RPFrameworkCommand.CMD_NETWORKING_WOL_REQUEST:
						# this is a request to send a Wake-On-LAN request to a network-enabled device
						# the command payload should be the MAC address of the device to wake up
						try:
							RPFrameworkNetworkingWOL.sendWakeOnLAN(command.commandPayload)
						except:
							self.hostPlugin.logErrorMessage(u'Failed to send Wake-on-LAN packet')
						
					elif command.commandName == CMD_RESTFUL_GET or command.commandName == CMD_RESTFUL_PUT or command.commandName == CMD_DOWNLOADFILE or command.commandName == CMD_DOWNLOADIMAGE:
						try:
							self.hostPlugin.logDebugMessage(u'Processing GET operation: ' + RPFrameworkUtils.to_unicode(command.commandPayload), RPFrameworkPlugin.DEBUGLEVEL_MED)
							
							# gather all of the parameters from the command payload
							# the payload should have the following format:
							# [0] => request method (http|https|etc.)
							# [1] => path for the GET operation
							# [2] => authentication type: none|basic|digest
							# [3] => username
							# [4] => password
							#
							# CMD_DOWNLOADFILE or CMD_DOWNLOADIMAGE
							# [5] => download filename/path
							# [6] => image resize width
							# [7] => image resize height
							#
							# CMD_RESTFUL_PUT
							# [5] => data to post as the body (if any, may be blank)
							commandPayloadList = command.getPayloadAsList()
							fullGetUrl = commandPayloadList[0] + u'://' + deviceHTTPAddress[0] + u':' + RPFrameworkUtils.to_unicode(deviceHTTPAddress[1]) + commandPayloadList[1]
							
							customHeaders = {}
							self.addCustomHTTPHeaders(customHeaders)
							
							authenticationParam = None
							authenticationType = u'none'
							username = u''
							password = u''
							if len(commandPayloadList) >= 3:
								authenticationType = commandPayloadList[2]
							if len(commandPayloadList) >= 4:
								username = commandPayloadList[3]
							if len(commandPayloadList) >= 5:
								password = commandPayloadList[4]
							if authenticationType != 'none' and username != u'':
								self.hostPlugin.logDebugMessage(u'Using login credentials... Username=> ' + username + u'; Password=>' + RPFrameworkUtils.to_unicode(len(password)) + u' characters long', RPFrameworkPlugin.DEBUGLEVEL_HIGH)
								authenticationParam = (username, password)
							
							# execute the URL fetching depending upon the method requested
							if command.commandName == CMD_RESTFUL_GET or command.commandName == CMD_DOWNLOADFILE or command.commandName == CMD_DOWNLOADIMAGE:
								responseObj = requests.get(fullGetUrl, auth=authenticationParam, headers=customHeaders, verify=False)
							elif command.commandName == CMD_RESTFUL_PUT:
								dataToPost = None
								if len(commandPayloadList) >= 6:
									dataToPost = commandPayloadList[5]
								responseObj = requests.post(fullGetUrl, auth=authenticationParam, headers=customHeaders, verify=False, data=dataToPost)
								
							# if the network command failed then allow the error processor to handle the issue
							if responseObj.status_code == 200:
								# the response handling will depend upon the type of command... binary returns must be
								# handled separately from (expected) text-based ones
								if command.commandName == CMD_DOWNLOADFILE or command.commandName == CMD_DOWNLOADIMAGE:
									# this is a binary return that should be saved to the file system without modification
									if len(commandPayloadList) >= 6:
										saveLocation = commandPayloadList[5]
									
										# execute the actual save from the binary response stream
										try:
											localFile = open(RPFrameworkUtils.to_str(saveLocation), "wb")
											localFile.write(responseObj.content)
											self.hostPlugin.logDebugMessage(u'Command Response: [' + RPFrameworkUtils.to_unicode(responseObj.status_code) + u'] -=- binary data written to ' + RPFrameworkUtils.to_unicode(saveLocation) + u'-=-', RPFrameworkPlugin.DEBUGLEVEL_HIGH)
										
											if command.commandName == CMD_DOWNLOADIMAGE:
												imageResizeWidth = 0
												imageResizeHeight = 0
												if len(command.commandPayload) >= 7:
													imageResizeWidth = int(command.commandPayload[6])
												if len(command.commandPayload) >= 8:
													imageResizeHeight = int(command.commandPayload[7])
								
												resizeCommandLine = u''
												if imageResizeWidth > 0 and imageResizeHeight > 0:
													# we have a specific size as a target...
													resizeCommandLine = u'sips -z ' + RPFrameworkUtils.to_unicode(imageResizeHeight) + u' ' + RPFrameworkUtils.to_unicode(imageResizeWidth) + u' ' + saveLocation
												elif imageResizeWidth > 0:
													# we have a maximum size measurement
													resizeCommandLine = u'sips -Z ' + RPFrameworkUtils.to_unicode(imageResizeWidth) + u' ' + saveLocation
									
												# if a command line has been formed, fire that off now...
												if resizeCommandLine == u'':
													self.hostPlugin.logDebugMessage(u'No image size specified for ' + RPFrameworkUtils.to_unicode(saveLocation) + u'; skipping resize.', RPFrameworkPlugin.DEBUGLEVEL_MED)
												else:
													self.hostPlugin.logDebugMessage(u'Executing resize via command line "' + resizeCommandLine + u'"', RPFrameworkPlugin.DEBUGLEVEL_HIGH)
													try:
														subprocess.Popen(resizeCommandLine, shell=True)
														self.hostPlugin.logDebugMessage(saveLocation + u' resized via sip shell command', RPFrameworkPlugin.DEBUGLEVEL_HIGH)
													except:
														self.hostPlugin.logErrorMessage(u'Error resizing image via sips')
										finally:
											if not localFile is None:
												localFile.close()					
									else:
										indigo.server.log(u'Unable to complete download action - no filename specified', isError=True)
								else:
									# handle this return as a text-based return
									self.hostPlugin.logDebugMessage(u'Command Response: [' + RPFrameworkUtils.to_unicode(responseObj.status_code) + u'] ' + RPFrameworkUtils.to_unicode(responseObj.text), RPFrameworkPlugin.DEBUGLEVEL_HIGH)
									self.hostPlugin.logDebugMessage(command.commandName + u' command completed; beginning response processing', RPFrameworkPlugin.DEBUGLEVEL_HIGH)
									self.handleDeviceTextResponse(responseObj, command)
									self.hostPlugin.logDebugMessage(command.commandName + u' command response processing completed', RPFrameworkPlugin.DEBUGLEVEL_HIGH)
									
							elif responseObj.status_code == 401:
								self.handleRESTfulError(command, u'401 - Unauthorized', responseObj)
							
							else:
								self.handleRESTfulError(command, str(responseObj.status_code), responseObj)
							 	
						except Exception, e:
							self.handleRESTfulError(command, e, responseObj)
						
					elif command.commandName == CMD_SOAP_REQUEST or command.commandName == CMD_JSON_REQUEST:
						responseObj = None
						try:
							# this is to post a SOAP request to a web service... this will be similar to a restful put request
							# but will contain a body payload
							self.hostPlugin.logDebugMessage(u'Received SOAP/JSON command request: ' + command.commandPayload, RPFrameworkPlugin.DEBUGLEVEL_HIGH)
							soapPayloadParser = re.compile("^\s*([^\n]+)\n\s*([^\n]+)\n(.*)$", re.DOTALL)
							soapPayloadData = soapPayloadParser.match(command.commandPayload)
							soapPath = soapPayloadData.group(1).strip()
							soapAction = soapPayloadData.group(2).strip()
							soapBody = soapPayloadData.group(3).strip()							
							fullGetUrl = u'http://' + deviceHTTPAddress[0] + u':' + RPFrameworkUtils.to_str(deviceHTTPAddress[1]) + RPFrameworkUtils.to_str(soapPath)
							self.hostPlugin.logDebugMessage(u'Processing SOAP/JSON operation to ' + fullGetUrl, RPFrameworkPlugin.DEBUGLEVEL_MED)

							customHeaders = {}
							self.addCustomHTTPHeaders(customHeaders)
							if command.commandName == CMD_SOAP_REQUEST:
								customHeaders["Content-type"] = "text/xml; charset=\"UTF-8\""
								customHeaders["SOAPAction"] = RPFrameworkUtils.to_str(soapAction)
							else:
								customHeaders["Content-type"] = "application/json"
							
							# execute the URL post to the web service
							self.hostPlugin.logDebugMessage(u'Sending SOAP/JSON request:\n' + RPFrameworkUtils.to_str(soapBody), RPFrameworkPlugin.DEBUGLEVEL_HIGH)
							responseObj = requests.post(fullGetUrl, headers=customHeaders, verify=False, data=RPFrameworkUtils.to_str(soapBody))
							
							if responseObj.status_code == 200:
								# handle this return as a text-based return
								self.hostPlugin.logDebugMessage(u'Command Response: [' + RPFrameworkUtils.to_unicode(responseObj.status_code) + u'] ' + RPFrameworkUtils.to_unicode(responseObj.text), RPFrameworkPlugin.DEBUGLEVEL_HIGH)
								self.hostPlugin.logDebugMessage(command.commandName + u' command completed; beginning response processing', RPFrameworkPlugin.DEBUGLEVEL_HIGH)
								self.handleDeviceTextResponse(responseObj, command)
								self.hostPlugin.logDebugMessage(command.commandName + u' command response processing completed', RPFrameworkPlugin.DEBUGLEVEL_HIGH)
								
							else:
								self.handleRESTfulError(command, str(responseObj.status_code), responseObj)

						except Exception, e:
							self.handleRESTfulError(command, e, responseObj)
					
					else:
						# this is an unknown command; dispatch it to another routine which is
						# able to handle the commands (to be overridden for individual devices)
						self.handleUnmanagedCommandInQueue(deviceHTTPAddress, command)
					
					# if the command has a pause defined for after it is completed then we
					# should execute that pause now
					if command.postCommandPause > 0.0 and continueProcessingCommands == True:
						self.hostPlugin.logDebugMessage(u'Post Command Pause: ' + RPFrameworkUtils.to_unicode(command.postCommandPause), RPFrameworkPlugin.DEBUGLEVEL_MED)
						time.sleep(command.postCommandPause)
					
					# complete the dequeuing of the command, allowing the next
					# command in queue to rise to the top
					commandQueue.task_done()
					lastQueuedCommandCompleted = emptyQueueReducedWaitCycles
				
				# when the queue is empty, pause a bit on each iteration
				if continueProcessingCommands == True:
					# if we have just completed a command recently, half the amount of
					# wait time, assuming that a subsequent command could be forthcoming
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
			pass
		except Exception:
			self.hostPlugin.exceptionLog()
		except:
			self.hostPlugin.exceptionLog()
		finally:
			self.hostPlugin.logDebugMessage(u'Command thread ending processing', RPFrameworkPlugin.DEBUGLEVEL_LOW)
			self.hostPlugin.closeDatabaseConnection(self.dbConn)
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine should return the HTTP address that will be used to connect to the
	# RESTful device. It may connect via IP address or a host name
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def getRESTfulDeviceAddress(self):
		return None
	
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine should be overridden in individual device classes whenever they must
	# handle custom commands that are not already defined
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def handleUnmanagedCommandInQueue(self, deviceHTTPAddress, rpCommand):
		pass
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will be called prior to any network operation to allow the addition
	# of custom headers to the request (does not include file download)
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def addCustomHTTPHeaders(self, httpRequest):
		pass
		
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will process any response from the device following the list of
	# response objects defined for this device type. For telnet this will always be
	# a text string
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def handleDeviceTextResponse(self, responseObj, rpCommand):
		# loop through the list of response definitions defined in the (base) class
		# and determine if any match
		responseText = responseObj.text
		for rpResponse in self.hostPlugin.getDeviceResponseDefinitions(self.indigoDevice.deviceTypeId):
			if rpResponse.isResponseMatch(responseText, rpCommand, self, self.hostPlugin):
				self.hostPlugin.logDebugMessage(u'Found response match: ' + RPFrameworkUtils.to_unicode(rpResponse.responseId), RPFrameworkPlugin.DEBUGLEVEL_MED)
				rpResponse.executeEffects(responseText, rpCommand, self, self.hostPlugin)
	
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will handle an error as thrown by the REST call... it allows 
	# descendant classes to do their own processing
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-		
	def handleRESTfulError(self, rpCommand, err, response=None):
		if rpCommand.commandName == CMD_RESTFUL_PUT or rpCommand.commandName == CMD_RESTFUL_GET:
			self.hostPlugin.logErrorMessage(u'An error occurred executing the GET/PUT request (Device: ' + RPFrameworkUtils.to_unicode(self.indigoDevice.id) + u'): ' + RPFrameworkUtils.to_unicode(err))
		else:
			self.hostPlugin.logErrorMessage(u'An error occurred processing the SOAP/JSON POST request: (Device: ' + RPFrameworkUtils.to_unicode(self.indigoDevice.id) + u'): ' + RPFrameworkUtils.to_unicode(err))		
	
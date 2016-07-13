#! /usr/bin/env python
# -*- coding: utf-8 -*-
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
# RPFrameworkDeviceResponse by RogueProeliator <adam.d.ashe@gmail.com>
# 	Class for all RogueProeliator's "incoming" responses such that they may be
#	automatically processed by base classes
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
#	Version 6:
#		Added error catching surrounding effect execution; now outputs to log instead of
#			crashing on error
#	Version 17:
#		Added unicode support
#		Change exception logging to new plugin-object based error logging
#	Version 18:
#		Added support for updateExecCondition specification on response processing effects
#
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////


#/////////////////////////////////////////////////////////////////////////////////////////
# Python imports
#/////////////////////////////////////////////////////////////////////////////////////////
import indigo
import math
import re
import RPFrameworkCommand
import RPFrameworkPlugin
import RPFrameworkUtils

#/////////////////////////////////////////////////////////////////////////////////////////
# Constants and configuration variables
#/////////////////////////////////////////////////////////////////////////////////////////
RESPONSE_EFFECT_UPDATESTATE = u'updateDeviceState'
RESPONSE_EFFECT_QUEUECOMMAND = u'queueCommand'
RESPONSE_EFFECT_CALLBACK = u'eventCallback'


#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
# RPFrameworkDeviceResponse
#	Class for all RogueProeliator's "incoming" responses such that they may be
#	automatically processed by base classes
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
class RPFrameworkDeviceResponse(object):
	
	#/////////////////////////////////////////////////////////////////////////////////////
	# Class construction and destruction methods
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# Constructor allows passing in the data that makes up the response object
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def __init__(self, responseId, criteriaFormatString, matchExpression, respondToActionId=u''):
		self.responseId = responseId
		self.criteriaFormatString = criteriaFormatString
		self.respondToActionId = respondToActionId
		self.matchExpression = matchExpression
		self.matchResultEffects = list()
		
	
	#/////////////////////////////////////////////////////////////////////////////////////
	# Effect definition functions
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# Allows an outside class to add a new effect to this response object
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def addResponseEffect(self, effect):
		self.matchResultEffects.append(effect)
		
	
	#/////////////////////////////////////////////////////////////////////////////////////
	# Testing and Execution functions
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will test the given input to determine if it is a match for the
	# response definition
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def isResponseMatch(self, responseObj, rpCommand, rpDevice, rpPlugin):
		if self.criteriaFormatString is None or self.criteriaFormatString == u'' or self.matchExpression is None or self.matchExpression == u'':
			# we only need to look at the action...
			if self.respondToActionId == u'' or self.respondToActionId == rpCommand.parentAction.indigoActionId:
				return True
			else:
				return False
				
		matchCriteriaTest = self.substituteCriteriaFormatString(self.criteriaFormatString, responseObj, rpCommand, rpDevice, rpPlugin)
		matchObj = re.match(self.matchExpression, matchCriteriaTest, re.I)
		return (matchObj is not None) and (self.respondToActionId == u'' or self.respondToActionId == rpCommand.parentAction.indigoActionId)
	
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will generate the criteria to test based upon the response and the
	# response definition criteria
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def substituteCriteriaFormatString(self, formatString, responseObj, rpCommand, rpDevice, rpPlugin):
		substitutedCriteria = formatString
		if substitutedCriteria is None:
			return u''
		
		# substitute the response/command object values as those are
		# specific to commands
		if rpCommand is not None:
			substitutedCriteria = substitutedCriteria.replace(u'%cp:name%', rpCommand.commandName)
			substitutedCriteria = substitutedCriteria.replace(u'%cp:payload%', RPFrameworkUtils.to_unicode(rpCommand.commandPayload))
		
		if isinstance(responseObj, (str, unicode)):
			substitutedCriteria = substitutedCriteria.replace("%cp:response%", responseObj)
		
		# substitute the standard RPFramework substitutions
		substitutedCriteria = rpPlugin.substituteIndigoValues(substitutedCriteria, rpDevice, None)
		
		#return the result back to the caller
		return substitutedCriteria
			
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will execute the effects of the response; it is assuming that it is
	# a match (it will not re-match)
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def executeEffects(self, responseObj, rpCommand, rpDevice, rpPlugin):
		for effect in self.matchResultEffects:
			# first we need to determine if this effect should be executed (based upon a condition; by default all
			# effects will be executed!)
			if effect.updateExecCondition != None and effect.updateExecCondition != u'':
				# this should eval to a boolean value
				if eval(rpPlugin.substituteIndigoValues(effect.updateExecCondition, rpDevice, dict())) == False:
					rpPlugin.logDebugMessage(u'Execute condition failed for response, skipping execution for effect: ' + effect.effectType, RPFrameworkPlugin.DEBUGLEVEL_HIGH)
					continue
		
			# processing for this effect is dependent upon the type
			try:
				if effect.effectType == RESPONSE_EFFECT_UPDATESTATE:
					# this effect should update a device state (param) with a value as formated
					newStateValueString = self.substituteCriteriaFormatString(effect.updateValueFormatString, responseObj, rpCommand, rpDevice, rpPlugin)
					if effect.evalUpdateValue == True:
						newStateValue = eval(newStateValueString)
					else:
						newStateValue = newStateValueString
						
					# the effect may have a UI value set... if not leave at an empty string so that
					# we don't attempt to update it
					newStateUIValue = u''
					if effect.updateValueFormatExString != u"":
						newStateUIValueString = self.substituteCriteriaFormatString(effect.updateValueFormatExString, responseObj, rpCommand, rpDevice, rpPlugin)
						if effect.evalUpdateValue == True:
							newStateUIValue = eval(newStateUIValueString)
						else:
							newStateUIValue = newStateUIValueString 
				
					# update the state...
					if newStateUIValue == u'':
						rpPlugin.logDebugMessage(u'Effect execution: Update state "' + effect.updateParam + u'" to "' + RPFrameworkUtils.to_unicode(newStateValue) + u'"', RPFrameworkPlugin.DEBUGLEVEL_MED)
						rpDevice.indigoDevice.updateStateOnServer(key=effect.updateParam, value=newStateValue)
					else:
						rpPlugin.logDebugMessage(u'Effect execution: Update state "' + effect.updateParam + '" to "' + RPFrameworkUtils.to_unicode(newStateValue) + u'" with UIValue "' + RPFrameworkUtils.to_unicode(newStateUIValue) + u'"', RPFrameworkPlugin.DEBUGLEVEL_MED)
						rpDevice.indigoDevice.updateStateOnServer(key=effect.updateParam, value=newStateValue, uiValue=newStateUIValue)
				
				elif effect.effectType == RESPONSE_EFFECT_QUEUECOMMAND:
					# this effect will enqueue a new command... the updateParam will define the command name
					# and the updateValueFormat will define the new payload
					queueCommandName = self.substituteCriteriaFormatString(effect.updateParam, responseObj, rpCommand, rpDevice, rpPlugin)

					queueCommandPayloadStr = self.substituteCriteriaFormatString(effect.updateValueFormatString, responseObj, rpCommand, rpDevice, rpPlugin)
					if effect.evalUpdateValue == True:
						queueCommandPayload = eval(queueCommandPayloadStr)
					else:
						queueCommandPayload = queueCommandPayloadStr
				
					rpPlugin.logDebugMessage(u'Effect execution: Queuing command {' + queueCommandName + u'}', RPFrameworkPlugin.DEBUGLEVEL_MED)
					rpDevice.queueDeviceCommand(RPFrameworkCommand.RPFrameworkCommand(queueCommandName, queueCommandPayload))
				
				elif effect.effectType == RESPONSE_EFFECT_CALLBACK:
					# this should kick off a callback to a python call on the device...
					rpPlugin.logDebugMessage(u'Effect execution: Calling function ' + effect.updateParam, RPFrameworkPlugin.DEBUGLEVEL_MED)
					eval(u'rpDevice.' + effect.updateParam + u'(responseObj, rpCommand)')
			except:
				rpPlugin.logErrorMessage(u'Error executing effect for device id ' + RPFrameworkUtils.to_unicode(rpDevice.indigoDevice.id))
				
	
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
# RPFrameworkDeviceResponseEffect
#	Class that defines the effects that a match against the device response will enact;
#	these are things such as updating a device state, firing an event, etc.
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
class RPFrameworkDeviceResponseEffect(object):
	
	#/////////////////////////////////////////////////////////////////////////////////////
	# Class construction and destruction methods
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# Constructor allows passing in the data that makes up the response object
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def __init__(self, effectType, updateParam, updateValueFormatString=u'', updateValueFormatExString=u'', evalUpdateValue=False, updateExecCondition=None):
		self.effectType = effectType
		self.updateParam = updateParam
		self.updateValueFormatString = updateValueFormatString
		self.updateValueFormatExString = updateValueFormatExString
		self.evalUpdateValue = evalUpdateValue
		self.updateExecCondition = updateExecCondition
		
		
#! /usr/bin/env python
# -*- coding: utf-8 -*-
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
# RPFrameworkNonCommChildDevice by RogueProeliator <adam.d.ashe@gmail.com>
# 	Base class for all RogueProeliator's devices which do not actively communicate but
#	rather function to pass commands along to a parent device; examples would be zones indigo
#	a multi-room audio system or zones in an alarm panel
#	
#	THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# 	IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# 	FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# 	AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# 	LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# 	OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# 	SOFTWARE.
#
#	Version 4:
#		Initial release of the device in the framework
#
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////

#/////////////////////////////////////////////////////////////////////////////////////////
# Python imports
#/////////////////////////////////////////////////////////////////////////////////////////
import indigo
import Queue

import RPFrameworkCommand
import RPFrameworkPlugin
import RPFrameworkDevice
import RPFrameworkUtils

#/////////////////////////////////////////////////////////////////////////////////////////
# Constants and configuration variables
#/////////////////////////////////////////////////////////////////////////////////////////


#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
# RPFrameworkNonCommChildDevice
#	Base class for all RogueProeliator's devices which do not actively communicate but
#	rather function to pass commands along to a parent device.
#
#	This function inherits the standard (communicating) device and disables those
#	functions (they should be present since the plugin will call them during the lifecycle
#	of the device)
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
class RPFrameworkNonCommChildDevice(RPFrameworkDevice.RPFrameworkDevice):

	#/////////////////////////////////////////////////////////////////////////////////////
	# Class construction and destruction methods
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# Constructor called once upon plugin class receiving a command to start device
	# communication. The plugin will call other commands when needed, simply zero out the
	# member variables
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def __init__(self, plugin, device):
		super(RPFrameworkNonCommChildDevice, self).__init__(plugin, device)

	#/////////////////////////////////////////////////////////////////////////////////////
	# Disabled communications functions
	#/////////////////////////////////////////////////////////////////////////////////////
	def initiateCommunications(self):
		super(RPFrameworkNonCommChildDevice, self).initiateCommunications(initializeConnect=False)
		
	def terminateCommunications(self):
		pass
		
	#/////////////////////////////////////////////////////////////////////////////////////
	# Queue and command processing methods
	#/////////////////////////////////////////////////////////////////////////////////////	
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# Add new command to queue of the PARENT object... this must be obtained from the
	# plugin...
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def queueDeviceCommand(self, command):
		parentDeviceId = int(self.indigoDevice.pluginProps[self.hostPlugin.getGUIConfigValue(self.indigoDevice.deviceTypeId, RPFrameworkPlugin.GUI_CONFIG_PARENTDEVICEIDPROPERTYNAME, u'')])
		if parentDeviceId in self.hostPlugin.managedDevices:
			self.hostPlugin.managedDevices[parentDeviceId].queueDeviceCommand(command)
		
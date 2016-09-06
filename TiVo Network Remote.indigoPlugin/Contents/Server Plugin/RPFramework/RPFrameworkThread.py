#! /usr/bin/env python
# -*- coding: utf-8 -*-
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
# RPFrameworkThread by RogueProeliator <adam.d.ashe@gmail.com>
# 	Class for all RogueProeliator's device threads; supports cancellation via raising an
#	exception in the thread
#	
#	THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# 	IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# 	FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# 	AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# 	LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# 	OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# 	SOFTWARE.
#
#	Version 8:
#		Initial release of the thread to the framework
#	Version 17:
#		Changed strings to unicode strings
#
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
import ctypes
import inspect
import threading


#/////////////////////////////////////////////////////////////////////////////////////////
# Internal module-level function used to send an exception to a given thread
#/////////////////////////////////////////////////////////////////////////////////////////
def _async_raise(tid, exctype):
	if not inspect.isclass(exctype):
		raise TypeError(u'Only types can be raised (not instances)')
	res = ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(tid), ctypes.py_object(exctype))
	if res == 0:
		raise ValueError(u'Invalid thread ID')
	elif res != 1:
		# if it returns a number greater than one, you're in trouble, 
		# and you should call it again with exc=NULL to revert the effect
		ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, 0)
		raise SystemError(u'PyThreadState_SetAsyncExc failed')
        

#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
# RPFrameworkCommand
#	Class that allows communication of an action request between the plugin device and
#	its processing thread that is executing the actions/requests/communications
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
class RPFrameworkThread(threading.Thread):

	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine returns the ID of the thread, which should be unique to all threads
	# in this package
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def _get_my_tid(self):
		if not self.isAlive():
			raise threading.ThreadError(u'The thread is not active')

		# check to see if we have the ID already retrieved/cached
		if hasattr(self, u'_thread_id'):
			return self._thread_id
        
		# the id is not yet cached to the class... attempt to find it now in the list
		# of active threads
		for tid, tobj in threading._active.items():
			if tobj is self:
				self._thread_id = tid
				return tid
        
		# we could not find the thread's ID
		raise AssertionError(u'Could not determine the thread''s id')
    
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine raises an exception of the given type within the thread's context
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def raise_exc(self, exctype):
		_async_raise(self._get_my_tid(), exctype)

	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine may be called in order to terminate the thread
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def terminateThread(self):
		self.raise_exc(SystemExit)
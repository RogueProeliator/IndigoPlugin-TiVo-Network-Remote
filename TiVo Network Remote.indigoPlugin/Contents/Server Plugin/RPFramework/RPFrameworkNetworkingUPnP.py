#! /usr/bin/env python
# -*- coding: utf-8 -*-
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
# RPFrameworkNetworkingUPnP by RogueProeliator <adam.d.ashe@gmail.com>
# 	Classes that handle various aspects of Universal Plug and Play protocols such as
#	discovery of devices.
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
#		Initial release of the plugin framework
#	Version 17:
#		Added unicode support / proper string conversions
#
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////

#/////////////////////////////////////////////////////////////////////////////////////////
# Python imports
#/////////////////////////////////////////////////////////////////////////////////////////
import socket
import httplib
import StringIO
import RPFrameworkUtils


#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
# SSDPResponse
#	Handles the request (and response) to SSDP queries initiated in order to find Network
#	devices such as Roku boxes
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
class SSDPResponse(object):
	######################################################################################
	# Internal class for creating the socket necessary to send the request
	######################################################################################
	class _FakeSocket(StringIO.StringIO):
		def makefile(self, *args, **kw):
			return self
		
	def __init__(self, response):
		r = httplib.HTTPResponse(self._FakeSocket(response))
		r.begin()
		
		self.location = u''
		self.usn = u''
		self.st = u''
		self.server = u''
		self.cache = u''
		
		if r.getheader("location") is not None:
			self.location = RPFrameworkUtils.to_unicode(r.getheader("location"))
			
		if r.getheader("usn") is not None:
			self.usn = RPFrameworkUtils.to_unicode(r.getheader("usn"))
	
		if r.getheader("st") is not None:
			self.st = RPFrameworkUtils.to_unicode(r.getheader("st"))
	
		if r.getheader("server") is not None:
			self.server = RPFrameworkUtils.to_unicode(r.getheader("server"))
		
		if r.getheader("cache-control") is not None:
			try:
				cacheControlHeader = RPFrameworkUtils.to_unicode(r.getheader("cache-control"))
				cacheControlHeader = cacheControlHeader.split(u'=')[1]
				self.cache = cacheControlHeader
			except:
				pass
		
		self.allHeaders = r.getheaders()
		
	def __repr__(self):
		return u'<SSDPResponse(%(location)s, %(st)s, %(usn)s, %(server)s)>' % (self.__dict__) + RPFrameworkUtils.to_unicode(self.allHeaders) + u'</SSDPResonse>'


#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
# uPnPDiscover
#	Module-level function that executes a uPNP MSEARCH operation to find devices matching
#	a given service
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
def uPnPDiscover(service, timeout=2, retries=1):
    group = ("239.255.255.250", 1900)
    message = "\r\n".join([
        "M-SEARCH * HTTP/1.1",
        "HOST: " + group[0] + ":" + RPFrameworkUtils.to_str(group[1]),
        "MAN: ""ssdp:discover""",
        "ST: " + service,"MX: 3","",""])
    socket.setdefaulttimeout(timeout)
    responses = {}
    for _ in range(retries):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.sendto(message, group)
        while True:
            try:
                response = SSDPResponse(sock.recv(1024))
                responses[response.location] = response
            except socket.timeout:
                break
    return responses.values()
 
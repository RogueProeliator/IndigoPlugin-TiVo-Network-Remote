#!/usr/bin/env python
# -*- coding: utf-8 -*-
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
# TiVo Network Remote Control by RogueProeliator <rp@rogueproeliator.com>
# 	See plugin.py for more plugin details and information
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////

#/////////////////////////////////////////////////////////////////////////////////////////
# Python imports
#/////////////////////////////////////////////////////////////////////////////////////////
import logging
import random
import re
import socket
import OpenSSL
import sys
import time
import simplejson

#/////////////////////////////////////////////////////////////////////////////////////////
# Gloabl variables… used between requests
#/////////////////////////////////////////////////////////////////////////////////////////
body_id = ''
rpc_id = 0
session_id = random.randrange(0x26c000, 0x27dc20)
 

#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
# RpcRequest
#	Handles the configuration / format of a single RPC request to the TiVo in a MindRPC
#	format
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
def RpcRequest(type, monitor=False, **kwargs):
  global rpc_id
  rpc_id += 1
 
  headers = '\r\n'.join((
      'Type: request',
      'RpcId: %d' % rpc_id,
      'SchemaVersion: 7',
      'Content-Type: application/json',
      'RequestType: %s' % type,
      'ResponseCount: %s' % (monitor and 'multiple' or 'single'),
      'BodyId: %s' % body_id,
      'X-ApplicationName: Quicksilver',
      'X-ApplicationVersion: 1.2',
      'X-ApplicationSessionId: 0x%x' % session_id,
      )) + '\r\n'
 
  req_obj = dict(**kwargs)
  req_obj.update({'type': type})
 
  body = json.dumps(req_obj) + '\n'
 
  # The "+ 2" is for the '\r\n' we'll add to the headers next.
  start_line = 'MRPC/2 %d %d' % (len(headers) + 2, len(body))
 
  return '\r\n'.join((start_line, headers, body))
 
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
# TiVoSSLCommunicator
#	Handles the actual communication to a TiVo Premier via the SSL channel to MindRPC
#	service on the TiVo
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
class TiVoSSLCommunicator(object):

	######################################################################################
	# Constructor that sets up the SSL communication channel
	def __init__(self, tivo_addr, tivo_mak):
		self.buf = ''
		self.makAddress = tivo_mak
		self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.ssl_socket = ssl.wrap_socket(self.socket, keyfile='sslClientCertKey.pem', certfile='sslClientCert.pem', cert_reqs=ssl.CERT_NONE)
		self.ssl_socket.connect((tivo_addr, 1413))
		self.Auth()
 
	######################################################################################
	# This routine will read input back from the SSL socket and process it as a JSON
	# return string
	def Read(self):
		start_line = ''
		head_len = None
		body_len = None
		
		while True:
			self.buf += self.ssl_socket.read(16)
			match = re.match(r'MRPC/2 (\d+) (\d+)\r\n', self.buf)
			if match:
				start_line = match.group(0)
				head_len = int(match.group(1))
				body_len = int(match.group(2))
				break
		
		need_len = len(start_line) + head_len + body_len
		while len(self.buf) < need_len:
			self.buf += self.ssl_socket.read(1024)
		buf = self.buf[:need_len]
		self.buf = self.buf[need_len:]
		
		logging.debug('READ %s', buf)
		return json.loads(buf[-1 * body_len:])
 
	######################################################################################
	# This routine will write the given data to the SSL socket
	def Write(self, data):
		logging.debug('SEND %s', data)
		self.ssl_socket.send(data)
 
	######################################################################################
	# This routine attempts to authenticate to the TiVo device, a required step before
	# sending in commands that operate the TiVo
	def Auth(self):
		self.Write(RpcRequest('bodyAuthenticate', credential={
			    'type': 'makCredential',
			    'key': self.makAddress,
			    }
			))
		result = self.Read()
		if result['status'] != 'success':
			raise "TiVo MindRPC interface via SSL failed authentication" 
 
	######################################################################################
	# This routine will attempt to navigate to the requested screen
	def uiNavigate(self, navType, uri):

		req = RpcRequest('uiNavigate', uri='x-tivo:' + navType + ':uuid:%s' % uri, bodyId='-')

		self.Write(req)
 

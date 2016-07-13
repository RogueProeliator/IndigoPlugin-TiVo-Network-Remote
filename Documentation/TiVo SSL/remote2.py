#!/usr/bin/env python
 
import logging
import random
import re
import socket
import ssl
import sys
import time
 
import simplejson
 
tivo_addr = '172.16.1.110'
mak = '0803274988'
 
body_id = ''
rpc_id = 0
session_id = random.randrange(0x26c000, 0x27dc20)
 
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
 
  body = simplejson.dumps(req_obj) + '\n'
 
  # The "+ 2" is for the '\r\n' we'll add to the headers next.
  start_line = 'MRPC/2 %d %d' % (len(headers) + 2, len(body))
 
  return '\r\n'.join((start_line, headers, body))
 
class Remote(object):
  def __init__(self):
    self.buf = ''
    self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.ssl_socket = ssl.wrap_socket(self.socket, keyfile='privkey2.pem', certfile='tivoCert.pem', cert_reqs=ssl.CERT_NONE)
    self.ssl_socket.connect((tivo_addr, 1413))
    self.Auth()
 
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
    return simplejson.loads(buf[-1 * body_len:])
 
  def Write(self, data):
    logging.debug('SEND %s', data)
    self.ssl_socket.send(data)
 
  def Auth(self):
    self.Write(RpcRequest('bodyAuthenticate',
        credential={
            'type': 'makCredential',
            'key': mak,
            }
        ))
    result = self.Read()
    if result['status'] != 'success':
      logging.error('Authentication failed!  Got: %s', result)
      sys.exit(1)
 
  def Key(self, key):
    """Send a key.
 
    Supported:
      Letters 'a' through 'z'.
      Numbers '0' through '1'.
      Named keys:
        actionA, actionB, actionC, actionD, advance, channelDown,
        channelUp, clear, down, enter, forward, guide, info, left, liveTv,
        pause, play, record, replay, reverse, right, select, slow,
        thumbsDown, thumbsUp, tivo, up, zoom
 
    A space is turned into the 'fast forward' button, as that's what the
    TiVo normally expects, where a space is a valid character to be
    entering.
    """
    if key == ' ':
      key = 'forward'
    if key.lower() in 'abcdefghijklmnopqrstuvwxyz':
      req = RpcRequest('keyEventSend', event='ascii', value=ord(key))
    elif key in '0123456789':
      req = RpcRequest('keyEventSend', event='num' + key)
    else:
      req = RpcRequest('keyEventSend', event=key)
 
    self.Write(req)
    result = self.Read()
    if result['type'] != 'success':
      logging.error('Pause failed!  Got: %s', result)
      sys.exit(1)
      
  def uiNavigate(self, uri):
    req = RpcRequest('uiNavigate', uri='x-tivo:hme:uuid:%s' % uri, bodyId='-')
    self.Write(req)
 
if __name__ == '__main__':
  logging.basicConfig(stream=sys.stderr, level=logging.INFO)
  remote = Remote()
  remote.Key('tivo')
  #remote.uiNavigate('35FE011C-3850-2228-FBC5-1B9EDBBE5863') #amazon
#Amazon:             x-tivo:hme:uuid:35FE011C-3850-2228-FBC5-1B9EDBBE5863
#Blockbuster:        x-tivo:hme:uuid:63ED0C3D-D49C-9602-C322-E0A3D3EA5A3D
#Browse Web Videos:  x-tivo:hme:uuid:19452283-D00B-C411-595D-447ABF62F37C
#Browse Web Videos:  x-tivo:hme:uuid:6784571A-016C-8A46-DF2F-FD842D78006F
#Fandango:           x-tivo:hme:uuid:B9DDBECF-BC6D-5E33-388A-4CF840068D79
#Music Choice:       x-tivo:hme:uuid:7FDF1BEB-AF92-B8B6-6269-FAE44C8F887D
#Netflix:            x-tivo:hme:uuid:7edeb291-0db8-487f-b842-6b97bc71ad9a
#One True Media:     x-tivo:hme:uuid:D1AF7BED-325E-5E6E-B087-72381C92D077
#Swivel:             x-tivo:hme:uuid:2BD40EF7-D9D2-3CD4-0130-6C18855CE898
#TiVoCast RSS:       x-tivo:hme:uuid:863cb78f-efdd-4106-b572-51733983dc76
#Youtube:            x-tivo:hme:uuid:9AA364C9-CF8A-1E1D-B50F-CC65C40D4A96
#  for key in 'typed via remote':
#    remote.Key(key)
  #time.sleep(2)
  #remote.Key('pause')
#!/usr/bin/env python
# -*- encoding: utf-8 -*-
#
# Copyright P. Christeas <p_christ@hol.gr> 2008,2009
#
#
# WARNING: This program as such is intended to be used by professional
# programmers who take the whole responsability of assessing all potential
# consequences resulting from its eventual inadequacies and bugs
# End users who are looking for a ready-to-use solution with commercial
# garantees and support are strongly adviced to contract a Free Software
# Service Company
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
###############################################################################
#

import imp
import sys
import os
import glob
import subprocess
import re

from optparse import OptionParser

parser = OptionParser()
parser.add_option("-q", "--quiet",
                  action="store_false", dest="verbose", default=True,
                  help="don't print status messages to stdout")

#parser.add_option("-r", "--onlyver",
                  #action="store_true", dest="onlyver", default=False,
                  #help="Generates the version string and exits.")

parser.add_option("-H", "--host", dest="host", default='',
                  help="use HOST as serving address", metavar="HOST")

parser.add_option("-p", "--port", dest="port", default=8000,
                  help="bind to PORT", metavar="PORT")

#parser.add_option("-m", "--exclude-from",
                  #dest="exclude",
                  #help="Reads the file FROM_LIST and excludes those modules",
                  #metavar = "FROM_LIST")

(options, args) = parser.parse_args()

if not len(args):
	print "Usage: %s <command> [args...]" % 'http-client.py'
	exit(2)

import httplib

from xmlrpclib import *

import httplib
class HTTP11(httplib.HTTP):
	_http_vsn = 11
	_http_vsn_str = 'HTTP/1.1'

class PersistentTransport(Transport):
    """Handles an HTTP transaction to an XML-RPC server, persistently."""

    def __init__(self, use_datetime=0):
        self._use_datetime = use_datetime
	self._http = {}
	print "Using persistent transport"

    def make_connection(self, host):
        # create a HTTP connection object from a host descriptor
	if not self._http.has_key(host):
		host, extra_headers, x509 = self.get_host_info(host)
		self._http[host] = HTTP11(host)
		print "New connection to",host
	return self._http[host]

    def get_host_info(self, host):
	host, extra_headers, x509 = Transport.get_host_info(self,host)
	if extra_headers == None:
		extra_headers = []
		
	extra_headers.append( ( 'Connection', 'keep-alive' ))
	
        return host, extra_headers, x509

    def _parse_response(self, file, sock, response):
        """ read response from input file/socket, and parse it
	    We are persistent, so it is important to only parse
	    the right amount of input
	"""

        p, u = self.getparser()

	while not response.isclosed():
		rdata = response.read(1024)
		if not rdata:
			break
		if self.verbose:
			print "body:", repr(response)
		p.feed(rdata)
		if len(rdata)<1024:
			break

        p.close()
        return u.close()

    def request(self, host, handler, request_body, verbose=0):
        # issue XML-RPC request

        h = self.make_connection(host)
        if verbose:
            h.set_debuglevel(1)

        self.send_request(h, handler, request_body)
        self.send_host(h, host)
        self.send_user_agent(h)
        self.send_content(h, request_body)

	resp = h._conn.getresponse()
	# TODO: except BadStatusLine, e:
	
        errcode, errmsg, headers = resp.status, resp.reason, resp.msg
	

        if errcode != 200:
            raise ProtocolError(
                host + handler,
                errcode, errmsg,
                headers
                )

        self.verbose = verbose

        try:
            sock = h._conn.sock
        except AttributeError:
            sock = None

        return self._parse_response(h.getfile(), sock, resp)


def simple_get(args):
	print "Getting http://%s" % args[0]
	conn = httplib.HTTPConnection(args[0])
	if len(args)>1:
		path = args[1]
	else:
		path = "/index.html"
	conn.request("GET", path )
	r1 = conn.getresponse()
	print "Reponse:",r1.status, r1.reason
	data1 = r1.read()
	print "Body:"
	print data1
	print "End of body\n"
	conn.close()

def multi_get(args):
	print "Getting http://%s" % args[0]
	conn = httplib.HTTPConnection(args[0])
	if len(args)>1:
		paths = args[1:]
	else:
		paths = ["/index.html"]
		
	for path in paths:
		print "getting ", path
		conn.request("GET", path, [], { 'Connection': 'keep-alive' } )
		r1 = conn.getresponse()
		print "Reponse:",r1.status, r1.reason
		data1 = r1.read()
		print "Body:"
		print data1
		print "End of body\n"
	conn.close()

def auth_get(args):
	import base64
	from time import sleep
	print "Getting http://%s" % args[0]
	conn = httplib.HTTPConnection(args[0])
	if len(args)>1:
		paths = args[1:]
	else:
		paths = ["/index.html"]
		
	for path in paths:
		print "getting ", path
		conn.request("GET", path, [], { 'Connection': 'keep-alive' } )
		try:
			r1 = conn.getresponse()
		except httplib.BadStatusLine, bsl:
			print "Bad status line:", bsl.line
			break
		if r1.status == 401: # and r1.headers:
			if 'www-authenticate' in r1.msg:
				(atype,realm) = r1.msg.getheader('www-authenticate').split(' ')
				data1 = r1.read()
				print r1.version,r1.isclosed(), r1.will_close
				print "Want to do auth %s for realm %s" % (atype, realm)
				if atype == 'Basic' :
					auths = base64.encodestring('user' + ':' + 'password')
					if auths[-1] == "\n":
						auths = auths[:-1]
					connhs = { 'Connection': 'keep-alive',
						'Authorization': 'Basic '+ auths }
					sleep(1)
					conn.request("GET",path,[], connhs)
					r1 = conn.getresponse()
				else:
					raise Exception("Unknown auth type %s" %atype)
			else:
				print "Got 401, cannot auth"
				raise Exception('No auth')
			
		print "Reponse:",r1.status, r1.reason
		data1 = r1.read()
		print "Body:"
		print data1
		print "End of body\n"
	conn.close()

class HTTPSConnection(httplib.HTTPSConnection):
	certs_file = None
        def connect(self):
            "Connect to a host on a given (SSL) port. check the certificate"
	    import socket, ssl

	    if HTTPSConnection.certs_file:
		ca_certs = HTTPSConnection.certs_file
		cert_reqs = ssl.CERT_REQUIRED
	    else:
		ca_certs = None
		cert_reqs = ssl.CERT_NONE
            sock = socket.create_connection((self.host, self.port), self.timeout)
            self.sock = ssl.wrap_socket(sock, self.key_file, self.cert_file,
				ca_certs=ca_certs,
				cert_reqs=cert_reqs)
	

	def getpeercert(self):
		import ssl
		cert = None
		if self.sock:
			cert =  self.sock.getpeercert()
		else:
			cert = ssl.get_server_certificate((self.host,self.port),
				ssl_version=ssl.PROTOCOL_SSLv23 )
			lf = (len(ssl.PEM_FOOTER)+1)
			if cert[0-lf] != '\n':
				cert = cert[:0-lf]+'\n'+cert[0-lf:]
			print lf, cert[0-lf]
		
		return cert

def auth_get_s(args):
	import base64,ssl
	print "Getting https://%s" % args[0]
	conn = HTTPSConnection(args[0],strict=True)
	try:
		conn.connect()
	except ssl.SSLError,e:
		print "SSL Error: ",e.errno, e.strerror, e.args
		print conn.getpeercert()
		return
	if len(args)>1:
		paths = args[1:]
	else:
		paths = ["/index.html"]
		
	for path in paths:
		print "getting ", path
		conn.request("GET", path, [], { 'Connection': 'keep-alive' } )
		try:
			r1 = conn.getresponse()
		except httplib.BadStatusLine, bsl:
			print "Bad status line:", bsl.line
			break
		if r1.status == 401: # and r1.headers:
			if 'www-authenticate' in r1.msg:
				(atype,realm) = r1.msg.getheader('www-authenticate').split(' ')
				data1 = r1.read()
				print r1.version,r1.isclosed(), r1.will_close
				print "Want to do auth %s for realm %s" % (atype, realm)
				if atype == 'Basic' :
					auths = base64.encodestring('user' + ':' + 'password')
					if auths[-1] == "\n":
						auths = auths[:-1]
					connhs = { 'Connection': 'keep-alive',
						'Authorization': 'Basic '+ auths }
					conn.request("GET",path,[], connhs)
					r1 = conn.getresponse()
				else:
					raise Exception("Unknown auth type %s" %atype)
			else:
				print "Got 401, cannot auth"
				raise Exception('No auth')
			
		print "Reponse:",r1.status, r1.reason
		data1 = r1.read()
		print "Body:"
		print data1
		print "End of body\n"
	conn.close()


def rpc_about(args):
	try:
		srv = ServerProxy(args[0]+'/xmlrpc/common');
		s = srv.about()
		print s
	except Fault, f:
		print "Fault:",f.faultCode
		print f.faultString
from time import sleep

def rpc_about_m(args):
	""" Multiple calls to about() """
	
	try:
		num = int(args[1])
		path = "http://" + args[0]
		srv = ServerProxy(path+'/xmlrpc/common',
			transport=PersistentTransport(),
			verbose=1)
		for i in range(num):
			print srv
			s = srv.about()
			print "Try #%d" %i
			if i == 0:
				print s
			print "OK #%d" %i
			sleep(10)
	except Fault, f:
		print "Fault:",f.faultCode
		print f.faultString

def rpc_listdb(args):
	import xmlrpclib
	
	try:
		srv = ServerProxy(args[0]+'/xmlrpc/db');
		li = srv.list()
		print "List db:",li
	except Fault, f:
		print "Fault:",f.faultCode
		print f.faultString

def rpc_generic(args):
	import xmlrpclib

	try:
		srv = ServerProxy(args[0]+'/xmlrpc/'+args[1])
		method = getattr(srv,args[2])
		li = method(*args[3:])
		print "Result:",li
	except Fault, f:
		print "Fault:",f.faultCode
		print f.faultString

def rpc_login(args):
	import xmlrpclib
	import getpass
	try:
		srv = ServerProxy(args[0]+'/xmlrpc/common')
		passwd =getpass.getpass("Password for %s@%s: " %(args[2],args[1]) )
		if srv.login(args[1], args[2],passwd):
			print "Login OK"
		else:
			print "Login Failed"
	except Fault, f:
		print "Fault:",f.faultCode
		print f.faultString

cmd = args[0]
args = args[1:]
commands = { 'get' : simple_get , 'mget' : multi_get, 'aget': auth_get,
	'agets': auth_get_s,
	'rabout': rpc_about, 'listdb': rpc_listdb, 'login': rpc_login,
	'rpc': rpc_generic, 'rabout_m': rpc_about_m }

if not commands.has_key(cmd):
	print "No such command: %s" % cmd
	exit(1)

funct = commands[cmd]
if not funct(args):
	exit(1)

#eof

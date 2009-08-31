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

parser.add_option("-r", "--onlyver",
                  action="store_true", dest="onlyver", default=False,
                  help="Generates the version string and exits.")

parser.add_option("-H", "--host", dest="host", default='',
                  help="use HOST as serving address", metavar="HOST")

parser.add_option("-p", "--port", dest="port", default=8000,
                  help="bind to PORT", metavar="PORT")

parser.add_option("-x", "--exclude-from",
                  dest="exclude",
                  help="Reads the file FROM_LIST and excludes those modules",
                  metavar = "FROM_LIST")

(options, args) = parser.parse_args()

from BaseHTTPServer import *

from SimpleHTTPServer import SimpleHTTPRequestHandler
class HTTPHandler(SimpleHTTPRequestHandler):
	def __init__(self,request, client_address, server):
		SimpleHTTPRequestHandler.__init__(self,request,client_address,server)
		print "Handler for %s inited" % str(client_address)
		self.protocol_version = 'HTTP/1.1'
	
	def handle(self):
		""" Classes here should NOT handle inside their constructor
		"""
		pass
	
	def finish(self):
		pass
	
	def setup(self):
		pass

class HTTPHandler2(HTTPHandler):
    def do_POST(self):
        """Serve a GET request."""
        f = self.send_head()
        try:
            # Get arguments by reading body of request.
            # We read this in chunks to avoid straining
            # socket.read(); around the 10 or 15Mb mark, some platforms
            # begin to have problems (bug #792570).
            max_chunk_size = 10*1024*1024
            size_remaining = int(self.headers["content-length"])
            L = []
            while size_remaining:
                chunk_size = min(size_remaining, max_chunk_size)
                L.append(self.rfile.read(chunk_size))
                size_remaining -= len(L[-1])
            data = ''.join(L)

        except Exception, e: # This should only happen if the module is buggy
            # internal error, report as HTTP server error
	    print "Error:",e
            self.send_error(500)
	    return

        if f:
            self.copyfile(f, self.wfile)
            f.close()

class HTTPDir:
	""" A dispatcher class, like a virtual folder in httpd
	"""
	def __init__(self,path,handler, auth_provider = None):
		self.path = path
		self.handler = handler
		self.auth_provider = auth_provider
		
	def matches(self, request):
		""" Test if some request matches us. If so, return
		    the matched path. """
		if request.startswith(self.path):
			return self.path
		return False
	
class AuthRequiredExc(Exception):
	def __init__(self,atype,realm):
		Exception.__init__(self)
		self.atype = atype
		self.realm = realm
		
class AuthRejectedExc(Exception):
	pass

class AuthProvider:
	def __init__(self,realm):
		self.realm = realm

	def setupAuth(self, multi,handler):
		""" Attach an AuthProxy object to handler
		"""
		pass

	def authenticate(self, user, passwd, client_address):
		if user == 'user' and passwd == 'password':
			return (user, passwd)
		else:
			return False

class BasicAuthProvider(AuthProvider):
	def setupAuth(self, multi, handler):
		if not multi.sec_realms.has_key(self.realm):
			multi.sec_realms[self.realm] = BasicAuthProxy(self)
			

class AuthProxy:
	""" This class will hold authentication information for a handler,
	    i.e. a connection
	"""
	def __init__(self, provider):
		self.provider = provider

	def checkRequest(self,handler,path = '/'):
		""" Check if we are allowed to process that request
		"""
		pass

import base64
class BasicAuthProxy(AuthProxy):
	""" Require basic authentication..
	"""
	def __init__(self,provider):
		AuthProxy.__init__(self,provider)
		self.auth_creds = None
		self.auth_tries = 0

	def checkRequest(self,handler,path = '/'):
		if self.auth_creds:
			return True
		auth_str = handler.headers.get('Authorization',False)
		if auth_str and auth_str.startswith('Basic '):
			auth_str=auth_str[len('Basic '):]
			(user,passwd) = base64.decodestring(auth_str).split(':')
			print "Found user=\"%s\", passwd=\"%s\"" %(user,passwd)
			self.auth_creds = self.provider.authenticate(user,passwd,handler.client_address)
			if self.auth_creds:
				return True
		if self.auth_tries > 5:
			raise AuthRejectedExc("Authorization failed.")
		self.auth_tries += 1
		raise AuthRequiredExc(atype = 'Basic', realm=self.provider.realm)
	
class noconnection:
	""" a class to use instead of the real connection
	"""
	def makefile(self, mode, bufsize):
		return None

import SocketServer
def _quote_html(html):
    return html.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class MultiHTTPHandler(BaseHTTPRequestHandler):
    """ this is a multiple handler, that will dispatch each request
        to a nested handler, iff it matches
	
	The handler will also have *one* dict of authentication proxies,
	groupped by their realm.
    """

    protocol_version = "HTTP/1.1"
    
    def __init__(self, request, client_address, server):
	self.in_handlers = {}
	self.sec_realms = {}
	print "MultiHttpHandler init for %s" %(str(client_address))
	SocketServer.StreamRequestHandler.__init__(self,request,client_address,server)

    def _handle_one_foreign(self,fore, path, auth_provider):
        """ This method overrides the handle_one_request for *children*
            handlers. It is required, since the first line should not be
	    read again..

        """
        fore.raw_requestline = "%s %s %s\n" % (self.command, path, self.version)
        if not fore.parse_request(): # An error code has been sent, just exit
            return
	self.request_version = fore.request_version
	if auth_provider and auth_provider.realm:
		try:
			self.sec_realms[auth_provider.realm].checkRequest(fore,path)
		except AuthRequiredExc,ae:
			if self.request_version != 'HTTP/1.1':
				self.log_error("Cannot require auth at %s",self.request_version)
				self.send_error(401)
				return
			self.send_response(401,'Authorization required')
			self.send_header('WWW-Authenticate','%s realm="%s"' % (ae.atype,ae.realm))
			self.send_header('Content-Type','text/html')
			self.send_header('Content-Length','0')
			self.end_headers()
			#self.wfile.write("\r\n")
			return
		except AuthRejectedExc,e:
			self.send_error(401,e.args[0])
			self.close_connection = 1
			return
        mname = 'do_' + fore.command
        if not hasattr(fore, mname):
            fore.send_error(501, "Unsupported method (%r)" % fore.command)
            return
        method = getattr(fore, mname)
        method()
	if fore.close_connection:
		# print "Closing connection because of handler"
		self.close_connection = fore.close_connection

    def parse_rawline(self):
        """Parse a request (internal).

        The request should be stored in self.raw_requestline; the results
        are in self.command, self.path, self.request_version and
        self.headers.

        Return True for success, False for failure; on failure, an
        error is sent back.

        """
        self.command = None  # set in case of error on the first line
        self.request_version = version = self.default_request_version
        self.close_connection = 1
        requestline = self.raw_requestline
        if requestline[-2:] == '\r\n':
            requestline = requestline[:-2]
        elif requestline[-1:] == '\n':
            requestline = requestline[:-1]
        self.requestline = requestline
        words = requestline.split()
        if len(words) == 3:
            [command, path, version] = words
            if version[:5] != 'HTTP/':
                self.send_error(400, "Bad request version (%r)" % version)
                return False
            try:
                base_version_number = version.split('/', 1)[1]
                version_number = base_version_number.split(".")
                # RFC 2145 section 3.1 says there can be only one "." and
                #   - major and minor numbers MUST be treated as
                #      separate integers;
                #   - HTTP/2.4 is a lower version than HTTP/2.13, which in
                #      turn is lower than HTTP/12.3;
                #   - Leading zeros MUST be ignored by recipients.
                if len(version_number) != 2:
                    raise ValueError
                version_number = int(version_number[0]), int(version_number[1])
            except (ValueError, IndexError):
                self.send_error(400, "Bad request version (%r)" % version)
                return False
            if version_number >= (1, 1):
                self.close_connection = 0
            if version_number >= (2, 0):
                self.send_error(505,
                          "Invalid HTTP Version (%s)" % base_version_number)
                return False
        elif len(words) == 2:
            [command, path] = words
            self.close_connection = 1
            if command != 'GET':
                self.send_error(400,
                                "Bad HTTP/0.9 request type (%r)" % command)
                return False
        elif not words:
            return False
        else:
            self.send_error(400, "Bad request syntax (%r)" % requestline)
            return False
	self.request_version = version
	self.command, self.path, self.version = command, path, version
	return True

    def handle_one_request(self):
        """Handle a single HTTP request.
	   Dispatch to the correct handler.
        """
        self.raw_requestline = self.rfile.readline()
	if not self.raw_requestline:
		self.close_connection = 1
		print "no requestline"
		return
	if not self.parse_rawline():
		self.log_message("Could not parse rawline.")
		return
        # self.parse_request(): # Do NOT parse here. the first line should be the only 
	for vdir in self.server.vdirs:
		p = vdir.matches(self.path)
		if p == False:
			continue
		npath = self.path[len(p):]
		if not npath.startswith('/'):
			npath = '/' + npath

		if not self.in_handlers.has_key(p):
			self.in_handlers[p] = vdir.handler(noconnection(),self.client_address,self.server)
			if vdir.auth_provider:
				vdir.auth_provider.setupAuth(self, self.in_handlers[p])
		hnd = self.in_handlers[p]
		hnd.rfile = self.rfile
		hnd.wfile = self.wfile
		self.rlpath = self.raw_requestline
		self._handle_one_foreign(hnd,npath, vdir.auth_provider)
		#print "Handled, closing = ", self.close_connection
		return
	# if no match:
        self.send_error(404, "Path not found: %s" % self.path)
        return

    def send_error2(self, code, message=None):
        import socket
	print "Sending error",code
	BaseHTTPRequestHandler.send_error(self,code,message)
	print "after send"
	self.wfile.flush()
	print "pending:", self.connection.pending(), self.connection._makefile_refs
	self.connection.shutdown(socket.SHUT_RDWR)

    def send_error(self, code, message=None):
        try:
            short, long = self.responses[code]
        except KeyError:
            short, long = '???', '???'
        if message is None:
            message = short
        explain = long
        self.log_error("code %d, message %s", code, message)
        # using _quote_html to prevent Cross Site Scripting attacks (see bug #1100201)
        content = (self.error_message_format %
                   {'code': code, 'message': _quote_html(message), 'explain': explain})
        self.send_response(code, message)
        self.send_header("Content-Type", self.error_content_type)
        self.send_header('Connection', 'close')
	self.send_header('Content-Length', len(content) or 0)
        self.end_headers()
        if self.command != 'HEAD' and code >= 200 and code not in (204, 304):
            self.wfile.write(content)


class SecureMultiHTTPHandler(MultiHTTPHandler):
    def setup(self):
	import ssl
        self.connection = ssl.wrap_socket(self.request,
				server_side=True,
				certfile="server.cert",
				keyfile="server.key",
				ssl_version=ssl.PROTOCOL_SSLv23)
        self.rfile = self.connection.makefile('rb', self.rbufsize)
        self.wfile = self.connection.makefile('wb', self.wbufsize)
	self.log_message("Secure %s connection from %s",self.connection.cipher(),self.client_address)

import threading
class ConnThreadingMixIn:
    """Mix-in class to handle each _connection_ in a new thread.
    
	This is necessary for persistent connections, where multiple
	requests should be handled synchronously at each connection, but
	multiple connections can run in parallel.
	"""

    # Decides how threads will act upon termination of the
    # main process
    daemon_threads = False

    def _handle_request_noblock(self):
        """Start a new thread to process the request."""
        t = threading.Thread(target = self._handle_request2)
	print "request came, handling in new thread",t
        if self.daemon_threads:
            t.setDaemon (1)
        t.start()
	
    def _handle_request2(self):
        """Handle one request, without blocking.

        I assume that select.select has returned that the socket is
        readable before this function was called, so there should be
        no risk of blocking in get_request().
        """
        try:
            request, client_address = self.get_request()
        except socket.error:
            return
        if self.verify_request(request, client_address):
            try:
                self.process_request(request, client_address)
            except:
                self.handle_error(request, client_address)
                self.close_request(request)


class TServer(ConnThreadingMixIn,HTTPServer): pass

def server_run(options):
	httpd = TServer((options.host,options.port),SecureMultiHTTPHandler )
	httpd.vdirs =[ HTTPDir('/dir/',HTTPHandler), HTTPDir('/xmlrpc/',HTTPHandler2),
			HTTPDir('/dirs/',HTTPHandler,BasicAuthProvider('/'))]
	httpd.serve_forever()

server_run(options)

#eof
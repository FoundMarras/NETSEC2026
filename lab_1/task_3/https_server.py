from http.server import BaseHTTPRequestHandler, HTTPSServer, HTTPServer
from http.cookies import SimpleCookie, CookieError
import ssl
import threading
from urllib.parse import unquote
import re
import json
import secrets

class HTTPSServer_RequestHandler(BaseHTTPRequestHandler):
    users = {}

    def send_response_status(self,staus):
        self.send_response(staus)
        self.send_header("Content-Length","0")
        self.end_headers()


    def do_GET(self):

        if self.path == "/":
            self.send_response_status(200)
            return
        elif self.path == "/whoami":
            cert = self.connection.getpeercert()
            cn = None
            for rdn in cert["subject"]:
                for key,value in rdn:
                    if key == "commonName":
                        cn = value

            body = cn.encode("utf-8")
            self.send_response(200)
            self.send_header('Content-type','application/json')
            self.send_header('Content-Length',str(len(body)))
            self.end_headers()
            
            self.wfile.write(body)
            return
        elif self.path != "/me":
            self.send_response_status(404)
            return

        try: 
            cookie = SimpleCookie(self.headers.get('Cookie'))
        except CookieError:
            self.send_response_status(401)
            return

        if "session" not in cookie:
            self.send_response_status(401)
            return

        token = cookie["session"].value
        user = type(self).users.get(token)

        body = json.dumps({"user": user}).encode("utf-8")
        self.send_response(200)
        self.send_header('Content-type','application/json')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
       
        self.wfile.write(body)
        return

    def do_POST(self):

        if(self.path != "/login"):
            self.send_response_status(404)
            return

        if self.headers.get("Content-Type","") != "application/json":
            self.send_response_status(415)
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self.send_response_status(400)
            return

        if not isinstance(data,dict) or not isinstance(data.get("user"),str):
            self.send_response_status(400)
            return
        
        if data.get("password") != "netsec" :
            self.send_response_status(401)
            return

        token = secrets.token_hex()
        type(self).users[token] = data["user"]

        cookie = SimpleCookie()
        cookie["session"] = token
        cookie["session"]["secure"] = True
        cookie["session"]["httponly"] = True
        cookie["session"]["path"] = "/"


        self.send_response(200)
        self.send_header('Content-type','application/json')
        self.send_header('Content-Length','0')
        self.send_header('Set-Cookie',cookie["session"].OutputString())
        self.end_headers()
        return

class mTLSServer_RequestHandler(BaseHTTPRequestHandler):

    def send_response_status(self,staus):
        self.send_response(staus)
        self.send_header("Content-Length","0")
        self.end_headers()


    def do_GET(self):

        if self.path != "/whoami":
            self.send_response_status(404)
            return
        
        cert = self.connection.getpeercert()
        cn = None
        for rdn in cert["subject"]:
            for key,value in rdn:
                if key == "commonName":
                    cn = value

        body = cn.encode("utf-8")
        self.send_response(200)
        self.send_header('Content-type','application/json')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        
        self.wfile.write(body)
        return
        

def run():
    print('Avvio dei server...')

    login_server = HTTPSServer(('',8443),HTTPSServer_RequestHandler,certfile="server.crt",keyfile="server.key")

    mtls_server = HTTPServer(('',8444),mTLSServer_RequestHandler)

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile="server.crt",keyfile="server.key")
    context.load_verify_locations(cafile="ca.crt")
    context.verify_mode = ssl.CERT_REQUIRED

    mtls_server.socket = context.wrap_socket(mtls_server.socket, server_side=True)

    threading.Thread(target=login_server.serve_forever, daemon=True).start()
    print('Server in esecuzione...')
    mtls_server.serve_forever()

run()
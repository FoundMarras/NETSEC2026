from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import unquote
import re
import json

class testHTTPServer_RequestHandler(BaseHTTPRequestHandler):
    notes = {}
    id = 0

    def do_GET(self):
        message = ""

        if self.path == "/":
            self.send_response(200)
        elif re.match(r'^/echo\?msg=',self.path):
            self.send_response(200)
            message = "{\"msg\":\"" + unquote(self.path.partition("msg=")[2]) + "\"}"
        elif re.match(r'^/notes/',self.path):

            if not self.path.partition("/notes/")[2].isdigit():
                self.send_response(404)
                self.send_header('Content-Length','0')
                self.end_headers()
                return

            int_id = int(self.path.partition("/notes/")[2])
            if int_id in type(self).notes:
                self.send_response(200)
                result = {"id": int_id, **type(self).notes[int_id]}
                message = json.dumps(result)
            else:
                self.send_response(404)
        else:
            self.send_response(404)
        
        self.send_header('Content-type','application/json')
        self.end_headers()
       
        self.wfile.write(bytes(message, "utf8"))
        return

    def do_POST(self):
        message = ""
        
        if self.path == "/notes":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)

            if self.headers.get("Content-Type","") != "application/json":
                self.send_response(415)
                self.send_header('Content-Length','0')
                self.end_headers()
                return

            try: 
                data = json.loads(body)
            except json.JSONDecodeError:
                self.send_response(400)
                self.send_header('Content-Length','0')
                self.end_headers()
                return

            if not isinstance(data,dict) or not isinstance(data.get("text"),str):
                self.send_response(400)
                self.send_header('Content-Length','0')
                self.end_headers()
                return

            type(self).id += 1
            type(self).notes[type(self).id] = data
            message = json.dumps({"id": type(self).id})
            self.send_response(201)
        else:
            self.send_response(404)
        
        self.send_header('Content-type','application/json')
        self.end_headers()
        
        self.wfile.write(bytes(message, "utf8"))    
        return

    def do_DELETE(self):
        message = ""

        if re.match(r'^/notes/',self.path):

            if not self.path.partition("/notes/")[2].isdigit():
                self.send_response(404)
                self.send_header('Content-Length','0')
                self.end_headers()
                return

            int_id = int(self.path.partition("/notes/")[2])
            if int_id in type(self).notes:
                self.send_response(204)
                del type(self).notes[int_id]
            else:
                self.send_response(404)

        self.send_header('Content-type','application/json')
        self.end_headers()
        return

    def method_not_allowed (self):
        self.send_response(405)
        self.send_header('Allowed','GET,POST,DELETE')
        self.send_header('Content-Length','0')
        self.end_headers()


    def __getattr__(self, name):
        if name.startswith("do_"):
            return self.method_not_allowed
        raise AttributeError(name)

def run():
    print('Avvio del server...')
    server_address = ('', 8080)
    httpd = HTTPServer(server_address, testHTTPServer_RequestHandler)
    print('Server in esecuzione...')
    httpd.serve_forever()

run()
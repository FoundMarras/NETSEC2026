import argparse
import asyncio
import json
import logging
from typing import Dict, Optional

from aioquic.asyncio import QuicConnectionProtocol, serve  
from aioquic.h3.connection import H3_ALPN, H3Connection    
from aioquic.h3.events import DataReceived, HeadersReceived, H3Event
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import HandshakeCompleted, QuicEvent
from hashlib import sha256

import threading
from http.server import BaseHTTPRequestHandler, HTTPSServer

#ALPN gives only the short version name "h3", so we map it the extended version name
ALPN_TO_VERSION = {"h3":"HTTP/3"}

LOG = logging.getLogger("h3server")

#CLASSIC HTTPS SERVER, port 4433/TCP

class TCPHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        body = b""

        if self.path == "/":
            body = b"hello from https over tcp\n"
            self.send_response(200)
            self.send_header("Content-Type","text/plain")
            self.send_header("Content-Length",str(len(body)))
            self.send_header("Alt-Svc", 'h3=":4433"')
            self.end_headers()
        elif self.path == "/proto":
            body = (f"{self.request_version}\n").encode()
            self.send_response(200)
            self.send_header("Content-Type","text/plain")
            self.send_header("Content-Length",str(len(body)))
            self.end_headers()
        
        self.wfile.write(body)

def start_tcp_server(certfile, keyfile):
    httpd = HTTPSServer(("0.0.0.0",4433), TCPHandler, certfile=certfile, keyfile=keyfile)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()


#HTTP/3 SERVER, port 4433, UDP

#One istance of this class is created for each client connection
class Http3ServerProtocol(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        #HTTP/3 layer, created only after the handshake
        self._http: Optional[H3Connection] = None
        # ALPN protocol chosen during the handshake
        self._alpn: Optional[str] = None
        #One QUIC connectionn carries many requests, one per stream, so we kept the stream stat in two dicts keyed by stream_id
        #_bodies: stores the body of each request, which can arrive split into several pieces on its stream
        self._bodies: Dict[int, bytearray] = {}
        #_req_meta: stores method and path of each request, because the body pieces that arrive later don't contain them
        self._req_meta: Dict[int, tuple[str, str]] = {}

    #Called by QuicConnectionProtocol for every QUIC event
    def quic_event_received(self, event: QuicEvent) -> None:

        #Handshake done and client chose HTTP/3
        if isinstance(event, HandshakeCompleted) and event.alpn_protocol in H3_ALPN:
            self._alpn = event.alpn_protocol
            #QUIC event only carry raw stream bytes, H3Connection parses them into HTTP/3 events
            self._http = H3Connection(self._quic)

        if self._http is not None:
            for h3_event in self._http.handle_event(event):
                self.handle_h3_event(h3_event)

    def handle_h3_event(self, event: H3Event) -> None:
        # Handle the Headers
        # read method and path and save them for this stream
        # if the method carries a body, create a buffer otherwise responde
        if isinstance(event, HeadersReceived):
            headers = {k.lower(): v for k, v in event.headers}
            method = headers.get(b":method", b"").decode()
            path = headers.get(b":path", b"/").decode()
            sid = event.stream_id

            LOG.info("Headers on stream %d: %s %s", sid, method, path)
            self._req_meta[sid] = (method, path)

            if method in ("POST", "PUT", "PATCH"):
                self._bodies[sid] = bytearray()
                if event.stream_ended:
                    payload = bytes(self._bodies.pop(sid))
                    self._respond(sid, method, path, payload)
                    self._req_meta.pop(sid, None)
            else:
                
                self._respond(sid, method, path, body=b"")
                self._req_meta.pop(sid, None)
        #Handle the body
        #append each piece to its stream's buffer and, when the last piece arrives, responde and remove the stream's state
        elif isinstance(event, DataReceived):
            sid = event.stream_id

            if sid not in self._bodies:
                return

            self._bodies[sid].extend(event.data)

            if event.stream_ended:
                method, path = self._req_meta.get(sid, ("", "/"))
                payload = bytes(self._bodies.pop(sid, bytearray()))
                self._respond(sid, method, path, payload)
                self._req_meta.pop(sid, None)

    # Build and send an HTTP/3 response on a stream
    def _respond(self, stream_id: int, method: Optional[str], path: Optional[str], body: bytes) -> None:
        status = b"200"
        content_type = b"text/plain"

        version = ALPN_TO_VERSION.get(self._alpn, "unknown")

        # Routing on method and path
        if method == "GET" and path == "/":
            payload = b"hello from aioquic h3 \n"
        elif method == "GET" and path =="/proto":
            # send back the http version used
            payload = (f"{version}\n").encode()
        elif method == "POST" and path == "/echo":
            try:
                obj = json.loads(body.decode() or "{}")
                payload = (json.dumps(obj, indent=2) + "\n").encode()
                content_type = b"application/json"
            except Exception:
                payload = body or b"(empty)\n"
                content_type = b"application/octet-stream"
        elif method == "POST" and path =="/hash":
            # sha 256 of the complete body, as a hexadecimal string
            payload = sha256(body).hexdigest().encode()
        else:
            payload = b"ok\n"

        headers = [
            (b":status", status),
            (b"content-type", content_type),
            (b"alt-svc", b'h3=":4433"; ma=3600'),
        ]

        self._http.send_headers(stream_id, headers)
        self._http.send_data(stream_id, payload, end_stream=True)
        LOG.info("Responded on stream %d (%s bytes)", stream_id, len(payload))

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=4433)
    parser.add_argument("--certificate", default="cert.pem")
    parser.add_argument("--private-key", dest="private_key", default="key.pem")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    start_tcp_server(args.certificate,args.private_key)

    # QUIC/TLS configuration
    config = QuicConfiguration(
        is_client=False,
        alpn_protocols=H3_ALPN,
    )
    config.load_cert_chain(args.certificate, args.private_key)

    #Start server
    server = await serve(
        host=args.host,
        port=args.port,
        configuration=config,
        create_protocol=Http3ServerProtocol,
    )

    logging.info("HTTP/3 server listening on %s:%d", args.host, args.port)

    # Keep running until cancelled
    try:
        await asyncio.Future()  # run forever
    except KeyboardInterrupt:
        pass
    finally:
        server.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
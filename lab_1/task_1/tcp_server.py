import re
import socket 
import threading 

bind_ip = "0.0.0.0" 
bind_port = 9001
dates = {}

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM) 
server.bind((bind_ip, bind_port)) 
server.listen(5) 

print(f"[+] Listening on port {bind_ip} : {bind_port}")                            

#client handling thread
def handle_client(client_socket): 
    buffer = b""
    while True:

        request = client_socket.recv(1024) 

        if not request:          # client closed the connection
            break
        buffer += request

        print(f"[+] Recieved: {request}") 

        # process every complete line in the buffer
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            str_command = line.decode("utf-8").rstrip("\r")

            if str_command == 'PING':
                response = "PONG\n"
            elif re.match(r'^ECHO ', str_command):
                response = str_command.removeprefix('ECHO ') + "\n"
            elif re.match(r'^SET (\S+) (.+)$', str_command):
                m = re.fullmatch(r'^SET (\S+) (.+)$', str_command)
                key, value = m.group(1), m.group(2)
                dates[key] = value
                response = "OK\n"
            elif re.match(r'^GET (\S+)$', str_command):
                m = re.fullmatch(r'^GET (\S+)$', str_command)
                key = m.group(1)
                if key in dates:
                    response = str(dates[key]) + "\n"
                else:
                    response = "NOT_FOUND\n"
            else:
                response = "ERR\n"

            client_socket.send(response.encode()) 
    client_socket.close()

while True: 
    client, addr = server.accept() 
    print(f"[+] Accepted connection from: {addr[0]}:{addr[1]}")

    client_handler = threading.Thread(target=handle_client, args=(client,))
    client_handler.start() 
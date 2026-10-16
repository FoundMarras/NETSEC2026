import socket

target_host = "0.0.0.0"
target_port = 9001

#creating socket object
client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#connecting the client
client.connect((target_host, target_port))
#sending data
#client.send("GET / HTTP/1.1\r\nHost: google.com\r\n\r\n".encode())
client.send("ECHO CIAO\n".encode())
#receiving the data 
response = client.recv(4096)
print(response.decode())
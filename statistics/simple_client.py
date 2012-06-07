from socket import socket, AF_INET, SOCK_DGRAM
data = 'UDP Data Content'
port = 9001
hostname = '127.0.0.1'
udp = socket(AF_INET,SOCK_DGRAM)
udp.sendto(data, (hostname, port))

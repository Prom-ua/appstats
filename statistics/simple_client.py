from socket import socket, AF_INET, SOCK_DGRAM
import json


data = dict(NAME='action2', CPU=10, REDIS=10)
encoder = json.JSONEncoder()
data = encoder.encode(data)
port = 9001
hostname = '127.0.0.1'
udp = socket(AF_INET, SOCK_DGRAM)
udp.sendto(data, (hostname, port))

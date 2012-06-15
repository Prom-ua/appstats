# encoding: utf-8

import json
import eventlet
from eventlet.green import socket

from .app import add_data


class UDPServer(object):

    def __init__(self, host=None, port=None):
        self.host = host
        self.port = port

    def handle(self, data, address):
        data = json.loads(data)
        add_data(data)

    def run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        pool = eventlet.GreenPool()
        while True:
            try:
                pool.spawn_n(self.handle, *sock.recvfrom(2 ** 16))
            except (SystemExit, KeyboardInterrupt):
                break

# encoding: utf-8

import json

import eventlet
from eventlet.green import socket

from .app import add_data


class UDPServer(object):

    BUF_SIZE = 2 ** 16
    POOL_SIZE = 1000
    _socket = socket.socket
    _pool = eventlet.GreenPool(size=POOL_SIZE)
    _spawn = _pool.spawn_n

    def __init__(self, host=None, port=None):
        self.host = host
        self.port = port

    def handle(self, data, address):
        data = json.loads(data)
        add_data(data)

    def run(self):
        sock = self._socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        while True:
            try:
                self._spawn(self.handle, *sock.recvfrom(self.BUF_SIZE))
            except (SystemExit, KeyboardInterrupt):
                break

# encoding: utf-8

import json

from statistics import app, day_counter, hour_counter


class UDPServer(object):

    def __init__(self, host=None, port=None):
        self.host = host or app.config['UDP_HOST']
        self.port = port or app.config['UDP_PORT']

    def handle(self, data, address):
        data = json.load(data)
        name = data['NAME']
        hour_counter.incrby(name, "REQUESTS", 1)
        day_counter.incrby(name, "REQUESTS", 1)
        for field in data:
            if field != 'NAME':
                hour_counter.incrby(name, field, int(data[field]))
                day_counter.incrby(name, field, int(data[field]))
        print "Data: %s \n addr: %s" % (data, address)

    def run(self):
        try:
            import eventlet
        except ImportError:
            raise Exception('It seems that you don\'t have the ``eventlet`` package installed, which is required to run '
                               'the udp service.')

        from eventlet.green import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        pool = eventlet.GreenPool()
        while True:
            try:
                pool.spawn_n(self.handle, *sock.recvfrom(2**16))
            except (SystemExit, KeyboardInterrupt):
                break

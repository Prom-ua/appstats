# encoding: utf-8

import json
import requests
import threading
from time import time
from socket import socket, AF_INET, SOCK_DGRAM, error as socket_error
from urlparse import urlparse


class Client(object):
    count_limit = 100
    desired_interval = 600

    def __init__(self, dsn):
        urlparts = urlparse(dsn)
        self.scheme = urlparts.scheme
        if self.scheme == 'udp':
            self.host = urlparts.hostname
            self.port = urlparts.port
        elif self.scheme == 'http':
            self.url = dsn
        else:
            raise Exception("Invalid scheme in dsn.")
        self._acc = {}
        self._last_sent = time()
        self._req_count = 0

    def add_data(self, data):
        lock = threading.Lock()
        with lock:
            for name, counts in data.iteritems():
                if name not in self._acc:
                    self._acc[name] = counts.copy()
                    self._acc[name]['NUMBER'] = 1
                else:
                    for field in counts:
                        if field in self._acc[name]:
                            self._acc[name][field] += counts[field]
                        else:
                            self._acc[name][field] = counts[field]
                    self._acc[name]['NUMBER'] += 1
                self._req_count += 1
            if ((time() - self._last_sent) > self.desired_interval
                or self._req_count > self.count_limit
            ):
                self.send_data()

    def send_data(self):
        if self.scheme == 'udp':
            self._send_udp()
        elif self.scheme == 'http':
            self._send_http()
        self._last_sent = time()
        self._req_count = 0
        self._acc = {}

    def _send_udp(self):
        udp_socket = None
        try:
            udp_socket = socket(AF_INET, SOCK_DGRAM)
            udp_socket.setblocking(False)
            json_data = json.dumps(self._acc)
            udp_socket.sendto(json_data, (self.host, self.port))
        except socket_error:
            pass
        finally:
            # Always close up the socket when we're done
            if udp_socket is not None:
                udp_socket.close()
                udp_socket = None

    def _send_http(self):
        with requests.session() as s:
            headers = {'content-type': 'application/json'}
            s.post(self.url, data=json.dumps(self._acc), headers=headers)

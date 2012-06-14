# encoding: utf-8

from json import JSONEncoder
from httplib import HTTPConnection
from time import time
from socket import socket, AF_INET, SOCK_DGRAM
from urllib import urlencode
from urlparse import urlparse


class Client(object):

    def __init__(self, dsn, fields):
        urlparts = urlparse(dsn)
        self.scheme = urlparts.scheme
        self.host, self.port = urlparts.netloc.split(':')
        self.port = int(self.port)
        self.path = urlparts.path
        self.fields = fields
        self.acc = {}
        self.last_sent = time()
        self.req_count = 0

    def add_data(self, data):
        if data['NAME'] not in self.acc:
            self.acc[data['NAME']] = data.copy()
            self.acc[data['NAME']]['REQUESTS'] = 1
        else:
            acc_data = self.acc[data['NAME']]
            for field in data:
                if field != 'NAME':
                    acc_data[field] += data[field]
            acc_data['REQUESTS'] += 1
        self.req_count += 1
        if (time() - self.last_sent) > 600 or self.req_count > 100:
            self.send_data()
            self.last_sent = time()
            self.req_count = 0
            self.acc = {}

    def send_data(self):
        if self.scheme == 'udp':
            self._send_udp()
        elif self.scheme == 'http':
            self._send_http()
        else:
            raise Exception("Invalid scheme in dsn.")

    def _send_udp(self):
        encoder = JSONEncoder()
        for data in self.acc.values():
            json_data = encoder.encode(data)
            udp = socket(AF_INET, SOCK_DGRAM)
            udp.sendto(json_data, (self.host, self.port))

    def _send_http(self):
        for data in self.acc.values():
            get_params = urlencode(data)
            conn = HTTPConnection(host=self.host, port=self.port)
            conn.request('GET', self.path + '?' + get_params)

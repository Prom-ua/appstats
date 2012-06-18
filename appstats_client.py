# encoding: utf-8

import json
import threading
from time import time
from urlparse import urlparse

import requests


lock = threading.Lock()


class Client(object):

    count_limit = 100
    desired_interval = 600

    def __init__(self, dsn):
        urlparts = urlparse(dsn)
        self.protocol = urlparts.scheme
        self.url = dsn
        self._session = requests.session()
        self._acc = {}
        self._last_sent = time()
        self._req_count = 0

    def add_data(self, data):
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
                or self._req_count >= self.count_limit
            ):
                self.send_data()

    def send_data(self):
        data = json.dumps(self._acc)
        self._send_http(data)
        self._last_sent = time()
        self._req_count = 0
        self._acc = {}

    def _send_http(self, data):
        headers = {'content-type': 'application/json'}
        try:
            self._session.post(self.url, data=data, headers=headers)
        except requests.RequestException:
            pass

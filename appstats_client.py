import json
import logging
import threading
from time import time

from requests import Session, RequestException


log = logging.getLogger(__name__)

lock = threading.Lock()


class AppStatsClient(object):
    limit = 100 # records
    interval = 60 # seconds
    timeout = 1 # timeout in seconds to submit data

    def __init__(self, url, app_id):
        self.url = url
        self.app_id = app_id
        self._acc = {}
        self._last_sent = time()
        self._session = Session(
            headers = {'Content-Type': 'application/json'},
            timeout = self.timeout,
        )

    def add(self, name, counts):
        with lock:
            acc = self._acc.setdefault(name, {'NUMBER': 0})
            acc['NUMBER'] += 1
            for counter in counts:
                acc.setdefault(counter, 0)
                acc[counter] += counts[counter]

            elapsed = time() - self._last_sent
            if elapsed >= self.interval or len(self._acc) >= self.limit:
                self.submit()

    def submit(self):
        data = json.dumps({self.app_id: self._acc})
        try:
            self._session.post(self.url, data=data)
        except RequestException, e:
            log.debug('Error during data submission: %s' % e)
        else:
            log.debug('Successfully submitted app stats')
        finally:
            self._last_sent = time()
            self._acc = {}

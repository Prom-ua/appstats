# encoding: utf-8

import datetime
from time import time
from calendar import timegm


class RollingCounter(object):
    """
    The rolling counter, which stores data only
    for the specified time interval.
    """

    last_val_key_format = '%(prefix)s,%(name)s,%(interval)s,%(part)s,last_val,%(field)s'
    updated_key_format = '%(prefix)s,%(name)s,%(interval)s,%(part)s,updated,%(field)s'
    key_format = '%(prefix)s,%(name)s,%(interval)s,%(part)s,%(field)s'

    def __init__(self, db, fields, redis_prefix, interval=3600, part=60):
        self.db = db
        self.prefix = redis_prefix
        self.interval = interval
        self.part = part
        self.fields = fields

    def _make_key(self, key_format, **kwargs):
        kwargs.update(prefix=self.prefix, interval=self.interval,
                      part=self.part)
        return key_format % kwargs

    def _get_names(self):
        names = []
        search_key = self._make_key(self.last_val_key_format, name='*',
                                    field='*')
        for key in self.db.keys(search_key):
            # Example key format:
            # appstats,path.to.module:Class.method,3600,60,last_val,CPU
            prefix, name, interval, part, suffix, field = key.split(',')
            if name not in names:
                names.append(name)
        return names

    def update(self):
        names = self._get_names()
        for name in names:
            for field in self.fields:
                key = self._make_key(self.key_format, name=name, field=field)
                key_last_val = self._make_key(self.last_val_key_format,
                                              name=name, field=field)
                key_updated = self._make_key(self.updated_key_format,
                                             name=name, field=field)

                if self.db.llen(key) == 0:
                    for i in xrange(self.interval / self.part - 1):
                        self.db.rpush(key, 0)
                    self.db.set(key_updated, time())

                updated = float(self.db.get(key_updated))
                last_val = int(self.db.get(key_last_val) or '0')
                passed_time = time() - updated

                # Check whether it is need to be updated:
                if passed_time > self.part:
                    num_of_new_parts = int(passed_time) / self.part
                    val_per_part = int(last_val / passed_time * self.part)

                    # For each new part perform a shift,
                    # filling a new cell with the value per one part:
                    for i in xrange(num_of_new_parts):
                        self.db.lpop(key)
                        self.db.rpush(key, val_per_part)

                    # New last_val = rest:
                    last_val -= num_of_new_parts * val_per_part
                    self.db.set(key_last_val, last_val)

                    # Evaluating time correction:
                    rest_time = passed_time - num_of_new_parts * self.part
                    self.db.set(key_updated, time() - rest_time)

    def get_vals(self, names=None):
        res = {}

        if not names:
            names = self._get_names()

        pl = self.db.pipeline()
        for name in names:
            for field in self.fields:
                key = self._make_key(self.key_format, name=name, field=field)
                key_last_val = self._make_key(self.last_val_key_format,
                                              name=name, field=field)
                pl.get(key_last_val)
                pl.lrange(key, 0, -1)
        pl_res = pl.execute()
        for name in names:
            counts = {}
            for field in self.fields:
                last_val = int(pl_res.pop(0) or '0')
                count = sum(map(int, pl_res.pop(0)))
                count += last_val
                counts[field] = count
            res[name] = counts
        return res

    def incrby(self, name, field, increment):
        if ',' in name:
            raise ValueError("Name can't contain ',' (comma)")

        if field not in self.fields:
            raise ValueError("No such field: %s" % field)

        key_last_val = self._make_key(self.last_val_key_format, name=name,
                                      field=field)
        self.db.incr(key_last_val, int(increment))


class HourlyCounter(object):
    """
    The HourlyCounter stores data, accumulated during strict hours intervals.
    E.g. data that came from 00:00 to 00:59.
    """

    key_format = '%(prefix)s,hourly,%(name)s,%(field)s'
    key_prev_upd_format = '%(prefix)s,hourly,prev_upd'

    def __init__(self, redis_db, mongo_db, fields, redis_prefix):
        self.redis_db = redis_db
        self.fields = fields
        self.collection = mongo_db.appstats_hourly
        self.prefix = redis_prefix

    def _get_names(self):
        names = []
        search_key = self._make_key(self.key_format, name='*',
                                    field='*')
        for key in self.redis_db.keys(search_key):
            # Example key format:
            # appstats,hourly,path.to.module:Class.method,CPU
            prefix, _, name, field = key.split(',')
            if name not in names:
                names.append(name)
        return names

    def _make_key(self, key_format, **kwargs):
        kwargs.update(prefix=self.prefix)
        return key_format % kwargs

    def incrby(self, name, field, increment):
        if ',' in name:
            raise ValueError("Name can't contain ',' (comma)")

        if field not in self.fields:
            raise ValueError("No such field: %s" % field)

        key = self._make_key(self.key_format, name=name, field=field)
        self.redis_db.incr(key, int(increment))

    def update(self):
        key_prev_upd = self._make_key(self.key_prev_upd_format)
        prev_upd = self.redis_db.get(key_prev_upd)

        # Get current datetime rounded to hour:
        now = datetime.datetime.utcnow()
        now = datetime.datetime.combine(datetime.date.today(),
                                        datetime.time(now.hour))
        if prev_upd:
            prev_upd = int(prev_upd) # Get timestamp
            prev_upd = datetime.datetime.utcfromtimestamp(prev_upd)
        else:
            # If there isn't prev_upd in redis,
            # we will use 'one hour before current time' variable instead:
            prev_upd = now - datetime.timedelta(hours=1)
            # Get unix timestamp:
            prev_upd_unix = timegm(prev_upd.utctimetuple())
            self.redis_db.set(key_prev_upd, prev_upd_unix)

        passed_hours = int((now - prev_upd).total_seconds()) / 3600
        if passed_hours == 0:
            # Too early, exiting
            return
        names = self._get_names()
        for name in names:
            doc = dict(name=name)
            for field in self.fields:
                key = self._make_key(self.key_format, name=name, field=field)
                val = int(self.redis_db.get(key) or '0')
                val_per_hour = val / passed_hours
                doc[field] = val_per_hour

                # For each passed hour add separate doc with the specific date:
                docs = []
                for i in xrange(passed_hours):
                    date = now - datetime.timedelta(hours=i)
                    doc['date'] = date
                    docs.append(doc.copy())
                # New val = rest:
                val -= passed_hours * val_per_hour
                self.redis_db.set(key, val)
            # Inserting docs in mongo:
            self.collection.insert(docs)
        prev_upd = timegm(now.utctimetuple())
        self.redis_db.set(key_prev_upd, prev_upd)

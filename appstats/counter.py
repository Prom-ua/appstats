# encoding: utf-8

import datetime
from time import time


class Counter(object):

    last_val_key_format = '%(prefix)s,%(name)s,%(interval)s,%(part)s,last_val,%(field)s'
    updated_key_format = '%(prefix)s,%(name)s,%(interval)s,%(part)s,updated,%(field)s'
    key_format = '%(prefix)s,%(name)s,%(interval)s,%(part)s,%(field)s'

    def __init__(self, db, app, fields, interval=3600, part=60):
        self.db = db
        self.prefix = app.config['REDIS_KEYS_PREFIX']
        self.interval = interval
        self.part = part
        self.fields = fields

    def _make_key(self, key_format, **kwargs):
        kwargs.update(prefix=self.prefix, interval=self.interval, part=self.part)
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

                # Check whether it is need to be updated
                if passed_time > self.part:
                    num_of_new_parts = int(passed_time) / self.part
                    val_per_part = int(last_val / passed_time * self.part)

                    for i in xrange(num_of_new_parts):
                        self.db.lpop(key)
                        self.db.rpush(key, val_per_part)

                    # New last_val = rest
                    last_val -= num_of_new_parts * val_per_part
                    self.db.set(key_last_val, last_val)

                    # Evaluate time correction
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
    key_format = '%(prefix)s,hourly,%(name)s,%(field)s'
    key_last_sent_format = '%(prefix)s,hourly,last_sent'

    def __init__(self, redis_db, mongo_db, app, fields):
        self.redis_db = redis_db
        self.fields = fields
        self.collection = mongo_db.appstats_hourly
        self.prefix = app.config['REDIS_KEYS_PREFIX']

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
        curr_hour = datetime.datetime.now().hour
        key_last_sent = self._make_key(self.key_last_sent_format)
        last_sent = self.redis_db.get(key_last_sent)
        if last_sent:
            last_sent = int(last_sent)
        else:
            self.redis_db.set(key_last_sent, curr_hour - 1)
            last_sent = curr_hour - 1
        new_hours = curr_hour - last_sent
        if not new_hours:
            return
        if new_hours < 0:
            new_hours = 24 - last_sent + curr_hour
        names = self._get_names()
        for name in names:
            doc = dict(name=name)
            for field in self.fields:
                key = self._make_key(self.key_format, name=name, field=field)
                val = int(self.redis_db.get(key) or '0')
                val_per_hour = val / new_hours
                doc[field] = val_per_hour
                docs = []
                for i in xrange(new_hours):
                    date = datetime.datetime.now().date()
                    new_date = datetime.datetime.combine(date,
                        datetime.time(curr_hour - i))
                    doc['date'] = new_date
                    docs.append(doc.copy())
                # New val = rest
                val -= new_hours * val_per_hour
                self.redis_db.set(key, val)
            self.collection.insert(docs)
        self.redis_db.set(key_last_sent, curr_hour)

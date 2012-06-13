# encoding: utf-8

from time import time


class Counter(object):
    last_val_key_format = '%(prefix)s,%(name)s,%(interval)s,%(part)s,last_val,%(field)s'
    updated_key_format = '%(prefix)s,%(name)s,%(interval)s,%(part)s,updated,%(field)s'
    key_format = '%(prefix)s,%(name)s,%(interval)s,%(part)s,%(field)s'

    def __init__(self, db, app, interval=3600, part=60):
        self.db = db
        self.prefix = app.config['REDIS_KEYS_PREFIX']
        self.interval = interval
        self.part = part
        self.fields = app.config['FIELDS']

    def _make_key(self, key_format, **kwargs):
        kwargs.update(prefix=self.prefix, interval=self.interval, part=self.part)
        return key_format % kwargs

    def _get_names(self):
        names = []
        search_key = self._make_key(
            self.last_val_key_format, name='*', field=self.fields[0]
        )
        for key in self.db.keys(search_key):
            # Example key format: statistics,path.to.module:Class.method,3600,60,last_val,REQUESTS
            prefix, name, interval, part, suffix, field = key.split(',')
            names.append(name)
        return names

    def update(self):
        names = self._get_names()
        for name in names:
            for field in self.fields:
                key = self._make_key(self.key_format, name=name, field=field)
                key_last_val = self._make_key(
                    self.last_val_key_format, name=name, field=field
                )
                key_updated = self._make_key(
                    self.updated_key_format, name=name, field=field
                )

                updated = float(self.db.get(key_updated))
                last_val = int(self.db.get(key_last_val))
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
        res = []
        if not names:
            names = self._get_names()
        for name in names:
            vals = {}
            for field in self.fields:
                key = self._make_key(self.key_format, name=name, field=field)
                key_last_val = self._make_key(
                    self.last_val_key_format, name=name, field=field
                )
                last_val = int(self.db.get(key_last_val) or '0')
                vals.update({
                    field: reduce(
                        lambda acc, val: acc + int(val),
                        self.db.lrange(key, 0, -1),
                        last_val
                    )
                })
            vals.update({'NAME': name})
            res.append(vals)
        return res

    def incrby(self, name, field, increment):
        if ',' in name:
            raise Exception("Name can't contain ',' (comma)")
        if field not in self.fields:
            raise Exception("No such field")
        if name not in self._get_names():
            for counter_field in self.fields:
                key = self._make_key(
                    self.key_format, name=name, field=counter_field
                )
                key_last_val = self._make_key(
                    self.last_val_key_format, name=name, field=counter_field
                )
                key_updated = self._make_key(
                    self.updated_key_format, name=name, field=counter_field
                )
                for i in xrange(self.interval / self.part - 1):
                    self.db.rpush(key, 0)
                self.db.set(key_updated, time())
                self.db.set(key_last_val, 0)
        key_last_val = self._make_key(
            self.last_val_key_format, name=name, field=field
        )
        self.db.incr(key_last_val, increment)

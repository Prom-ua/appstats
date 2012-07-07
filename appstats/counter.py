# encoding: utf-8

from calendar import timegm
from datetime import datetime, timedelta, time


class RollingCounter(object):
    """
    The rolling counter, which stores data only
    for the specified time interval.

    Parameters:
      - 'db' -- redis db instance to accumulate statistics data in
      - 'fields' -- list of fields names to track of
      - 'redis_prefix' -- prefix used in each redis key to separate statistics
      data
      - 'interval' -- interval during which the counter stores the data
      - 'part' -- accuracy indicator, number of parts interval will split
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
        pl = self.db.pipeline()
        now = timegm(datetime.utcnow().utctimetuple())
        for name in names:
            for field in self.fields:
                key = self._make_key(self.key_format, name=name, field=field)
                last_val_key = self._make_key(self.last_val_key_format,
                                              name=name, field=field)
                updated_key = self._make_key(self.updated_key_format,
                                             name=name, field=field)

                if self.db.llen(key) == 0:
                    for i in xrange(self.interval / self.part - 1):
                        self.db.rpush(key, 0)
                    self.db.set(updated_key, now)

                updated = float(self.db.get(updated_key))
                last_val = int(self.db.get(last_val_key) or '0')
                passed_time = now - updated

                # Check whether it is need to be updated
                if passed_time > self.part:
                    num_of_new_parts = int(passed_time) / self.part
                    val_per_part = int(last_val / passed_time * self.part)

                    # For each new part perform a shift,
                    # filling a new cell with the value per one part
                    for i in xrange(num_of_new_parts):
                        pl.lpop(key)
                        pl.rpush(key, val_per_part)

                    # New last_val = rest
                    last_val -= num_of_new_parts * val_per_part
                    pl.set(last_val_key, last_val)

                    # Evaluating time correction
                    rest_time = passed_time - num_of_new_parts * self.part
                    pl.set(updated_key, now - rest_time)
        pl.execute()

    def get_vals(self, names=None):
        res = {}

        if not names:
            names = self._get_names()

        pl = self.db.pipeline()
        for name in names:
            for field in self.fields:
                key = self._make_key(self.key_format, name=name, field=field)
                last_val_key = self._make_key(self.last_val_key_format,
                                              name=name, field=field)
                pl.get(last_val_key)
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

        last_val_key = self._make_key(self.last_val_key_format, name=name,
                                      field=field)
        self.db.incr(last_val_key, int(increment))


class PeriodicCounter(object):
    """
    The PeriodicCounter stores data, accumulated during strict intervals.
    E.g. if divider = 1, counter stores data that came from 00:00 to 00:59.

    Parameters:
      - 'divider' -- hour divider, specifies interval. E.g. if divider = 3,
      interval = 60 / 3 = 20 minutes. 1 <= divider <= 60
      - 'redis_db' -- redis db instance to temporary accumulate information in
      - 'mongo_db' -- mongo db instance to store statistics in
      - 'fields' -- list of fields names to track of
      - 'redis_prefix' -- prefix used in each redis key to separate statistics
      data
    """

    key_format = '%(prefix)s,periodic,%(divider)s,%(name)s,%(field)s'
    prev_upd_key_format = '%(prefix)s,periodic,%(divider)s,prev_upd'

    def __init__(self, divider, redis_db, mongo_db, fields, redis_prefix):
        self.redis_db = redis_db
        self.fields = fields
        self.collection = mongo_db['appstats_periodic-%u' % divider]
        self.prefix = redis_prefix
        self.divider = divider
        self._interval = 60 / divider

    def _get_names(self):
        names = []
        search_key = self._make_key(self.key_format, name='*',
                                    field='*')
        for key in self.redis_db.keys(search_key):
            # Example key format:
            # appstats,periodic,6,path.to.module:Class.method,CPU
            prefix, periodic, divider, name, field = key.split(',')
            if name not in names:
                names.append(name)
        return names

    def _make_key(self, key_format, **kwargs):
        kwargs.update(prefix=self.prefix, divider=self.divider)
        return key_format % kwargs

    def incrby(self, name, field, increment):
        if ',' in name:
            raise ValueError("Name can't contain ',' (comma)")

        if field not in self.fields:
            raise ValueError("No such field: %s" % field)

        key = self._make_key(self.key_format, name=name, field=field)
        self.redis_db.incr(key, int(increment))

    def update(self):
        prev_upd_key = self._make_key(self.prev_upd_key_format)
        prev_upd = self.redis_db.get(prev_upd_key)

        # Get current datetime rounded to interval
        now = datetime.utcnow()
        new_time = time(hour=now.hour,
                        minute=(now.minute / self._interval * self._interval))
        now = datetime.combine(now.date(), new_time)
        if prev_upd:
            prev_upd = int(prev_upd) # Get previous timestamp
            prev_upd = datetime.utcfromtimestamp(prev_upd)
        else:
            # If there isn't prev_upd in redis,
            # we will use 'one interval before current time' variable instead
            prev_upd = now - timedelta(minutes=self._interval)
            # Get unix timestamp
            prev_upd_unix = timegm(prev_upd.utctimetuple())
            self.redis_db.set(prev_upd_key, prev_upd_unix)
        delta = now - prev_upd
        # 24 * 60 = 1440
        passed_intervals = (delta.days * 1440 + delta.seconds / 60) / self._interval
        if passed_intervals == 0:
            # Too early, exiting
            return
        names = self._get_names()
        for name in names:
            # Trying to get site, separated by @ from the name
            if len(name.split('@')) == 2:
                site, short_name = name.split('@')
            else:
                short_name = name
                site = 'prom.ua' # if site isn't specified, take default one
            doc = dict(name=short_name, site=site)
            for field in self.fields:
                key = self._make_key(self.key_format, name=name, field=field)
                val = int(self.redis_db.get(key) or '0')
                val_per_interval = val / passed_intervals
                doc[field] = val_per_interval

                # For each passed interval add separate doc with the specific date
                docs = []
                for offset_scale in xrange(passed_intervals):
                    offset = self._interval * offset_scale
                    date = now - timedelta(minutes=offset)
                    doc['date'] = date
                    docs.append(doc.copy())
                # New val = rest
                val -= passed_intervals * val_per_interval
                self.redis_db.set(key, val)
            self.collection.insert(docs)
        prev_upd = timegm(now.utctimetuple())
        self.redis_db.set(prev_upd_key, prev_upd)

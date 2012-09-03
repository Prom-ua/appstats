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
      - 'parts' -- accuracy indicator, number of parts interval will split
    """

    last_val_key_format = '%(prefix)s,%(app_id)s,%(name)s,%(interval)s,%(parts)s,last_val,%(field)s'
    updated_key_format = '%(prefix)s,%(app_id)s,%(name)s,%(interval)s,%(parts)s,updated,%(field)s'
    key_format = '%(prefix)s,%(app_id)s,%(name)s,%(interval)s,%(parts)s,%(field)s'

    def __init__(self, db, fields, redis_prefix, interval=3600, parts=60):
        self.db = db
        self.prefix = redis_prefix
        self.interval = interval
        self.parts = parts
        self.fields = fields

    def _make_key(self, key_format, **kwargs):
        kwargs.update(prefix=self.prefix, interval=self.interval,
                      parts=self.parts)
        return key_format % kwargs

    def _get_app_ids(self):
        app_ids = set()
        search_key = self._make_key(self.last_val_key_format, app_id='*',
                                    name='*', field='*')
        for key in self.db.keys(search_key):
            # Example key format:
            # appstats,prom.ua,path.to.module:Class.method,3600,60,last_val,CPU
            prefix, app_id, name, interval, parts, suffix, field = key.split(',')
            app_ids.add(app_id)
        return app_ids

    def _get_names(self, app_id):
        names = set()
        search_key = self._make_key(self.last_val_key_format, app_id=app_id,
                                    name='*', field='*')
        for key in self.db.keys(search_key):
            # Example key format:
            # appstats,prom.ua,path.to.module:Class.method,3600,60,last_val,CPU
            prefix, app_id, name, interval, parts, suffix, field = key.split(',')
            names.add(name)
        return names

    def update(self):
        pl = self.db.pipeline()
        now = timegm(datetime.utcnow().utctimetuple())
        for app_id in self._get_app_ids():
            for name in self._get_names(app_id):
                for field in self.fields:
                    key = self._make_key(self.key_format, name=name,
                                         app_id=app_id, field=field)
                    last_val_key = self._make_key(self.last_val_key_format,
                                                  app_id=app_id, name=name,
                                                  field=field)
                    updated_key = self._make_key(self.updated_key_format,
                                                 app_id=app_id, name=name,
                                                 field=field)

                    if self.db.llen(key) == 0:
                        for i in xrange(self.interval / self.parts - 1):
                            self.db.rpush(key, 0)
                        self.db.set(updated_key, now)

                    updated = float(self.db.get(updated_key))
                    last_val = int(self.db.get(last_val_key) or '0')
                    passed_time = now - updated

                    # Check whether it is need to be updated
                    if passed_time > self.parts:
                        num_of_new_parts = int(passed_time) / self.parts
                        val_per_part = last_val // num_of_new_parts

                        # There is no need to pop and push the same values more
                        # than self.parts times.
                        if num_of_new_parts > self.parts:
                            num_of_new_parts = self.parts

                        # For each new part (without the final) perform a shift,
                        # filling a new cell with the value per one part
                        for i in xrange(num_of_new_parts - 1):
                            pl.lpop(key)
                            pl.rpush(key, val_per_part)
                        # The final one will contain the rest
                        rest = last_val - (num_of_new_parts - 1) * val_per_part
                        pl.lpop(key)
                        pl.rpush(key, rest)

                        # New last_val = 0
                        pl.set(last_val_key, 0)

                        # Evaluating time correction
                        rest_time = passed_time - num_of_new_parts * self.parts
                        pl.set(updated_key, now - rest_time)
        pl.execute()

    def get_vals(self):
        pl = self.db.pipeline()
        app_ids = self._get_app_ids()
        for app_id in app_ids:
            names = self._get_names(app_id)
            for name in names:
                for field in self.fields:
                    key = self._make_key(self.key_format, name=name,
                                         app_id=app_id, field=field)
                    last_val_key = self._make_key(self.last_val_key_format,
                                                  app_id=app_id, name=name,
                                                  field=field)
                    pl.get(last_val_key)
                    pl.lrange(key, 0, -1)
        pl_res = pl.execute()
        res = {}
        for app_id in app_ids:
            res[app_id] = {}
            names = self._get_names(app_id)
            for name in names:
                counts = {}
                for field in self.fields:
                    last_val = int(pl_res.pop(0) or '0')
                    count = sum(map(int, pl_res.pop(0)))
                    count += last_val
                    # Restore value by dividing it on 10000000
                    count /= 1000000.
                    counts[field] = count
                res[app_id][name] = counts
        # res format example: {'app_id1': {'name1': {'field1': 1, 'field2': 2}}}
        return res

    def incrby(self, app_id, name, field, increment):
        if ',' in name:
            raise ValueError("Name can't contain ',' (comma)")
        if ',' in app_id:
            raise ValueError("App_id can't contain ',' (comma)")
        if field not in self.fields:
            return

        last_val_key = self._make_key(self.last_val_key_format, app_id=app_id,
                                      name=name, field=field)
        # Hook for more accurate storing
        increment *= 1000000
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
      - 'period' -- interval in hours during which the counter stores the data.
      All data older than this value will be removed.
      Default value is 30 * 24 = 720 (30 days).
    """

    key_format = '%(prefix)s,periodic,%(divider)s,%(app_id)s,%(name)s,%(field)s'
    prev_upd_key_format = '%(prefix)s,periodic,%(divider)s,prev_upd'

    def __init__(self, divider, redis_db, mongo_db, fields,
                 redis_prefix, period=720):
        self.redis_db = redis_db
        self.fields = fields
        self.collection = mongo_db['appstats_periodic-%u' % divider]
        self.prefix = redis_prefix
        self.divider = divider
        self.period = period
        self.interval = 60 / divider

    def _get_app_ids(self):
        app_ids = set()
        search_key = self._make_key(self.key_format, app_id='*',
                                    name='*', field='*')
        for key in self.redis_db.keys(search_key):
            # Example key format:
            # appstats,periodic,6,prom.ua,path.to.module:Class.method,CPU
            prefix, periodic, divider, app_id, name, field = key.split(',')
            app_ids.add(app_id)
        return app_ids

    def _get_names(self, app_id):
        names = set()
        search_key = self._make_key(self.key_format, name='*', app_id=app_id,
                                    field='*')
        for key in self.redis_db.keys(search_key):
            # Example key format:
            # appstats,periodic,6,prom.ua,path.to.module:Class.method,CPU
            prefix, periodic, divider, app_id, name, field = key.split(',')
            names.add(name)
        return names

    def _make_key(self, key_format, **kwargs):
        kwargs.update(prefix=self.prefix, divider=self.divider)
        return key_format % kwargs

    def incrby(self, app_id, name, field, increment):
        if ',' in name:
            raise ValueError("Name can't contain ',' (comma)")
        if ',' in app_id:
            raise ValueError("App_id can't contain ',' (comma)")
        if field not in self.fields:
            return

        key = self._make_key(self.key_format, app_id=app_id, name=name,
                             field=field)
        # Hook for more accurate storing
        increment *= 1000000
        self.redis_db.incr(key, int(increment))

    def update(self):
        prev_upd_key = self._make_key(self.prev_upd_key_format)
        prev_upd = self.redis_db.get(prev_upd_key)

        # Get current utc datetime rounded to interval
        now = datetime.utcnow()
        new_time = time(hour=now.hour,
                        minute=((now.minute // self.interval) * self.interval))
        now = datetime.combine(now.date(), new_time)
        if prev_upd:
            prev_upd = int(prev_upd)  # Get previous timestamp
            prev_upd = datetime.utcfromtimestamp(prev_upd)
        else:
            # If there isn't prev_upd in redis,
            # use 'one interval before current time' variable instead
            prev_upd = now - timedelta(minutes=self.interval)
            # Get unix utc timestamp
            prev_upd_unix = timegm(prev_upd.utctimetuple())
            self.redis_db.set(prev_upd_key, prev_upd_unix)
        delta = now - prev_upd
        # 24 * 60 = 1440
        passed_intervals = (delta.days * 1440 + delta.seconds / 60) / self.interval
        if passed_intervals == 0:
            # Too early, exiting
            return
        for app_id in self._get_app_ids():
            for name in self._get_names(app_id):
                doc = dict(name=name, app_id=app_id)
                for field in self.fields:
                    key = self._make_key(self.key_format, app_id=app_id,
                                         name=name, field=field)
                    val = self.redis_db.get(key)
                    # Restore value by dividing it on 10000000
                    val = float(val) / 1000000. if val else 0.0
                    val_per_interval = val / passed_intervals
                    doc[field] = val_per_interval

                    # For each passed interval add separate doc with the specific date
                    docs = []
                    for offset_scale in xrange(passed_intervals):
                        offset = self.interval * offset_scale
                        date = now - timedelta(minutes=offset)
                        doc['date'] = date
                        docs.append(doc.copy())
                    # New val = 0
                    self.redis_db.set(key, 0)
                self.collection.insert(docs)
            prev_upd = timegm(now.utctimetuple())
            self.redis_db.set(prev_upd_key, prev_upd)
            oldest_date = now - timedelta(hours=self.period)
            self.collection.remove({'date': {'$lte': oldest_date}})

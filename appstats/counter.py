# encoding: utf-8

import logging
from time import sleep
from calendar import timegm
from datetime import datetime, timedelta, time

from pymongo.errors import AutoReconnect


log = logging.getLogger(__name__)


class RollingCounter(object):
    """
    The rolling counter, which stores data only
    for the specified time interval.

    Parameters:
      - 'db' -- redis db instance to accumulate statistics data in
      - 'fields' -- list of fields names to track of
      - 'redis_prefix' -- prefix used in each redis key to separate statistics
      data
      - 'stats' -- statistics type id
      - 'interval' -- interval during which the counter stores the data
      - 'secs_per_part' -- accuracy indicator, determine the time range of
      one part in seconds
    """

    last_val_key_format = '%(prefix)s,%(app_id)s,%(name)s,%(interval)s,%(secs_per_part)s,last_val,%(field)s'
    updated_key_format = '%(prefix)s,%(app_id)s,%(name)s,%(interval)s,%(secs_per_part)s,updated,%(field)s'
    key_format = '%(prefix)s,%(app_id)s,%(name)s,%(interval)s,%(secs_per_part)s,%(field)s'

    def __init__(self, db, fields, redis_prefix, stats='apps',
                 interval=3600, secs_per_part=60):
        self.db = db
        self.prefix = '%s_%s' % (redis_prefix, stats)
        self.interval = interval
        self.secs_per_part = secs_per_part
        self._num_of_parts = interval // secs_per_part
        self.fields = fields

    def _make_key(self, key_format, **kwargs):
        """
        Return redis key produced by inserting kwargs into given `key_format`.
        Specify format with `prefix`, `interval` and `secs_per_part` values
        taken from counter object.
        """
        kwargs.update(prefix=self.prefix, interval=self.interval,
                      secs_per_part=self.secs_per_part)
        return key_format % kwargs

    def _get_app_ids(self):
        """
        Return all app_ids this counter works with.
        """
        app_ids = set()
        search_key = self._make_key(self.last_val_key_format, app_id='*',
                                    name='*', field='*')
        for key in self.db.keys(search_key):
            # Example key format:
            # appstats,prom.ua,path.to.module:Class.method,3600,60,last_val,CPU
            (prefix, app_id, name,
             interval, secs_per_part,
             suffix, field) = key.split(',')
            app_ids.add(app_id)
        return app_ids

    def _get_names(self, app_id):
        """
        Return all names this counter watching over.
        """
        names = set()
        search_key = self._make_key(self.last_val_key_format, app_id=app_id,
                                    name='*', field='*')
        for key in self.db.keys(search_key):
            # Example key format:
            # appstats,prom.ua,path.to.module:Class.method,3600,60,last_val,CPU
            (prefix, app_id, name,
             interval, secs_per_part,
             suffix, field) = key.split(',')
            names.add(name)
        return names

    def update(self):
        """
        Actualize counter statistics.
        This method should be called periodically (not necessarily) with
        period less or equal `secs_per_part` for better accuracy.
        """
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
                        for i in xrange(self._num_of_parts - 1):
                            self.db.rpush(key, 0)
                        self.db.set(updated_key, now)

                    updated = float(self.db.get(updated_key))
                    last_val = float(self.db.get(last_val_key) or '0.0')
                    passed_time = now - updated

                    # Check whether it is need to be updated
                    if passed_time > self.secs_per_part:
                        num_of_new_parts = int(
                            passed_time // self.secs_per_part)
                        val_per_part = last_val / num_of_new_parts

                        # There is no need to pop and push the same values more
                        # than self._num_of_parts times.
                        if num_of_new_parts > self._num_of_parts:
                            num_of_shifts = self._num_of_parts
                        else:
                            num_of_shifts = num_of_new_parts

                        # For each new part perform a shift,
                        # filling a new cell with the value per one part
                        for i in xrange(num_of_shifts):
                            pl.lpop(key)
                            pl.rpush(key, val_per_part)

                        # New last_val = 0
                        pl.set(last_val_key, 0)

                        # Evaluating time correction
                        rest_time = passed_time - num_of_new_parts * self.secs_per_part
                        pl.set(updated_key, now - rest_time)
        pl.execute()

    def get_vals(self):
        """
        Return all data counter has.
        Result format example:
            {'app_id1': {'name1': {'field1': 1, 'field2': 2}}}
        """
        pl = self.db.pipeline()
        app_id_names = {app_id: self._get_names(app_id)
                        for app_id in self._get_app_ids()}
        for app_id, names in app_id_names.iteritems():
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
        for app_id, names in app_id_names.iteritems():
            res[app_id] = {}
            for name in names:
                counts = {}
                for field in self.fields:
                    last_val = float(pl_res.pop(0) or '0.0')
                    count = sum(map(float, pl_res.pop(0)))
                    count += last_val
                    counts[field] = count
                res[app_id][name] = counts
        return res

    def incrby(self, app_id, name, field, increment):
        """
        Add `increment` to value of a count
        specified by `app_id`, `name` and `field`
        """
        if ',' in name:
            raise ValueError("Name can't contain ',' (comma)")
        if ',' in app_id:
            raise ValueError("App_id can't contain ',' (comma)")
        if field not in self.fields:
            return

        last_val_key = self._make_key(self.last_val_key_format, app_id=app_id,
                                      name=name, field=field)
        self.db.incrbyfloat(last_val_key, increment)


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
      - 'stats' -- statistics type id
      - 'period' -- interval in hours during which the counter stores the data.
      All data older than this value will be removed.
      Default value is 30 * 24 = 720 (30 days).
    """

    key_format = '%(prefix)s,periodic,%(divider)s,%(app_id)s,%(name)s,%(field)s'
    prev_upd_key_format = '%(prefix)s,periodic,%(divider)s,prev_upd'
    MAX_MONGO_RETRIES = 3
    MAX_PASSED_INTERVALS = 10

    def __init__(self, divider, redis_db, mongo_db, fields,
                 redis_prefix, stats='apps', period=720):
        self.redis_db = redis_db
        self.fields = fields
        self.collection = mongo_db['appstats_%s_periodic-%u' % (stats, divider)]
        self.prefix = '%s_%s' % (redis_prefix, stats)
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
        self.redis_db.incrbyfloat(key, increment)

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
        passed_intervals = int(delta.total_seconds() / 60 / self.interval)
        if passed_intervals == 0:
            # Too early, exiting
            return

        # Quick fix for case, when many intervals have passed
        if passed_intervals < MAX_PASSED_INTERVALS:
            num_intervals = passed_intervals
        else:
            num_intervals = MAX_PASSED_INTERVALS

        docs = []
        for app_id in self._get_app_ids():
            for name in self._get_names(app_id):
                doc = dict(name=name, app_id=app_id)
                for field in self.fields:
                    key = self._make_key(self.key_format, app_id=app_id,
                                         name=name, field=field)
                    val = self.redis_db.get(key)
                    val = float(val) if val else 0.0
                    val_per_interval = val / passed_intervals
                    doc[field] = val_per_interval
                    # New val = 0
                    self.redis_db.set(key, 0)

                # For each passed interval
                # add separate doc with the specific date
                for offset_scale in xrange(num_intervals):
                    offset = self.interval * offset_scale
                    date = now - timedelta(minutes=offset)
                    doc['date'] = date
                    docs.append(doc.copy())
        if docs:
            # Make MAX_MONGO_RETRIES tries to insert docs
            tries = self.MAX_MONGO_RETRIES
            while True:
                try:
                    self.collection.insert(docs)
                    break
                except AutoReconnect:
                    log.warn("AutoReconnect exception while inserting "
                             "docs in mongo")
                    # Last try, raise exception
                    if tries <= 0:
                        raise
                    tries -= 1
                    sleep(0.5)

            prev_upd = timegm(now.utctimetuple())
            self.redis_db.set(prev_upd_key, prev_upd)
            oldest_date = now - timedelta(hours=self.period)
            self.collection.remove({'date': {'$lte': oldest_date}})

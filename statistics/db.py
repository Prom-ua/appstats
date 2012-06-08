from statistics import app
import redis

class RedisDB(object):
    def __init__(self, host=None, port=None, day_parts=24, hour_parts=60):
        self.host = host or app.config['REDIS_HOST']
        self.port = port or app.config['REDIS_PORT']
        self.day_parts = day_parts
        self.hour_parts = hour_parts
        self.set_key = app.config['REDIS_KEYS_PREFIX'] + 'keys'
        self.db = redis.Redis(host=self.host, port=self.port)

    def __contains__(self, name):
        key_prefix = RedisDB.make_key('min', name)
        for key in self.get_keys_starts_with(key_prefix):
            name_from_db = RedisDB.split_key(key)['name']
            if name == name_from_db:
                return True
        return False

    def get_keys_starts_with(self, prefix):
        res = []
        keys = self.db.smembers(self.set_key)
        for key in keys:
            if key.startswith(prefix):
                res += [key]
        return res
    
    def add_name(self, name, fields):
        for field in fields:
            pl = self.db.pipeline()
            key = RedisDB.make_key('min', name, field)
            pl.set(key, 0)
            pl.sadd(self.set_key, key)
            key = RedisDB.make_key('hour', name, field)
            pl.sadd(self.set_key, key)
            for i in xrange(self.hour_parts):
                pl.lpush(key, 0)
            key = RedisDB.make_key('day', name, field)
            pl.sadd(self.set_key, key)
            for i in xrange(self.day_parts):
                pl.lpush(key, 0)
            pl.execute()
    
    def get_all_names(self):
        key_prefix = RedisDB.make_key('min')
        names = []
        for key in self.get_keys_starts_with(key_prefix):
            name = RedisDB.split_key(key)['name']
            names += [name] if name not in names else []
        return names
    
    @staticmethod
    def make_key(table, name='', field=''):
        return app.config['REDIS_KEYS_PREFIX'] + table + '.' + \
            ((name + '.') if name else '') + field

    @staticmethod
    def split_key(key):
        table = key.split('.')[1]
        field = key.split('.')[-1]
        name = '.'.join(key.split('.')[2:-1])
        return {'table': table, 'field': field, 'name': name}


    def inc_field(self, name, field):
        key = RedisDB.make_key('min', name, field)
        self.db.incr(key)

    def set_min_value(self, name, field, value):
        key = RedisDB.make_key('min', name, field)
        self.db.set(key, value)
        
    def get_value(self, table, name, field):
        key = RedisDB.make_key(table, name, field)
        if table == 'min':
            return int(self.db.get(key))
        return sum([int(count) for count in self.db.lrange(key, 0, -1)])

    def get_all_fields(self, table, name):
        key_prefix = RedisDB.make_key(table, name)
        pl = self.db.pipeline()
        res = {}
        fields = []
        for key in self.get_keys_starts_with(key_prefix):
            field = RedisDB.split_key(key)['field']
            fields += [field]
            pl.lrange(key, 0, -1)
        for field, row in zip(fields, pl.execute()):
            res.update({field: sum([int(count) for count in row])})
        res.update({'NAME': name})
        return res

    def get_all(self, table):
        key_prefix = RedisDB.make_key(table)
        res = []
        names = []
        for name in self.get_all_names():
            res += [self.get_all_fields(table=table, name=name)]
        return res

    def update_hour_table(self):
        key_prefix = RedisDB.make_key('hour')
        for key in self.get_keys_starts_with(key_prefix):
            min_key = RedisDB.split_key(key)
            min_key.update({'table': 'min'})
            min_key = RedisDB.make_key(**min_key)
            per_min = self.db.getset(min_key, 0)
            self.db.lpop(key)
            self.db.rpush(key, per_min)
            
    def update_day_table(self):
        key_prefix = RedisDB.make_key('day')
        for key in self.get_keys_starts_with(key_prefix):
            hour_key = RedisDB.split_key(key)
            hour_key.update({'table': 'hour'})
            per_hour = self.get_value(**hour_key)
            self.db.lpop(key)
            self.db.rpush(key, per_hour)


def get_all_sum(db):
    res = []
    for key in db.keys(app.config['REDIS_KEYS_PREFIX'] + '*'):
        row = db.hgetall(key)
        for k in row:
            row[k] = int(row[k])
        row.update({'NAME': key.split(app.config['REDIS_KEYS_PREFIX'])[1]})
        key = app.config['REDIS_HOUR_KEYS_PREFIX'] + key
        req_per_hour = sum([int(count) for count in db.lrange(key, 0, -1)])
        row.update({'REQUESTS_PER_HOUR': req_per_hour})
        res += [row]
    return res

def connect_redis_db(host=None, port=None):
    host = host or app.config['REDIS_HOST']
    port = port or app.config['REDIS_PORT']
    db = redis.Redis(host=host, port=port)
    return db

connect_db = connect_redis_db

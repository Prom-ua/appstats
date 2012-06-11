from time import time
class Counter():
    def __init__(self, fields, db, app, interval=3600, part=60):
        self.db = db
        self.fields = fields
        self.prefix = app.config['REDIS_KEYS_PREFIX']
        self.interval = interval
        self.part = part

    def update(self):
        names = []
        for key in self.db.keys("%s*.%s.%s.%s" % (self.prefix, self.interval, self.part, self.fields[0])):
            names += ['.'.join(key.split('.')[1:-3])]
        for name in names:
            for field in self.fields:
                key = "%s%s.%s.%s.%s" % (self.prefix, name, self.interval, self.part, field)
                key_last = "%s%s.%s.%s.last.%s" % (self.prefix, name, self.interval, self.part, field)

                if self.db.llen(key) == 0:
                    for i in xrange(self.interval/self.part - 1):
                        self.db.rpush(key, 0)
                    self.db.hset(key_last, 'updated', time())

                updated = float(self.db.hget(key_last, 'updated'))
                val = int(self.db.hget(key_last, 'val'))
                passed_time = time() - updated
                print passed_time
                if passed_time > self.part:
                    num_of_new_parts = int(passed_time) / self.part
                    val_per_part = int(val / passed_time * self.part)
                    for i in xrange(num_of_new_parts):
                        self.db.lpop(key)
                        self.db.rpush(key, val_per_part)
                    val -= num_of_new_parts * val_per_part
                    self.db.hset(key_last, 'val', val)
                    rest_time = passed_time - num_of_new_parts * self.part
                    self.db.hset(key_last, 'updated', time() - rest_time)

    def get_vals(self, names=None):
        res = []
        if not names:
            names = []
            for key in self.db.keys("%s*.%s.%s.%s" % (self.prefix, self.interval, self.part, self.fields[0])):
                names += ['.'.join(key.split('.')[1:-3])]

        for name in names:
            vals = {}
            for field in self.fields:
                key = "%s%s.%s.%s.%s" % (self.prefix, name, self.interval, self.part, field)
                key_last = "%s%s.%s.%s.last.%s" % (self.prefix, name, self.interval, self.part, field)
                last_val = int(self.db.hget(key_last, 'val'))
                vals.update(
                    {field: sum([int(count) for count in self.db.lrange(key, 0, -1)]) + last_val}
                )
            vals.update({'NAME': name})
            res += [vals]
        return res

    def incrby_last(self, name, field, increment):
        key_last = "%s%s.%s.%s.last.%s" % (self.prefix, name, self.interval, self.part, field)
        self.db.hincrby(key_last, 'val', increment)

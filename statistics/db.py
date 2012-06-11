class Counter():
    def __init__(self, fields, db, app, interval=3600, part=60):
        self.db = db
        self.fields = fields
        self.prefix = app.config['REDIS_KEYS_PREFIX']
        self.interval = interval
        self.part = part

    def update(self, name, field, new_val):
        key = "%s%s.%s.%s.%s" % (self.prefix, name, self.interval, self.part, field)
        if self.db.llen(key) == 0:
            for i in xrange(self.interval/self.part):
                self.db.rpush(key, 0)
        self.db.lpop(key)
        self.db.rpush(key, new_val)

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
                vals.update(
                    {field: sum([int(count) for count in self.db.lrange(key, 0, -1)])}
                )
            vals.update({'NAME': name})
            res += [vals]
        return res

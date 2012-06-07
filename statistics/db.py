from statistics import app
import redis

def get_all_sum(db):
    res = []
    for key in db.keys(app.config['REDIS_KEYS_PREFIX'] + '*'):
        row = db.hgetall(key)
        for k in row:
            row[k] = int(row[k])
        row.update({'NAME': key.split(app.config['REDIS_KEYS_PREFIX'])[1]})
        res += [row]
    return res

def connect_redis_db(host=None, port=None):
    host = host or app.config['REDIS_HOST']
    port = port or app.config['REDIS_PORT']
    db = redis.Redis(host=host, port=port)
    return db

connect_db = connect_redis_db

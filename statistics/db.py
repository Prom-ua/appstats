from statistics import app
import redis

def connect_db(host=None, port=None):
    host = host or app.config['REDIS_HOST']
    port = port or app.config['REDIS_PORT']
    db = redis.Redis(host=host, port=port)
    return db

def get_all_sum(db):
    res = []
    for key in db.keys("statistics.*"):
        row = db.hgetall(key)
        for k in row:
            row[k] = int(row[k])
        row.update({'NAME': key.split("statistics.")[1]})
        res += [row]
    return res

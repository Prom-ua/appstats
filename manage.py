from flaskext.script import Manager

from statistics import app
from statistics.db import connect_redis_db, RedisDB

manager = Manager(app)

@manager.command
def periodic_requests_update():
    db = connect_redis_db()
    for key in db.keys(app.config['REDIS_KEYS_PREFIX'] + '*'):
        req_count = int(db.hget(key, 'REQUESTS'))
        req_count_prev = int(db.hget(key, 'REQUESTS_PREV') or '0')
        db.hset(key, 'REQUESTS_PREV', req_count)
        key = app.config['REDIS_HOUR_KEYS_PREFIX'] + key
        while db.llen(key) < 6:
            db.lpush(key, 0)
        db.lpop(key)
        db.rpush(key, req_count - req_count_prev)

@manager.command
def update_hour_table():
    db = RedisDB()
    db.update_hour_table()

@manager.command
def update_day_table():
    db = RedisDB()
    db.update_day_table()

if __name__ == "__main__":
    manager.run()

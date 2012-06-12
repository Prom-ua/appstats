from flask import Flask
from statistics.counter import Counter
import redis

app = Flask(__name__)
app.config.from_object('config')
db = redis.Redis(host=app.config['REDIS_HOST'], port=app.config['REDIS_PORT'])
hour_counter = Counter(db=db, app=app)
day_counter = Counter(interval=86400, part=3600, db=db, app=app)
min_counter = Counter(interval=60, part=60, db=db, app=app)

import statistics.webui

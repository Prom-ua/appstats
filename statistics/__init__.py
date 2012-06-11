from flask import Flask
from statistics.db import Counter
import redis

app = Flask(__name__)
app.config.from_object('config')
db = redis.Redis(host=app.config['REDIS_HOST'], port=app.config['REDIS_PORT'])
fields = ["CPU", "TOTAL", "SQL", "SOLR", "REDIS", "MEMCACHED", "REQUESTS"]
hour_counter = Counter(fields=fields, db=db, app=app)
day_counter = Counter(interval=86400, part=3600, fields=fields, db=db, app=app)
min_counter = Counter(interval=60, part=60, fields=fields, db=db, app=app)

import statistics.webui

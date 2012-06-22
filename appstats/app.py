# encoding: utf-8

from os.path import expanduser

import redis
from flask import Flask, render_template, request
from pymongo import Connection, DESCENDING
from werkzeug.wsgi import ClosingIterator

from .counter import Counter


app = Flask(__name__)
app.config.from_object('appstats.config')
if not app.config.from_envvar('APPSTATS_SETTINGS', silent=True):
    app.config.from_pyfile('/etc/appstats.cfg', silent=True)
    app.config.from_pyfile(expanduser('~/.appstats.cfg'), silent=True)
redis_db = redis.Redis(host=app.config['REDIS_HOST'], port=app.config['REDIS_PORT'])
mongo_conn = Connection(host=app.config['MONGO_HOST'],
                      port=app.config['MONGO_PORT'],
                      network_timeout=30,
                      _connect=False
             )
mongo_db = mongo_conn[app.config['MONGO_DB_NAME']]
hour_counter = Counter(db=redis_db, app=app)
day_counter = Counter(interval=86400, part=3600, db=redis_db, app=app)
counters = [hour_counter, day_counter]
number_of_lines = 20


def add_data_middleware(wsgi_app):
    def inner(environ, start_response):
        iterator = wsgi_app(environ, start_response)
        data = environ.get('appstats.data')
        if not data:
            return iterator
        return ClosingIterator(iterator, lambda: add_data(data))
    return inner


app.wsgi_app = add_data_middleware(app.wsgi_app)


def add_data(data):
    for name, counts in data.iteritems():
        if not 'NUMBER' in counts:
            for counter in counters:
                counter.incrby(name, 'NUMBER', 1)
        for field, val in counts.iteritems():
            for counter in counters:
                counter.incrby(name, field, val)


@app.route('/')
def main_page():
    sort_by_field = request.args.get('sort_by_field', 'NUMBER')
    sort_by_period = request.args.get('sort_by_period', 'hour')
    number_of_lines = request.args.get('number_of_lines', 20, int)

    table = mongo_db.appstats_table.find()
    if sort_by_field == 'name':
        table = table.sort('name')
    else:
        table = table.sort('%s_%s' % (sort_by_field, sort_by_period), DESCENDING)
    table = table.limit(number_of_lines)

    return render_template('main_page.html', table=table,
                           fields=hour_counter.fields,
                           sort_by_field=sort_by_field,
                           sort_by_period=sort_by_period,
                           number_of_lines=number_of_lines)


@app.route('/add/', methods=['POST'])
def add_page():
    data = request.json
    request.environ['appstats.data'] = data
    return 'ok'

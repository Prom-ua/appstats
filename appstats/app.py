# encoding: utf-8

import datetime
from time import mktime
from os.path import expanduser

import pytz
import redis
from flask import Flask, render_template, request
from pymongo import Connection, DESCENDING
from werkzeug.wsgi import ClosingIterator

from .counter import RollingCounter, HourlyCounter


app = Flask(__name__)
app.config.from_object('appstats.config')
if not app.config.from_envvar('APPSTATS_SETTINGS', silent=True):
    app.config.from_pyfile('/etc/appstats.cfg', silent=True)
    app.config.from_pyfile(expanduser('~/.appstats.cfg'), silent=True)

fields = app.config['FIELDS'][:]
if 'NUMBER' not in fields:
    fields.insert(0, 'NUMBER')

redis_db = redis.Redis(host=app.config['REDIS_HOST'],
                       port=app.config['REDIS_PORT'],
                       db=app.config['REDIS_DB'])
REDIS_PREFIX = 'appstats'

mongo_conn = Connection(host=app.config['MONGO_HOST'],
                        port=app.config['MONGO_PORT'], network_timeout=30,
                        _connect=False)
mongo_db = mongo_conn[app.config['MONGO_DB_NAME']]

last_hour_counter = RollingCounter(db=redis_db, fields=fields,
                                   redis_prefix=REDIS_PREFIX)

last_day_counter = RollingCounter(db=redis_db, fields=fields,
                                  redis_prefix=REDIS_PREFIX, interval=86400,
                                  part=3600)

hourly_counter = HourlyCounter(redis_db=redis_db, mongo_db=mongo_db,
                               fields=fields, redis_prefix=REDIS_PREFIX)

counters = [last_hour_counter, last_day_counter, hourly_counter]


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
    selected_field = request.args.get('selected_field', 'NUMBER')

    docs = mongo_db.appstats_docs.find()
    if sort_by_field == 'name':
        docs = docs.sort('name')
    else:
        sort_by = '%s_%s' % (sort_by_field, sort_by_period)
        docs = docs.sort(sort_by, DESCENDING)
    docs = docs.limit(number_of_lines)

    return render_template('main_page.html', sort_by_field=sort_by_field,
                           fields=fields, sort_by_period=sort_by_period,
                           number_of_lines=number_of_lines, docs=docs,
                           selected_field=selected_field)


@app.route('/info/')
def info_page():
    name = request.args.get('name')
    field = request.args.get('field', fields[0])
    hours = request.args.get('hours', 6, int)
    # Starting datetime of needed data
    starting_from = datetime.datetime.utcnow() - datetime.timedelta(hours=hours)
    docs = mongo_db.appstats_hourly.find({'name': name,
                                          'date': {'$gt': starting_from}})
    docs = docs.sort('date')
    tz = pytz.timezone('Europe/Kiev')
    data = []
    # If docs is empty, we will return zero value on current datime.
    if docs.count() == 0:
        date = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
        date = date.astimezone(tz)
        data = [[mktime(date.timetuple()) * 1000, 0]]
    # For each doc localize date, transform timestamp from seconds to
    # milliseconds and append list [data, value] to data
    for doc in docs:
        date = doc['date'].replace(tzinfo=pytz.utc)
        date = date.astimezone(tz)
        point = [mktime(date.timetuple()) * 1000, doc[field]]
        data.append(point)
    return render_template('info_page.html', fields=fields, data=data,
                           name=name, selected_field=field, hours=hours)


@app.route('/add/', methods=['POST'])
def add_page():
    data = request.json
    request.environ['appstats.data'] = data
    return 'ok'

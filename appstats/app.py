# encoding: utf-8

import datetime
from time import mktime
from copy import deepcopy
from os.path import expanduser
from operator import itemgetter

import pytz
import redis
from flask import Flask, render_template, request, url_for
from pymongo import Connection, DESCENDING
from werkzeug.wsgi import ClosingIterator

from .counter import RollingCounter, PeriodicCounter
from .filters import json_filter, time_filter, count_filter


app = Flask(__name__)
app.config.from_object('appstats.config')
if not app.config.from_envvar('APPSTATS_SETTINGS', silent=True):
    app.config.from_pyfile('/etc/appstats.cfg', silent=True)
    app.config.from_pyfile(expanduser('~/.appstats.cfg'), silent=True)

time_fields = deepcopy(app.config['TIME_FIELDS'])
fields = app.config['FIELDS'] + time_fields
if 'NUMBER' not in [field['key'] for field in fields]:
    fields.insert(0, dict(key='NUMBER', name='NUMBER',
                          format=None, visible=True))
fields_keys = [field['key'] for field in fields]
visible_fields = filter(itemgetter('visible'), fields)

redis_db = redis.Redis(host=app.config['REDIS_HOST'],
                       port=app.config['REDIS_PORT'],
                       db=app.config['REDIS_DB'])
REDIS_PREFIX = 'appstats'

mongo_conn = Connection(host=app.config['MONGO_HOST'], network_timeout=30,
                        port=app.config['MONGO_PORT'], _connect=False)
mongo_db = mongo_conn[app.config['MONGO_DB_NAME']]

last_hour_counter = RollingCounter(db=redis_db, fields=fields_keys,
                                   redis_prefix=REDIS_PREFIX)
last_day_counter = RollingCounter(db=redis_db, fields=fields_keys,
                                  redis_prefix=REDIS_PREFIX, interval=86400,
                                  part=3600)
rolling_counters = [last_hour_counter, last_day_counter]

periodic_counters = []
# Very accurate, 6 hours counter with 1 min intervals
periodic_counters.append(PeriodicCounter(divider=60, redis_db=redis_db,
                                         mongo_db=mongo_db, fields=fields_keys,
                                         redis_prefix=REDIS_PREFIX,
                                         period=6))
# Middle accurate, 6 days(144 hours) counter with 10 min intervals
periodic_counters.append(PeriodicCounter(divider=6, redis_db=redis_db,
                                         mongo_db=mongo_db, fields=fields_keys,
                                         redis_prefix=REDIS_PREFIX,
                                         period=144))
# Low accurate, half-year(182 * 24 = 4368) counter with 60 min intervals
periodic_counters.append(PeriodicCounter(divider=1, redis_db=redis_db,
                                         mongo_db=mongo_db, fields=fields_keys,
                                         redis_prefix=REDIS_PREFIX,
                                         period=4368))
periodic_counters = sorted(periodic_counters, key=lambda c: c.period)

counters = rolling_counters + periodic_counters


app.jinja_env.filters['json'] = json_filter
app.jinja_env.filters['time'] = time_filter
app.jinja_env.filters['count'] = count_filter


def current_url(**updates):
    args = request.view_args.copy()
    args.update(request.args)
    args.update(updates)
    return url_for(request.endpoint, **args)
app.jinja_env.globals['current_url'] = current_url


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
    for app_id in data:
        for name, counts in data[app_id].iteritems():
            if not 'NUMBER' in counts:
                for counter in counters:
                    counter.incrby(app_id, name, 'NUMBER', 1)
            for field, val in counts.iteritems():
                for counter in counters:
                    counter.incrby(app_id, name, field, val)


@app.route('/', defaults={'app_id': app.config['APP_IDS'][0]['key']})
@app.route('/<app_id>/')
def main_page(app_id):
    sort_by_field = request.args.get('sort_by_field', 'NUMBER')
    sort_by_period = request.args.get('sort_by_period', 'hour')
    number_of_lines = request.args.get('number_of_lines', 10, int)
    selected_field = request.args.get('selected_field', 'NUMBER')

    docs = mongo_db.appstats_docs.find({'app_id': app_id})
    if sort_by_field == 'name':
        docs = docs.sort('name')
    else:
        sort_by = '%s_%s' % (sort_by_field, sort_by_period)
        docs = docs.sort(sort_by, DESCENDING)
    docs = docs.limit(number_of_lines)

    return render_template('main_page.html', sort_by_field=sort_by_field,
                           fields=visible_fields,
                           sort_by_period=sort_by_period, docs=docs,
                           number_of_lines=number_of_lines,
                           selected_field=selected_field, app_id=app_id,
                           app_ids=app.config['APP_IDS'])


@app.route('/info/<app_id>/<name>/')
def info_page(app_id, name):
    hours = request.args.get('hours', 6, int)
    # Starting datetime of needed data
    starting_from = datetime.datetime.utcnow() - datetime.timedelta(hours=hours)
    # Choosing the most suitable, accurate counter based on given hours
    counter = None
    for periodic_counter in periodic_counters:
        if hours <= periodic_counter.period:
            counter = periodic_counter
            break
    # If there isn't suitable counter,
    # take the last one (contains the most full data)
    if not counter:
        counter = periodic_counters[-1]
    docs = counter.collection.find({'name': name, 'app_id': app_id,
                                    'date': {'$gt': starting_from}})
    docs = docs.sort('date')
    tz = pytz.timezone('Europe/Kiev')
    # Prepare list of rows for each time_field
    time_data = [[] for _ in time_fields]
    num_data = []
    # If docs is empty, return zero value on current datetime.
    if docs.count() == 0:
        date = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
        date = date.astimezone(tz)
        date = mktime(date.timetuple()) * 1000
        num_data = [[date, 0]]
        time_data = [[[date, 0]]]
    # For each doc localize date, transform timestamp from seconds to
    # milliseconds and append list [date, value] to data
    for doc in docs:
        date = doc['date'].replace(tzinfo=pytz.utc)
        date = date.astimezone(tz)
        date = mktime(date.timetuple()) * 1000

        if doc['NUMBER'] == 0:
            num_data.append([date, None])
            for row in time_data:
                row.append([date, None])
            continue

        req_per_sec = float(doc['NUMBER']) / (counter.interval * 60)
        num_point = [date, req_per_sec]
        num_data.append(num_point)
        
        for i, time_field in enumerate(time_fields):
            key = time_field['key']
            value = doc.get(key)
            if value:
                value = float(value) / doc['NUMBER']
            time_data[i].append([date, value])
    num_data = [num_data]
    # Get all names from time_fields and use tham as labels
    time_labels = [f['name'] for f in time_fields]

    doc = mongo_db.appstats_docs.find({'app_id': app_id, 'name': name}).next()

    return render_template('info_page.html', fields=visible_fields, doc=doc,
                           num_data=num_data, name=name, hours=hours,
                           selected_site=app_id, app_id=app_id,
                           app_ids=app.config['APP_IDS'],
                           time_labels=time_labels, time_data=time_data)


@app.route('/add/', methods=['POST'])
def add_page():
    data = request.json
    request.environ['appstats.data'] = data
    return 'ok'

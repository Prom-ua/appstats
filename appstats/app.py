# encoding: utf-8

from os.path import expanduser

import redis
from flask import Flask, render_template, request
from werkzeug.wsgi import ClosingIterator

from .counter import Counter


app = Flask(__name__)
app.config.from_object('appstats.config')
if not app.config.from_envvar('APPSTATS_SETTINGS', silent=True):
    app.config.from_pyfile('/etc/appstats.cfg', silent=True)
    app.config.from_pyfile(expanduser('~/.appstats.cfg'), silent=True)
db = redis.Redis(host=app.config['REDIS_HOST'], port=app.config['REDIS_PORT'])
hour_counter = Counter(db=db, app=app)
day_counter = Counter(interval=86400, part=3600, db=db, app=app)
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
    hour_data = hour_counter.get_vals()
    day_aver_data = day_counter.get_vals()
    hour_aver_data = {}

    for name, counts in hour_data.iteritems():
        req_count = counts['NUMBER']
        h_aver_counts = {}
        for field in counts:
            if field == 'NUMBER':
                req_per_hour = float(counts[field]) / hour_counter.interval
                h_aver_counts[field] = round(req_per_hour, 2)
            else:
                h_aver_counts[field] = round(float(counts[field]) / req_count, 2)
        hour_aver_data[name] = h_aver_counts

    for name, counts in day_aver_data.iteritems():
        req_count = counts['NUMBER']
        for field in counts:
            if  field == 'NUMBER':
                req_per_day = float(counts[field]) / day_counter.interval
                counts[field] = round(req_per_day, 2)
            else:
                counts[field] = round(float(counts[field]) / req_count, 2)

    data = {}
    for name in hour_data:
        data[name] = dict(hour=hour_data[name], hour_aver=hour_aver_data[name],
                          day_aver=day_aver_data[name])

    sort_by_field = request.args.get('sort_by_field', 'NUMBER')
    sort_by_period = request.args.get('sort_by_period', 'hour')
    number_of_lines = request.args.get('number_of_lines', 20, int)
    if sort_by_field == 'NAME':
        get_sorting_key = lambda tpl: tpl[0]
    else:
        get_sorting_key = lambda tpl: tpl[1][sort_by_period][sort_by_field]
    data = sorted(data.items(), key=get_sorting_key,
                  reverse=True)[:number_of_lines]

    return render_template('main_page.html', data=data,
                           fields=hour_counter.fields,
                           sort_by_field=sort_by_field,
                           sort_by_period=sort_by_period,
                           number_of_lines=number_of_lines)


@app.route('/add/', methods=['POST'])
def add_page():
    data = request.json
    request.environ['appstats.data'] = data
    return 'ok'

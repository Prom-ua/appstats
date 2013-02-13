# encoding: utf-8

from copy import deepcopy
from os.path import expanduser
from operator import itemgetter
from datetime import datetime
from collections import OrderedDict

import redis
from flask import abort, Blueprint, Flask, redirect
from flask import render_template, request, url_for
from pymongo import Connection, ASCENDING, DESCENDING
from werkzeug.wsgi import ClosingIterator

from .util import current_url, get_chart_info
from .counter import RollingCounter, PeriodicCounter
from .filters import json_filter, time_filter, count_filter, default_filter
from .filters import pretty_hours_filter


app = Flask(__name__)
app.config.from_object('appstats.config')
if not app.config.from_envvar('APPSTATS_SETTINGS', silent=True):
    app.config.from_pyfile('/etc/appstats.cfg', silent=True)
    app.config.from_pyfile(expanduser('~/.appstats.cfg'), silent=True)

APPLICATIONS = OrderedDict(app.config['APPLICATIONS'])

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

mongo_conn = Connection(host=app.config['MONGO_URI'], network_timeout=30,
                        connecttimeoutms=60000, _connect=False)
mongo_db = mongo_conn[app.config['MONGO_DB_NAME']]

########################### Application Counters ##############################

# Appliations statistics rolling counters
apps_last_hour_counter = RollingCounter(db=redis_db, fields=fields_keys,
                                        redis_prefix=REDIS_PREFIX)
apps_last_day_counter = RollingCounter(db=redis_db, fields=fields_keys,
                                       redis_prefix=REDIS_PREFIX,
                                       interval=86400, secs_per_part=3600)
apps_rolling_counters = [apps_last_hour_counter, apps_last_day_counter]

# Appliations statistics periodic counters
apps_periodic_counters = []
# Very accurate, 6 hours counter with 1 min intervals
apps_periodic_counters.append(PeriodicCounter(
    divider=60, redis_db=redis_db,
    mongo_db=mongo_db, fields=fields_keys,
    redis_prefix=REDIS_PREFIX, period=6))
# Middle accurate, 6 days(144 hours) counter with 10 min intervals
apps_periodic_counters.append(PeriodicCounter(
    divider=6, redis_db=redis_db,
    mongo_db=mongo_db, fields=fields_keys,
    redis_prefix=REDIS_PREFIX, period=144))
# Low accurate, half-year(182 * 24 = 4368) counter with 60 min intervals
apps_periodic_counters.append(PeriodicCounter(
    divider=1, redis_db=redis_db,
    mongo_db=mongo_db, fields=fields_keys,
    redis_prefix=REDIS_PREFIX, period=4368))
apps_periodic_counters = sorted(apps_periodic_counters, key=lambda c: c.period)

# All applications counters
apps_counters = apps_rolling_counters + apps_periodic_counters

###############################################################################

############################## Tasks Counters #################################
# Tasks statistics rolling counters
tasks_last_hour_counter = RollingCounter(db=redis_db, fields=fields_keys,
                                         redis_prefix=REDIS_PREFIX,
                                         stats='tasks')
tasks_last_day_counter = RollingCounter(db=redis_db, fields=fields_keys,
                                        redis_prefix=REDIS_PREFIX,
                                        stats='tasks', interval=86400,
                                        secs_per_part=3600)
tasks_rolling_counters = [tasks_last_hour_counter, tasks_last_day_counter]

# Tasks statistics periodic counters
tasks_periodic_counters = []
# Very accurate, 6 hours counter with 1 min intervals
tasks_periodic_counters.append(PeriodicCounter(
    divider=60, redis_db=redis_db,
    mongo_db=mongo_db, fields=fields_keys,
    redis_prefix=REDIS_PREFIX, period=6, stats='tasks'))
# Middle accurate, 6 days(144 hours) counter with 10 min intervals
tasks_periodic_counters.append(PeriodicCounter(
    divider=6, redis_db=redis_db,
    mongo_db=mongo_db, fields=fields_keys,
    redis_prefix=REDIS_PREFIX, period=144, stats='tasks'))
# Low accurate, half-year(182 * 24 = 4368) counter with 60 min intervals
tasks_periodic_counters.append(PeriodicCounter(
    divider=1, redis_db=redis_db,
    mongo_db=mongo_db, fields=fields_keys,
    redis_prefix=REDIS_PREFIX, period=4368, stats='tasks'))
tasks_periodic_counters = sorted(tasks_periodic_counters,
                                 key=lambda c: c.period)

# All tasks counters
tasks_counters = tasks_rolling_counters + tasks_periodic_counters

###############################################################################


ROWS_LIMIT_OPTIONS = [10, 25, 50]
INFO_HOURS_OPTIONS = [6, 12, 24, 144, 720]


app.jinja_env.filters['json'] = json_filter
app.jinja_env.filters['time'] = time_filter
app.jinja_env.filters['count'] = count_filter
app.jinja_env.filters['default'] = default_filter
app.jinja_env.filters['pretty_hours'] = pretty_hours_filter

app.jinja_env.globals['current_url'] = current_url


def add_stats_middleware(wsgi_app):
    def inner(environ, start_response):
        iterator = wsgi_app(environ, start_response)
        apps_stats = environ.get('appstats.apps_stats')
        tasks_stats = environ.get('appstats.tasks_stats')
        if not (apps_stats or tasks_stats):
            return iterator
        return ClosingIterator(iterator, lambda: add_stats(apps_stats,
                                                           tasks_stats,
                                                           apps_counters,
                                                           tasks_counters))
    return inner
app.wsgi_app = add_stats_middleware(app.wsgi_app)


def add_stats(apps_stats, tasks_stats, apps_counters, tasks_counters):
    if apps_stats:
        app.logger.debug("Adding new apps_stats: \n %s", apps_stats)
        for app_id in apps_stats:
            for name, counts in apps_stats[app_id].iteritems():
                if not 'NUMBER' in counts:
                    for counter in apps_counters:
                        counter.incrby(app_id, name, 'NUMBER', 1)
                for field, val in counts.iteritems():
                    for counter in apps_counters:
                        counter.incrby(app_id, name, field, val)

    if tasks_stats:
        app.logger.debug("Adding new tasks_stats: \n %s", tasks_stats)
        for app_id in tasks_stats:
            for name, counts in tasks_stats[app_id].iteritems():
                if not 'NUMBER' in counts:
                    for counter in tasks_counters:
                        counter.incrby(app_id, name, 'NUMBER', 1)
                for field, val in counts.iteritems():
                    for counter in tasks_counters:
                        counter.incrby(app_id, name, field, val)


@app.route('/')
def dashboard():
    return redirect(url_for('stats_frontend.appstats'))


@app.route('/add/apps_stats', methods=['GET'])
def add_apps_stats_help():
    return render_template('add_page_help.jinja')


@app.route('/add/apps_stats', methods=['POST'])
def add_apps_stats():
    apps_stats = request.json
    request.environ['appstats.apps_stats'] = apps_stats
    return 'ok'


@app.route('/add/tasks_stats', methods=['GET'])
def add_tasks_stats_help():
    return render_template('add_page_help.jinja')


@app.route('/add/tasks_stats', methods=['POST'])
def add_tasks_stats():
    tasks_stats = request.json
    request.environ['appstats.tasks_stats'] = tasks_stats
    return 'ok'


@app.route('/add/event', methods=['GET'])
def add_event_page_help():
    return render_template('add_event_page_help.jinja')


@app.route('/add/event', methods=['POST'])
def add_event_page():
    events = request.json
    if events:
        docs = [{'app_id': event['app_id'], 'title': event['title'],
                 'date': datetime.utcfromtimestamp(event['timestamp']),
                 'descr': event['descr']} for event in events]
        app.logger.debug("Adding new events: \n %s", docs)
        mongo_db.appstats_events.insert(docs)
    mongo_db.appstats_events.ensure_index([('date', ASCENDING),
                                           ('app_id', ASCENDING)],
                                          ttl=3600)
    return 'ok'


stats_bp = Blueprint('stats_frontend', __name__, url_prefix='/<app_id>')


@stats_bp.url_defaults
def add_app_id(endpoint, values):
    values.setdefault('app_id', APPLICATIONS.keys()[0])


@stats_bp.url_value_preprocessor
def check_app_id(endpoint, values):
    if values['app_id'] not in APPLICATIONS:
        abort(404)


@stats_bp.context_processor
def add_nav_list():
    """
    nav_list structure:
    {
        'name': 'AppStats',
        'url': '/',
        'rates': [
            {
                'name': 'Application',
                'url': '/appstats/',
                'active': True
            }
        ],
        'apps_list':{
            'title':'App1',
            'apps':{
                'App1':'/url/1/',
                'App2':'/url/2/'
            }
        }
    }
    """
    app_id = request.view_args.get('app_id')
    app_name = APPLICATIONS[app_id]
    apps = {
        def_app_name: current_url(app_id=def_app_id)
        for def_app_id, def_app_name
        in APPLICATIONS.iteritems()}
    rates = []
    rates.append(dict(name='Application',
                      url=url_for('.appstats', app_id=app_id),
                      active=(request.endpoint == 'stats_frontend.appstats' or
                              request.endpoint == 'stats_frontend.apps_info')))
    rates.append(dict(name='Tasks',
                      url=url_for('.tasks', app_id=app_id),
                      active=(request.endpoint == 'stats_frontend.tasks' or
                              request.endpoint == 'stats_frontend.tasks_info')))
    rates.append(dict(name='Task queue',
                      url='',
                      active=False))
    rates.append(dict(name='Logs',
                      url='',
                      active=False))
    rates.append(dict(name='Tracing',
                      url='',
                      active=False))
    nav_list = dict(name='AppStats', url=url_for('dashboard'),
                    rates=rates, apps_list=dict(title=app_name, apps=apps))

    return dict(nav_list=nav_list)


@stats_bp.route('/appstats')
def appstats(app_id):
    sort_by_field = request.args.get('sort_by_field', 'NUMBER')
    if (sort_by_field not in (f['key'] for f in visible_fields)
        and sort_by_field != 'name'):
        abort(404)

    sort_by_period = request.args.get('sort_by_period', 'hour')

    rows_limit = request.args.get('rows', ROWS_LIMIT_OPTIONS[0], int)
    if rows_limit not in ROWS_LIMIT_OPTIONS:
        rows_limit = ROWS_LIMIT_OPTIONS[0]

    selected_field = request.args.get('selected_field', 'NUMBER')
    if selected_field not in (f['key'] for f in visible_fields):
        abort(404)

    docs = mongo_db.appstats_docs.find({'app_id': app_id})
    if sort_by_field == 'name':
        docs = docs.sort('name')
    else:
        sort_by = '%s_%s' % (sort_by_field, sort_by_period)
        docs = docs.sort(sort_by, DESCENDING)
    docs = docs.limit(rows_limit)

    return render_template('stats.jinja', sort_by_field=sort_by_field,
                           app_id=app_id, fields=visible_fields,
                           sort_by_period=sort_by_period, docs=docs,
                           rows_limit=rows_limit,
                           rows_limit_options=ROWS_LIMIT_OPTIONS,
                           selected_field=selected_field,
                           info_endpoint='.apps_info')


@stats_bp.route('/tasks')
def tasks(app_id):
    sort_by_field = request.args.get('sort_by_field', 'NUMBER')
    if (sort_by_field not in (f['key'] for f in visible_fields)
        and sort_by_field != 'name'):
        abort(404)

    sort_by_period = request.args.get('sort_by_period', 'hour')

    rows_limit = request.args.get('rows', ROWS_LIMIT_OPTIONS[0], int)
    if rows_limit not in ROWS_LIMIT_OPTIONS:
        rows_limit = ROWS_LIMIT_OPTIONS[0]

    selected_field = request.args.get('selected_field', 'NUMBER')
    if selected_field not in (f['key'] for f in visible_fields):
        abort(404)

    docs = mongo_db.appstats_tasks_docs.find({'app_id': app_id})
    if sort_by_field == 'name':
        docs = docs.sort('name')
    else:
        sort_by = '%s_%s' % (sort_by_field, sort_by_period)
        docs = docs.sort(sort_by, DESCENDING)
    docs = docs.limit(rows_limit)

    return render_template('stats.jinja', sort_by_field=sort_by_field,
                           app_id=app_id, fields=visible_fields,
                           sort_by_period=sort_by_period, docs=docs,
                           rows_limit=rows_limit,
                           rows_limit_options=ROWS_LIMIT_OPTIONS,
                           selected_field=selected_field,
                           info_endpoint='.tasks_info')


@stats_bp.route('/appstats/<name>')
def apps_info(app_id, name):
    hours = request.args.get('hours', INFO_HOURS_OPTIONS[0], int)
    if hours not in INFO_HOURS_OPTIONS:
        hours = INFO_HOURS_OPTIONS[0]

    num_data, time_data = get_chart_info(apps_periodic_counters, time_fields,
                                         app_id, name, hours)

    # Get all names from time_fields and use them as labels
    time_labels = [f['name'] for f in time_fields]

    doc = mongo_db.appstats_docs.find_one(
        {'app_id': app_id, 'name': name}) or {}

    return render_template('info_page.jinja', fields=visible_fields, doc=doc,
                           info_hours_options=INFO_HOURS_OPTIONS,
                           num_data=num_data, name=name, hours=hours,
                           time_labels=time_labels, time_data=time_data)


@stats_bp.route('/tasks/<name>')
def tasks_info(app_id, name):
    hours = request.args.get('hours', INFO_HOURS_OPTIONS[0], int)
    if hours not in INFO_HOURS_OPTIONS:
        hours = INFO_HOURS_OPTIONS[0]

    num_data, time_data = get_chart_info(tasks_periodic_counters, time_fields,
                                         app_id, name, hours)

    # Get all names from time_fields and use them as labels
    time_labels = [f['name'] for f in time_fields]

    doc = mongo_db.appstats_tasks_docs.find_one(
        {'app_id': app_id, 'name': name}) or {}

    return render_template('info_page.jinja', fields=visible_fields, doc=doc,
                           info_hours_options=INFO_HOURS_OPTIONS,
                           num_data=num_data, name=name, hours=hours,
                           time_labels=time_labels, time_data=time_data)


app.register_blueprint(stats_bp)

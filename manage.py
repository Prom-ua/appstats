# encoding: utf-8

from datetime import datetime, timedelta

from flaskext.script import Manager
from pymongo import ASCENDING

from appstats.app import app, apps_last_hour_counter, apps_last_day_counter
from appstats.app import app, tasks_last_hour_counter, tasks_last_day_counter
from appstats.app import apps_periodic_counters, tasks_periodic_counters
from appstats.app import apps_counters, tasks_counters
from appstats.app import REDIS_PREFIX, redis_db, mongo_db

from appstats.util import calc_aver_data, data_to_flat_form


manager = Manager(app)


@manager.option('-d', '--days', dest='days', type=int, default=182)
@manager.option('-s', '--stats', required=True, dest='stats',
                choices=['apps', 'tasks'], help='Stats to strip')
def strip_db(days, stats):
    """ Remove data older then specified number of days from db. """
    oldest_date = datetime.utcnow() - timedelta(days)
    if stats == 'apps':
        periodic_counters = apps_periodic_counters
    elif stats == 'tasks':
        periodic_counters = apps_periodic_counters
    for periodic_counter in periodic_counters:
        periodic_counter.collection.remove({'date': {'$lt': oldest_date}})


@manager.command
def clear():
    """ Delete all data from redis and mongo dbs. """
    # Flush all redis records with appstats prefix
    keys = redis_db.keys('%s*' % REDIS_PREFIX)
    if keys:
        redis_db.delete(*keys)
    # Drop mongo 'cache' collection
    mongo_db.drop_collection('appstats_docs')
    mongo_db.drop_collection('appstats_tasks_docs')
    # Drop mongo events collection
    mongo_db.drop_collection('appstats_events')
    # Drop all mongo periodic stats collections
    for periodic_counter in apps_periodic_counters + tasks_periodic_counters:
        mongo_db.drop_collection(periodic_counter.collection)


@manager.option('-s', '--stats', required=True, dest='stats',
                choices=['apps', 'tasks'], help='Statistics to update')
def update_counters(stats):
    """ Update all counters """
    if stats == 'apps':
        counters = apps_counters
        periodic_counters = apps_periodic_counters
    elif stats == 'tasks':
        counters = tasks_counters
        periodic_counters = tasks_periodic_counters
    # Ensuring indexes
    for counter in periodic_counters:
        counter.collection.ensure_index([('app_id', ASCENDING),
                                         ('name', ASCENDING),
                                         ('date', ASCENDING)],
                                        ttl=3600)
    for counter in counters:
        counter.update()


@manager.option('-s', '--stats', required=True, dest='stats',
                choices=['apps', 'tasks'], help='Statistics to update')
def update_cache(stats):
    """ Update cache """
    if stats == 'apps':
        collection = mongo_db['appstats_docs']
        last_hour_counter = apps_last_hour_counter
        last_day_counter = apps_last_day_counter
    elif stats == 'tasks':
        collection = mongo_db['appstats_tasks_docs']
        last_hour_counter = tasks_last_hour_counter
        last_day_counter = tasks_last_day_counter
    # Ensuring indexes
    collection.ensure_index([('app_id', ASCENDING), ('name', ASCENDING)],
                            ttl=3600)

    hour_data = last_hour_counter.get_vals()
    day_data = last_day_counter.get_vals()
    hour_aver_data = calc_aver_data(hour_data, last_hour_counter.interval)
    day_aver_data = calc_aver_data(day_data, last_day_counter.interval)

    docs = data_to_flat_form(hour_data, hour_aver_data,
                             day_data, day_aver_data,
                             last_hour_counter.fields)
    # Replace with new data
    collection.remove()
    if docs:
        collection.insert(docs.values())


if __name__ == '__main__':
    manager.run()

# encoding: utf-8

from datetime import datetime, timedelta

from flaskext.script import Manager

from appstats.app import (app, last_hour_counter, last_day_counter,
    periodic_counter, counters, mongo_db, redis_db, REDIS_PREFIX
)


manager = Manager(app)


@manager.command
def strip_db():
    max_age = 182 # Half-year
    oldest_date = datetime.utcnow() - timedelta(max_age)
    periodic_counter.collection.remove({'date': {'$lt': oldest_date}})


@manager.command
def clear():
    # Flush all redis records with appstats prefix
    keys = redis_db.keys('%s*' % REDIS_PREFIX)
    redis_db.delete(*keys)
    # Drop mongo 'cache' collection
    mongo_db.drop_collection('appstats_docs')
    # Drop mongo periodic stats collection
    mongo_db.drop_collection(periodic_counter.collection)


@manager.command
def update():
    for counter in counters:
        counter.update()

    hour_data = last_hour_counter.get_vals()
    day_data = last_day_counter.get_vals()
    day_aver_data = {}
    hour_aver_data = {}

    # Calculating hour average data
    for app_id in hour_data:
        hour_aver_data[app_id] = {}
        for name, counts in hour_data[app_id].iteritems():
            req_count = counts['NUMBER']
            h_aver_counts = {}
            if req_count == 0:
                for field in counts:
                    h_aver_counts[field] = 0.0
                continue
            for field in counts:
                if field == 'NUMBER':
                    req_per_hour = float(counts[field]) / last_hour_counter.interval
                    h_aver_counts[field] = round(req_per_hour, 1)
                else:
                    h_aver_counts[field] = round(float(counts[field]) / req_count, 1)
            hour_aver_data[app_id][name] = h_aver_counts

    # Calculating day average data
    for app_id in day_data:
        day_aver_data[app_id] = {}
        for name, counts in day_data[app_id].iteritems():
            req_count = counts['NUMBER']
            d_aver_counts = {}
            if req_count == 0:
                for field in counts:
                    d_aver_counts[field] = 0.0
                continue
            for field in counts:
                if  field == 'NUMBER':
                    req_per_day = float(counts[field]) / last_day_counter.interval
                    d_aver_counts[field] = round(req_per_day, 1)
                else:
                    d_aver_counts[field] = round(float(counts[field]) / req_count, 1)
            day_aver_data[app_id][name] = d_aver_counts

    # Transforming data into flat form
    docs = {}

    for app_id in hour_data:
        for name in hour_data[app_id]:
            doc = docs.setdefault((app_id, name), dict(app_id=app_id, name=name))
            for field in last_hour_counter.fields:
                key = '%s_%s' % (field, 'hour')
                doc[key] = hour_data[app_id][name][field]

        for name in hour_aver_data[app_id]:
            doc = docs.setdefault((app_id, name), dict(app_id=app_id, name=name))
            for field in last_hour_counter.fields:
                key = '%s_%s' % (field, 'hour_aver')
                doc[key] = hour_aver_data[app_id][name][field]

    for app_id in day_data:
        for name in day_data[app_id]:
            doc = docs.setdefault((app_id, name), dict(app_id=app_id, name=name))
            for field in last_day_counter.fields:
                key = '%s_%s' % (field, 'day')
                doc[key] = day_data[app_id][name][field]

        for name in day_aver_data[app_id]:
            doc = docs.setdefault((app_id, name), dict(app_id=app_id, name=name))
            for field in last_day_counter.fields:
                key = '%s_%s' % (field, 'day_aver')
                doc[key] = day_aver_data[app_id][name][field]

    # Replace with new data
    mongo_db.appstats_docs.remove()
    if docs:
        mongo_db.appstats_docs.insert(docs.values())


if __name__ == '__main__':
    manager.run()

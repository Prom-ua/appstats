# encoding: utf-8

from flaskext.script import Manager

from appstats.app import app, hour_counter, day_counter, mongo_db


manager = Manager(app)


@manager.command
def update():
    hour_counter.update()
    day_counter.update()

    hour_data = hour_counter.get_vals()
    day_aver_data = day_counter.get_vals()
    hour_aver_data = {}

    # Calculating hour average data
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

    # Calculating day average data
    for name, counts in day_aver_data.iteritems():
        req_count = counts['NUMBER']
        for field in counts:
            if  field == 'NUMBER':
                req_per_day = float(counts[field]) / day_counter.interval
                counts[field] = round(req_per_day, 2)
            else:
                counts[field] = round(float(counts[field]) / req_count, 2)

    # Transforming data into flat form
    docs = []
    for name in hour_data:
        doc = {}
        doc['name'] = name
        for field in hour_counter.fields:
            key = '%s_%s' % (field, 'hour')
            doc[key] = hour_data[name][field]

            key = '%s_%s' % (field, 'hour_aver')
            doc[key] = hour_aver_data[name][field]

            key = '%s_%s' % (field, 'day_aver')
            doc[key] = day_aver_data[name][field]
        docs.append(doc)

    # Replace with new data
    mongo_db.appstats_docs.remove()
    if docs:
        mongo_db.appstats_docs.insert(docs)


if __name__ == '__main__':
    manager.run()

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
    table = []
    for name in hour_data:
        record = {}
        record['name'] = name
        for field in hour_counter.fields:
            key = '%s_%s' % (field, 'hour')
            record[key] = hour_data[name][field]

            key = '%s_%s' % (field, 'hour_aver')
            record[key] = hour_aver_data[name][field]

            key = '%s_%s' % (field, 'day_aver')
            record[key] = day_aver_data[name][field]
        table.append(record)

    # Replace with new data
    mongo_db.appstats_table.remove()
    if table:
        mongo_db.appstats_table.insert(table)


if __name__ == '__main__':
    manager.run()

# encoding: utf-8

import redis

from flask import Flask, render_template, redirect, request

from .counter import Counter


app = Flask(__name__)
app.config.from_object('config')
db = redis.Redis(host=app.config['REDIS_HOST'], port=app.config['REDIS_PORT'])
hour_counter = Counter(db=db, app=app)
day_counter = Counter(interval=86400, part=3600, db=db, app=app)
counters = [hour_counter, day_counter]


def add_data(data):
    name = data['NAME']
    if not 'REQUESTS' in data:
        for counter in counters:
            counter.incrby(name, "REQUESTS", 1)
    for field in data:
        for counter in counters:
            if field != 'NAME':
                counter.incrby(name, field, data[field])


@app.route('/')
def main_page():
    hour_data = hour_counter.get_vals()
    day_aver_data = day_counter.get_vals()
    hour_aver_data = []

    for row in hour_data:
        req_count = row['REQUESTS']
        h_aver_row = {}
        for k in row:
            if k == 'NAME':
                h_aver_row[k] = row[k]
            elif k == 'REQUESTS':
                h_aver_row[k] = round(float(row[k]) / hour_counter.interval, 2)
            elif k in hour_counter.fields:
                h_aver_row[k] = round(float(row[k]) / req_count, 2)
        hour_aver_data.append(h_aver_row)

    for row in day_aver_data:
        req_count = row['REQUESTS']
        for k in row:
            if  k == 'REQUESTS':
                row[k] = round(float(row[k]) / day_counter.interval, 2)
            elif k in hour_counter.fields:
                row[k] = round(float(row[k]) / req_count, 2)

    data = []
    for h_row in hour_data:
        for h_aver_row in hour_aver_data:
            for d_aver_row in day_aver_data:
                if h_row['NAME'] == h_aver_row['NAME'] == d_aver_row['NAME']:
                    data.append(dict(hour=h_row, hour_aver=h_aver_row,
                                     day_aver=d_aver_row))

    sort_by_field = request.args.get('sort_by_field', 'REQUESTS')
    sort_by_period = request.args.get('sort_by_period', 'hour')
    get_sorting_key = lambda row: row[sort_by_period][sort_by_field]
    data = sorted(data, key=get_sorting_key, reverse=True)

    return render_template('main_page.html', data=data,
                           fields=hour_counter.fields,
                           sort_by_field=sort_by_field,
                           sort_by_period=sort_by_period)


@app.route('/add/')
def add_page():
    data = request.args.to_dict()

    for field in data:
        if field != 'NAME':
            data[field] = int(data[field])

    add_data(data)
    hour_counter.update()
    day_counter.update()
    return redirect('/')

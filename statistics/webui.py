from flask import render_template, redirect, request

from statistics import app, hour_counter, day_counter

@app.route("/")
def main_page():
    hour_data = hour_counter.get_vals()
    day_aver_data = day_counter.get_vals()
    hour_aver_data = hour_counter.get_vals()
    for row in hour_aver_data:
        req_count = row['REQUESTS']
        for k in row:
            if k in hour_counter.fields and k != "REQUESTS":
                row[k] = round(float(row[k])/req_count, 2)
    for row in day_aver_data:
        req_count = row['REQUESTS']
        for k in row:
            if k in hour_counter.fields and k != "REQUESTS":
                row[k] = round(float(row[k])/req_count, 2)
    data = []
    for h_row in hour_data:
        for h_aver_row in hour_aver_data:
            for d_aver_row in day_aver_data:
                if h_row['NAME'] == h_aver_row['NAME'] == d_aver_row['NAME']:
                    data += [dict(hour=h_row, hour_aver=h_aver_row, day_aver=d_aver_row)]
    sort_by_field = request.args.get('sort_by_field', None)
    sort_by_period = request.args.get('sort_by_period', None)
    if sort_by_field and sort_by_period:
        data = sorted(data, key=lambda row: row[sort_by_period][sort_by_field], reverse=True)
    return render_template("main_page.html", data=data, fields=hour_counter.fields)

@app.route("/add/")
def add_page():
    name = request.args.get('NAME')
    hour_counter.incrby_last(name, "REQUESTS", 1)
    day_counter.incrby_last(name, "REQUESTS", 1)
    for field in request.args:
        if field != "NAME":
            new_val = request.args.get(field, 0, int)
            hour_counter.incrby_last(name, field, new_val)
    for field in request.args:
        if field != "NAME":
            new_val = request.args.get(field, 0, int)
            day_counter.incrby_last(name, field, new_val)
    hour_counter.update()
    day_counter.update()
    return redirect("/")

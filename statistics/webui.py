from flask import render_template, redirect, request

from statistics import app, hour_counter, day_counter, fields

@app.route("/")
def main_page():
    data = hour_counter.get_vals()
    sort_by = request.args.get('sort_by', None)
    if sort_by:
        data = sorted(data, key=lambda row: row[sort_by])
    return render_template("main_page.html", data=data, fields=fields)

@app.route("/day_aver/")
def day_aver():
    data = day_counter.get_vals()
    for row in data:
        req_count = row['REQUESTS']
        for k in row:
            if k in fields and k != "REQUESTS":
                row[k] = float(row[k])/req_count
    return render_template("main_page.html", data=data, fields=fields)

@app.route("/hour_aver/")
def hour_aver():
    data = hour_counter.get_vals()
    for row in data:
        req_count = row['REQUESTS']
        for k in row:
            if k in fields and k != "REQUESTS":
                row[k] = float(row[k])/req_count
    return render_template("main_page.html", data=data, fields=fields)

@app.route("/add/")
def add_page():
    name = request.args.get('NAME')
    hour_counter.incrby_last(name, "REQUESTS", 1)
    day_counter.incrby_last(name, "REQUESTS", 1)
    for field in fields:
        new_val = int(request.args.get(field, '0'))
        hour_counter.incrby_last(name, field, new_val)
        day_counter.incrby_last(name, field, new_val)
    hour_counter.update()
    day_counter.update()
    return redirect("/")

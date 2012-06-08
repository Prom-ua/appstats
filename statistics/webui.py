from flask import render_template, g, redirect, request
from db import connect_db, get_all_sum, RedisDB

from statistics import app

@app.before_request
def before_request():
    g.db = RedisDB()
    g.fields = ["CPU", "TOTAL", "SQL", "SOLR", "REDIS", "MEMCACHED", "REQUESTS"]

@app.route("/")
def main_page():
    sort_by = request.args.get('sort_by', None)
    data = g.db.get_all('day')
    if sort_by:
        hour_data = sorted(data, key=lambda row: row[sort_by])
    return render_template("main_page.html", data=data)

@app.route("/day_aver/")
def average():
    data = g.db.get_all('day')
    for row in data:
        req_count = row['REQUESTS']
        for k in row:
            if k in g.fields and k != "REQUESTS":
                row[k] = float(row[k])/req_count
    return render_template("main_page.html", data=data)

@app.route("/hour_aver/")
def average():
    data = g.db.get_all('hour')
    for row in data:
        req_count = row['REQUESTS']
        for k in row:
            if k in g.fields and k != "REQUESTS":
                row[k] = float(row[k])/req_count
    return render_template("main_page.html", data=data)

@app.route("/add/")
def add_page():
    name = request.args.get('NAME')
    if name not in g.db:
        g.db.add_name(name, g.fields)
    for field in g.fields:
        new_val = int(request.args.get(field, '0'))
        old_val = g.db.get_value('min', name, field)
        new_val += old_val
        g.db.set_min_value(name, field, new_val)
    g.db.inc_field(name, "REQUESTS")
    return redirect("/")

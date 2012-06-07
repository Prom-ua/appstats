from flask import render_template, g, redirect, request
from db import connect_db, get_all_sum

from statistics import app

@app.before_request
def before_request():
    g.db = connect_db()
    g.fields = ["CPU", "TOTAL", "SQL", "SOLR", "REDIS", "MEMCACHED"]

@app.route("/")
def main_page():
    sort_by = request.args.get('sort_by', None)
    data = get_all_sum(g.db)
    if sort_by:
        data = sorted(data, key=lambda row: row[sort_by])
    return render_template("main_page.html", data=data)

@app.route("/average/")
def average():
    data = get_all_sum(g.db)
    for row in data:
        req_count = row['REQUESTS']
        for k in row:
            if k in g.fields:
                row[k] = float(row[k])/req_count
    return render_template("main_page.html", data=data)

@app.route("/add/")
def add_page():
    key = request.args.get('KEY')
    for field in g.fields:
        new_val = int(request.args.get(field, '0'))
        old_val = int(g.db.hget(key, field) or '0')
        new_val += old_val
        g.db.hset(key, field, new_val)
    g.db.hincrby(key, "REQUESTS", "1")
    return redirect("/")

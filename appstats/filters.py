# encoding: utf-8

import json


def json_filter(value):
    return json.dumps(value)


def count_filter(value):
    if value is None:
        return ""
    count = float(value)
    base = 1000
    prefixes = [
        ('K'),
        ('M'),
        ('G'),
        ('T'),
        ('P'),
        ('E'),
        ('Z'),
        ('Y')
    ]
    if count < base:
        return "%.1f" % count
    else:
        for i, prefix in enumerate(prefixes):
            unit = base ** (i + 2)
            if count < unit:
                return "%.1f %s" % ((base * count / unit), prefix)
        return "%.1f %s" % ((base * count / unit), prefix)


def time_filter(value):
    if value is None:
        return ""
    # Transform secs into microseconds
    time = float(value) * 1000000
    if time < 1000:
        return u"%d µs" % time
    else:
        time /= 1000
    if time < 1000:
        return "%.1f ms" % time
    else:
        time /= 1000
    if time < 60:
        return "%.1f s" % time
    else:
        time /= 60
    if time < 60:
        return "%.1f m" % time
    else:
        time /= 60
    if time < 24:
        return "%.1f h" % time
    else:
        time /= 24
        return "%.1f d" % time


def default_filter(value):
    if value is None:
        return ""
    return "%.1f" % float(value)


def pretty_hours_filter(value):
    hours = int(value)
    if hours == 1:
        return "1 hour"
    if hours <= 24:
        return "%u hours" % hours
    return "%u days" % (hours / 24)

# encoding: utf-8

import json


def json_filter(value):
    return json.dumps(value)


def count_filter(value):
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
        return '%.1f' % count
    else:
        for i, prefix in enumerate(prefixes):
            unit = base ** (i + 2)
            if count < unit:
                return '%.1f %s' % ((base * count / unit), prefix)
        return '%.1f %s' % ((base * count / unit), prefix)


def time_filter(value):
    time = float(value)
    if time < 1000:
        return '%.1f ms' % time
    else:
        time = time / 1000
    if time < 60:
        return '%.1f sec' % time
    else:
        time = time / 60
    if time < 60:
        return '%.1f min' % time
    else:
        time = time / 60
    if time < 24:
        return '%.1f hours' % time
    else:
        time = time / 24
        return'%.1f days' % time



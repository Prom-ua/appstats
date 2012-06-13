# encoding: utf-8

def add_data(data, counters):
    print data
    name = data['NAME']
    if not 'REQUESTS' in data:
        for counter in counters:
            counter.incrby(name, "REQUESTS", 1)
    for field in data:
        for counter in counters:
            if field != 'NAME':
                counter.incrby(name, field, data[field])

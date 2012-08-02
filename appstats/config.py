REDIS_HOST = '127.0.0.1'
REDIS_PORT = 6379
REDIS_DB = 0

MONGO_HOST = '127.0.0.1'
MONGO_PORT = 27017
MONGO_DB_NAME = 'appstats'

APP_IDS = [dict(key='prom.ua', name='Prom.ua'),
           dict(key='tiu.ru', name='Tiu.ru'),
           dict(key='deal.by', name='Deal.by')]

FIELDS = [
    dict(key='NUMBER',    name='NUMBER',  format=None,    visible=True),
    dict(key='cpu_time',  name='CPU',     format='time',  visible=True),
]

TIME_FIELDS = [
    dict(key='real_time',       name='TOTAL',   format='time',  visible=True),
    dict(key='memc:duration',   name='MEMC',    format='time',  visible=True),
    dict(key='redis:duration',  name='REDIS',   format='time',  visible=True),
    dict(key='solr:duration',   name='SOLR',    format='time',  visible=True),
    dict(key='sql:duration',    name='SQL',     format='time',  visible=True),
]

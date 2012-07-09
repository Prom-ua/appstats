UDP_PORT = 9001
UDP_HOST = '127.0.0.1'

REDIS_HOST = '127.0.0.1'
REDIS_PORT = 6379
REDIS_DB = 0

MONGO_HOST = '127.0.0.1'
MONGO_PORT = 27017
MONGO_DB_NAME = 'appstats'

APP_IDS = ['prom.ua', 'tiu.ru', 'deal.by']

# FIELDS = [{'key': 'example', 'name': 'EXAMPLE', 'format': 'time'}]
FIELDS = [dict(key='cpu_time', name='CPU', format='time'),
          dict(key='real_time', name='TOTAL', format='time'),
          dict(key='sql', name='SQL', format=None),
          dict(key='solr', name='SOLR', foramt=None),
          dict(key='redis', name='REDIS', format=None),
          dict(key='memcached', name='MEMCACHED', format=None)]

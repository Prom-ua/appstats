DEBUG = True
UDP_PORT = 9001
UDP_HOST = '127.0.0.1'

REDIS_HOST = '127.0.0.1'
REDIS_PORT = 6379

REDIS_KEYS_PREFIX = 'appstats'
FIELDS = ['cpu_time', 'real_time', 'sql', 'solr', 'redis', 'cache', 'memcached', 'NUMBER']

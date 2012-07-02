Install requirements:
    > pip install -r requirements.txt

Default settings:
    UDP_PORT = 9001
    UDP_HOST = '127.0.0.1'

    REDIS_HOST = '127.0.0.1'
    REDIS_PORT = 6379

    MONGO_HOST = '127.0.0.1'
    MONGO_PORT = 27017
    MONGO_DB_NAME = 'appstats'

    REDIS_KEYS_PREFIX = 'appstats'
    FIELDS = ['cpu_time', 'real_time', 'sql', 'solr', 'redis', 'memcached']

Settings files:
    1. path from environment variable 'APPSTATS_SETTINGS'
    2. /etc/appstats.cfg
    3. ~/.appstats.cfg

Run service:
    > gunicorn --daemon --workers=8 appstats.app:app.wsgi_app

Cron command:
    python /path/to/appstats/manage.py update

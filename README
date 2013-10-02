Install requirements:
    $ pip install -r requirements.txt

Default settings file: appstats/config.py

Settings files:
    1. path from environment variable 'APPSTATS_SETTINGS'
    2. /etc/appstats.cfg
    3. ~/.appstats.cfg

Run service:
    $ gunicorn --daemon --workers=8 appstats.app:app.wsgi_app

Cron command:
    */2 * * * * user python /path/to/appstats/manage.py update_cache -s 'apps'
    */2 * * * * user python /path/to/appstats/manage.py update_cache -s 'tasks'
    * * * * * user python /path/to/appstats/manage.py update_counters -s 'apps'
    * * * * * user python /path/to/appstats/manage.py update_counters -s 'tasks'

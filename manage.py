from flaskext.script import Manager

from statistics.app import app, hour_counter, day_counter


manager = Manager(app)

@manager.command
def update():
    hour_counter.update()
    day_counter.update()

if __name__ == '__main__':
    manager.run()

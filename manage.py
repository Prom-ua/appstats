from flaskext.script import Manager

from statistics import app

manager = Manager(app)

if __name__ == "__main__":
    manager.run()

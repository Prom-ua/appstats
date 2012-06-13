# encoding: utf-8

import daemon

from flaskext.script import Manager

from statistics.app import app, hour_counter, day_counter
from statistics.udp_server import UDPServer


manager = Manager(app)


@manager.command
def update():
    hour_counter.update()
    day_counter.update()


@manager.command
def run_udp_server():
    udp_server = UDPServer(
        host=app.config['UDP_HOST'],
        port=app.config['UDP_PORT']
    )
    with daemon.DaemonContext():
        udp_server.run()


if __name__ == '__main__':
    manager.run()

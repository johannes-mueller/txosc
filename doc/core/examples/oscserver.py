# Copyright (c) 2001-2006 Twisted Matrix Laboratories.
# See LICENSE for details.

""" Simple OSC server """

import sys
# FIXME - remove this dirty hack
sys.path.insert(0, ".")

from twisted.internet import reactor
from twisted.protocols import osc

if __name__ == "__main__":
    reactor.listenUDP(17777, osc.OscServerProtocol())

    reactor.run()
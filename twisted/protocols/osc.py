# -*- test-case-name: twisted.test.test_osc -*-
# Copyright (c) 2009 Alexandre Quessy, Arjan Scherpenisse
# See LICENSE for details.

"""
OSC 1.1 Protocol over UDP for Twisted.
http://opensoundcontrol.org/spec-1_1 
"""
import string
import math
import struct

from twisted.internet.protocol import DatagramProtocol
from twisted.internet import defer, reactor

class OscError(Exception):
    """
    Any error raised by this module.
    """
    pass


class Message(object):
    """
    OSC Message
    """

    def __init__(self, address, type_tags="", arguments=[]):
        self.address = address
        self.type_tags = type_tags
        self.arguments = arguments

    def toBinary(self):
        return StringArgument(self.address).toBinary() + "," + self.type_tags + "".join([a.toBinary() for a in self.arguments])


class Bundle(object):
    """
    OSC Bundle
    """
    def __init__(self, messages=[],  time_tag=None):
        self.messages = messages
        self.time_tag = time_tag
        if self.time_tag is None:
            pass
            #TODO create time tag
            pass


class Argument(object):
    """
    Base OSC argument
    """
    def __init__(self, value):
        self.value = value

    def toBinary(self):
        """
        Encode the value to binary form, ready to send over the wire.
        """
        raise NotImplemented('Override this method')


class BlobArgument(Argument):
    typeTag = "b"


class StringArgument(Argument):
    typeTag = "s"

    def toBinary(self):
        length = math.ceil((len(self.value)+1) / 4.0) * 4
        return struct.pack(">%ds" % (length), str(self.value))


class IntArgument(Argument):
    typeTag = "i"

    def toBinary(self):
        return struct.pack(">i", int(self.value))


class LongArgument(Argument):
    typeTag = None # FIXME

    def toBinary(self):
        return struct.pack('>l', long(self.value))


class FloatArgument(Argument):
    typeTag = "f"

    def toBinary(self):
        return struct.pack(">f", float(self.value))


class DoubleArgument(FloatArgument):
    typeTag = None # FIXME


class TimeTagArgument(Argument):
    typeTag = "t"

    def toBinary(self):
        fr, sec = math.modf(self.value)
        return struct.pack('>ll', long(sec), long(fr * 1e9))



class SymbolArgument(Argument):
    pass
    #FIXME: what is that?

#global dicts
_types = {
    float: FloatArgument,
    str: StringArgument,
    int: IntArgument,
    long: LongArgument,
    unicode: StringArgument,
    #TODO : more types
    }


_tags = {
    "b": BlobArgument,
    "f": FloatArgument,
    "i": IntArgument,
    "s": StringArgument,
    #TODO : more types
    }

def createArgument(data, type_tag=None):
    """
    Creates an OSC argument, trying to guess its type if no type is given.

    Factory of *Attribute object.
    :param data: Any Python base type.
    :param type_tag: One-letter string. Either "i", "f", etc.
    """
    global _types
    global _tags
    kind = type(data)
    try:
        if type_tag in _tags.keys():
            return _tags[type_tag](data)
        if kind in _types.keys():
            return _types[kind](data)
        else:
            raise OscError("Data %s")
    except ValueError, e:
        raise OscError("Could not cast %s to %s. %s" % (data, type_tag, e.message))

def _readString(data):
    """
    Parses binary data to get the first string in it.
    
    Returns a tuple with string, leftover.
    The leftover should be parsed next.
    :rettype: tuple

    OSC-string A sequence of non-null ASCII characters followed by a null, 
    followed by 0-3 additional null characters to make the total number of bits a multiple of 32.
    """
    null_pos = string.find(data, "\0") # find the first null char
    s = data[0:null_pos] # get the first string out of data
    i = null_pos # find the position of the beginning of the next data
    i = i + (4 - (i % 4)) # considering that all data must have a size of a multiple of 4 chars.
    leftover = data[i:]
    return (s, leftover)

class OscProtocol(DatagramProtocol):
    """
    The OSC server protocol
    """
    def datagramReceived(self, data, (host, port)):
        #The contents of an OSC packet must be either an OSC Message or an OSC Bundle. The first byte of the packet's contents unambiguously distinguishes between these two alternatives.
        packet_type = data[0] # TODO
        print "received %r from %s:%d" % (data, host, port)
        osc_address, leftover = _readString(data)
        print("Got OSC address: %s" % (osc_address))
        #self.transport.write(data, (host, port))


class OscClientProtocol(DatagramProtocol):
     def __init__(self, onStart):
         self.onStart = onStart

     def startProtocol(self):
         self.onStart.callback(self)


class OscSender(object):
     def __init__(self):
         d = defer.Deferred()
         def listening(proto):
             self.proto = proto
         d.addCallback(listening)
         self._port = reactor.listenUDP(0, OscClientProtocol(d))

     def send(self, msg, (host, port)):
         data = msg.toBinary()
         self.proto.transport.write(data, (host, port))

     def stop(self):
         self._call.stop()
         self._port.stopListening()


# TODO: move to doc/core/examples/oscserver.py
if __name__ == "__main__":
    reactor.listenUDP(17777, OscProtocol())

    ds = OscSender()
    ds.send(Message("/foo"), ("127.0.0.1", 17777))

    reactor.run()
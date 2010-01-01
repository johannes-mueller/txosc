# -*- test-case-name: twisted.test.test_osc -*-
# Copyright (c) 2009 Alexandre Quessy, Arjan Scherpenisse
# See LICENSE for details.

"""
OSC 1.1 Protocol over UDP for Twisted.
Specification : http://opensoundcontrol.org/spec-1_1
Examples : http://opensoundcontrol.org/spec-1_0-examples
"""
import string
import math
import struct
import time
import fnmatch

from twisted.internet.protocol import DatagramProtocol
from twisted.internet import reactor
from twisted.internet import defer

def _ceilToMultipleOfFour(num):
    """
    Rounds a number to the closest higher number that is a mulitple of four.
    That is for data that need to be padded with zeros so that the length of their data
    must be a multiple of 32 bits.
    """
    #return math.ceil((num + 1) / 4.0) * 4
    return num + (4 - (num % 4)) 

class OscError(Exception):
    """
    Any error raised by this module.
    """
    pass

def binary_print(s):
    print " ".join(["%02x" % ord(c) for c in s])

class Message(object):
    """
    An OSC Message.
    """
    address = None
    arguments = None

    def __init__(self, address, *arguments):
        self.address = address
        self.arguments = list(arguments)


    def toBinary(self):
        return StringArgument(self.address).toBinary() + StringArgument("," + self.getTypeTags()).toBinary() + "".join([a.toBinary() for a in self.arguments])


    def getTypeTags(self):
        """
        :rettype: string
        """
        return "".join([a.typeTag for a in self.arguments])


    def add(self, value):
        """
        Add an argument with given value, using L{createArgument}.
        """
        self.arguments.append(createArgument(value))


    @staticmethod
    def fromBinary(data):
        osc_address, leftover = stringFromBinary(data)
        #print("Got OSC address: %s" % (osc_address))
        message = Message(osc_address)
        type_tags, leftover = stringFromBinary(leftover)

        if type_tags[0] != ",":
            # invalid type tag string
            raise OscError("Invalid typetag string: %s" % type_tags)

        for type_tag in type_tags[1:]:
            arg, leftover = createArgumentFromBinary(type_tag, leftover)
            message.arguments.append(arg)

        return message, leftover


    def __str__(self):
        args = " ".join([str(a) for a in self.arguments])
        return "%s ,%s %s" % (self.address, self.getTypeTags(), args)


    def __eq__(self, other):
        if self.address != other.address:
            return False
        if self.getTypeTags() != other.getTypeTags():
            return False
        if len(self.arguments) != len(other.arguments):
            return False
        for i in range(len(self.arguments)):
            if self.arguments[i].value != other.arguments[i].value:
                return False
        return True

    def __ne__(self, other):
        return not (self == other)


class Bundle(object):
    """
    OSC Bundle
    """
    def __init__(self, messages=[],  time_tag=0):
        self.messages = messages[:]
        self.time_tag = time_tag
        if self.time_tag is None:
            pass
            #TODO create time tag

    def toBinary(self):
        data = "#bundle"
        data += TimeTagArgument(self.time_tag).toBinary()
        for msg in self.messages:
            binary = msg.toBinary()
            data += IntArgument(len(binary)).toBinary()
            data += binary
        return data


    def __eq__(self, other):
        if len(self.messages) != len(other.messages):
            return False
        for i in range(len(self.messages)):
            if self.messages[i] != other.messages[i]:
                return False
        return True

    def __ne__(self, other):
        return not (self == other)


class Argument(object):
    """
    Base OSC argument
    """
    typeTag = None  # Must be implemented in children classes

    def __init__(self, value):
        self.value = value


    def toBinary(self):
        """
        Encode the value to binary form, ready to send over the wire.
        """
        raise NotImplemented('Override this method')


    @staticmethod
    def fromBinary(data):
        """
        Decode the value from binary form. Result is a tuple of (Instance, leftover).
        """
        raise NotImplemented('Override this method')

    def __str__(self):
        return "%s:%s " % (self.typeTag, self.value)

#
# OSC 1.1 required arguments
#

class BlobArgument(Argument):
    typeTag = "b"

    def toBinary(self):
        sz = len(self.value)
        #length = math.ceil((sz+1) / 4.0) * 4
        length = _ceilToMultipleOfFour(sz)
        return struct.pack(">i%ds" % (length), sz, str(self.value))
    
    @staticmethod
    def fromBinary(data):
        try:
            length = struct.unpack(">i", data[0:4])[0]
            index_of_leftover = _ceilToMultipleOfFour(length) + 4
            try:
                blob_data = data[4:length + 4]
            except IndexError, e:
                raise OscError("Not enough bytes to find size of a blob of size %s in %s." % (length, data))
        except IndexError, e:
            raise OscError("Not enough bytes to find size of a blob argument in %s." % (data))
        leftover = data[index_of_leftover:]
        return BlobArgument(blob_data), leftover
        


class StringArgument(Argument):
    typeTag = "s"

    def toBinary(self):
        length = math.ceil((len(self.value)+1) / 4.0) * 4
        return struct.pack(">%ds" % (length), str(self.value))

    @staticmethod
    def fromBinary(data):
        """
        Parses binary data to get the first string in it.

        Returns a tuple with string, leftover.
        The leftover should be parsed next.
        :rettype: tuple

        OSC-string A sequence of non-null ASCII characters followed by a null, 
            followed by 0-3 additional null characters to make the total number of bits a multiple of 32.
        """
        value, leftover = stringFromBinary(data)
        return StringArgument(value), leftover


class IntArgument(Argument):
    typeTag = "i"

    def toBinary(self):
        if self.value >= 1<<31:
            raise OverflowError("Integer too large: %d" % self.value)
        if self.value < -1<<31:
            raise OverflowError("Integer too small: %d" % self.value)
        return struct.pack(">i", int(self.value))

    @staticmethod
    def fromBinary(data):
        try:
            i = struct.unpack(">i", data[:4])[0]
            leftover = data[4:]
        except IndexError, e:
            raise OscError("Too few bytes left to get an int from %s." % (data))
            #FIXME: do not raise error and return leftover anyways ?
        return IntArgument(i), leftover


class FloatArgument(Argument):
    typeTag = "f"

    def toBinary(self):
        return struct.pack(">f", float(self.value))

    @staticmethod
    def fromBinary(data):
        try:
            f = struct.unpack(">f", data[:4])[0]
            leftover = data[4:]
        except IndexError, e:
            raise OscError("Too few bytes left to get a float from %s." % (data))
            #FIXME: do not raise error and return leftover anyways ?
        return FloatArgument(f), leftover


class TimeTagArgument(Argument):
    """
    Time tags are represented by a 64 bit fixed point number. The first 32 bits specify the number of seconds since midnight on January 1, 1900, and the last 32 bits specify fractional parts of a second to a precision of about 200 picoseconds. This is the representation used by Internet NTP timestamps. 

    The time tag value consisting of 63 zero bits followed by a one in the least signifigant bit is a special case meaning "immediately."
    """
    typeTag = "t"
    SECONDS_UTC_TO_UNIX_EPOCH = 2208988800

    def __init__(self, value=None):
        # TODO: call parent's constructor ?
        if value is None:
            #FIXME: is that the correct NTP timestamp ?
            value = self.SECONDS_UTC_TO_UNIX_EPOCH + time.time()
        self.value = value

    def toBinary(self):
        fr, sec = math.modf(self.value)
        return struct.pack('>ll', long(sec), long(fr * 1e9))

    @staticmethod
    def fromBinary(data):
        high, low = struct.unpack(">ll", data[0:8])
        leftover = data[8:]
        time = float(int(high) + low / float(1e9))
        return TimeTagArgument(time), leftover


class BooleanArgument(Argument):
    def __init__(self, value):
        Argument.__init__(self, value)
        if self.value:
            self.typeTag = "T"
        else:
            self.typeTag = "F"

    def toBinary(self):
        return "" # bool args do not have data, just a type tag



class DatalessArgument(Argument):
    """
    An argument whose value is defined just by its type tag.
    """
    typeTag = None # override in subclass
    value = None # override in subclass

    def __init__(self):
        Argument.__init__(self, self.value)

    def toBinary(self):
        return ""

class NullArgument(DatalessArgument):
    typeTag = "N"
    value = None

class ImpulseArgument(DatalessArgument):
    typeTag = "I"
    value = True

#
# Optional arguments
#
# Should we implement all types that are listed "optional" in
# http://opensoundcontrol.org/spec-1_0 ?

#class SymbolArgument(StringArgument):
#    typeTag = "S"


#global dicts
_types = {
    float: FloatArgument,
    str: StringArgument,
    int: IntArgument,
    bool: BooleanArgument
    #TODO: unicode?: StringArgument,
    #TODO : more types
    }

_tags = {
    "b": BlobArgument,
    "f": FloatArgument,
    "i": IntArgument,
    "s": StringArgument,
    #TODO : more types
    }


def createArgument(value, type_tag=None):
    """
    Creates an OSC argument, trying to guess its type if no type is given.

    Factory of *Attribute object.
    :param data: Any Python base type.
    :param type_tag: One-letter string. Either "i", "f", etc.
    """
    global _types
    global _tags
    kind = type(value)

    if type_tag:
        # Get the argument type based on given type tag
        if type_tag == "T":
            return BooleanArgument(True)
        if type_tag == "F":
            return BooleanArgument(False)
        if type_tag == "N":
            return NullArgument()
        if type_tag == "I":
            return ImpulseArgument()

        if type_tag in _tags.keys():
            return _tags[type_tag](value)

        raise OscError("Unknown type tag: %s" % type)

    else:
        # Guess the argument type based on the type of the value
        if kind in _types.keys():
            return _types[kind](value)

        raise OscError("No OSC argument type for %s (value = %s)" % (kind, value))


def createArgumentFromBinary(type_tag, data):
    if type_tag == "T":
        return BooleanArgument(True), data
    if type_tag == "F":
        return BooleanArgument(False), data
    if type_tag == "N":
        return NullArgument(), data
    if type_tag == "I":
        return ImpulseArgument(), data

    global _tags
    if type_tag not in _tags:
        raise OscError("Invalid typetag: %s" % type_tag)

    return _tags[type_tag].fromBinary(data)


def stringFromBinary(data):
    null_pos = string.find(data, "\0") # find the first null char
    value = data[0:null_pos] # get the first string out of data
    # find the position of the beginning of the next data
    leftover = data[_ceilToMultipleOfFour(null_pos):]
    return value, leftover



class AddressSpace(object):
    """
    Adding/removing OSC handlers callbacks utility.

    Callbacks are stored in a tree-like structure.
    """

    def __init__(self):
        # TODO: implement as a tree of sets or a big dict?
        self.root = AddressNode()


    def addCallback(self, pattern, callable, typeTags=None):
        
        path = self._patternPath(pattern)
        return self.root.addCallback(path, callable)

        
    def removeCallback(self, pattern, callable):
        """
        :rettype: -> None
        """
        path = self._patternPath(pattern)
        return self.root.removeCallback(path, callable)


    def removeAllCallbacks(self, pattern):
        """
        :rettype: -> None
        """
        raise NotImplementedError("AddressSpace is in progress.")


    def matchCallbacks(self, message):
        """
        Get all callbacks for a given message
        """
        pattern = message.address
        return self.getCallbacks(pattern)


    def getCallbacks(self, pattern):
        """
        Retrieve all callbacks which are bound to given
        pattern. Returns a set() of callables.
        """
        path = self._patternPath(pattern)
        nodes = self.root.match(path)
        if not nodes:
            return nodes
        return reduce(lambda a, b: a.union(b), [n.callbacks for n in nodes])


    def dispatch(self, Message, clientAddress):
        """
        Executes every callback matching the message address with Message as argument. 
        (and not only its arguments) 
        The order in which the callbacks are called in undefined.
        -> None
        """
        raise NotImplementedError("AddressSpace is in progress.")


    def _messagePath(self, message):
        """
        Given an L{osc.Message}, return the path split up in components.
        """
        return self._patternPath(message.address)


    def _patternPath(self, pattern):
        """
        Given a OSC address path like /foo/bar, return a list of
        ['foo', 'bar']. Note that an OSC address always starts with a
        slash.
        """
        return pattern.split("/")[1:]



class AddressNode(object):
    def __init__(self):
        self.childNodes = {}
        self.callbacks = set()
        self.parent = None
        self.wildcardNodes = set()

    def match(self, path, matchAllChilds = False):
        if not len(path) or matchAllChilds:
            c = set([self])
            if matchAllChilds and self.childNodes:
                c = c.union(reduce(lambda a, b: a.union(b), [n.match(path, True) for n in self.childNodes.values()]))
            return c

        matchedNodes = set()

        part = path[0]
        if AddressNode.isWildcard(part):
            for c in self.childNodes:
                if AddressNode.matchesWildcard(c, part):
                    matchedNodes.add( (self.childNodes[c], part[-1] == "*") )
            # FIXME - what if both the part and some of my childs have wildcards?
        elif self.wildcardNodes:
            matches = set()
            for c in self.wildcardNodes:
                if AddressNode.matchesWildcard(part, c):
                    all = c[-1] == "*" and not self.childNodes[c].childNodes
                    matchedNodes.add( (self.childNodes[c], all) )
                    break
        if part in self.childNodes:
            matchedNodes.add( (self.childNodes[part], False) )

        if not matchedNodes:
            return matchedNodes
        return reduce(lambda a, b: a.union(b), [n.match(path[1:], all) for n, all in matchedNodes])

    def addCallback(self, path, cb):
        if not len(path):
            self.callbacks.add(cb)
        else:
            part = path[0]
            if part not in self.childNodes:
                if not AddressNode.isValidAddressPart(part):
                    raise ValueError("Invalid address part: '%s'" % part)
                self.childNodes[part] = AddressNode()
                if AddressNode.isWildcard(part):
                    self.wildcardNodes.add(part)
            self.childNodes[part].addCallback(path[1:], cb)

    def removeCallback(self, path, cb):
        if not len(path):
            self.callbacks.remove(cb)
        else:
            part = path[0]
            if part not in self.childNodes:
                raise KeyError("No such address part: " + part)
            self.childNodes[part].removeCallback(path[1:], cb)
            if not self.childNodes[part].callbacks and not self.childNodes[part].childNodes:
                # remove child
                if part in self.wildcardNodes:
                    self.wildcardNodes.remove(part)
                del self.childNodes[part]

    @staticmethod
    def isWildcard(part):
        wildcardChars = set("*?[]{}")
        return len(set(part).intersection(wildcardChars)) > 0

    @staticmethod
    def isValidAddressPart(part):
        invalidChars = set(" #,/")
        return len(set(part).intersection(invalidChars)) == 0

    @staticmethod
    def matchesWildcard(value, wildcard):
        if value == wildcard and not AddressNode.isWildcard(wildcard):
            return True
        if wildcard == "*":
            return True

        return fnmatch.fnmatchcase(value, wildcard)


class OscServerProtocol(DatagramProtocol):
    """
    The OSC server protocol
    """
    def datagramReceived(self, data, (host, port)):
        #The contents of an OSC packet must be either an OSC Message or an OSC Bundle. The first byte of the packet's contents unambiguously distinguishes between these two alternatives.
        #packet_type = data[0] # TODO
        print("received %r from %s:%d" % (data, host, port))
        #TODO : check if it is a #bundle
        message, leftover = Message.fromBinary(data)
        self.messageReceived(message)

    def messageReceived(self, message):
        print "Message received: [%s]" % message



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
    reactor.listenUDP(17777, OscServerProtocol())

    ds = OscSender()
    ds.send(Message("/foo"), ("127.0.0.1", 17777))
    ds.send(Message("/foo", StringArgument("bar")), ("127.0.0.1", 17777))

    reactor.run()

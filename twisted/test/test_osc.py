# Copyright (c) 2009 Alexandre Quessy, Arjan Scherpenisse
# See LICENSE for details.

"""
OSC tests.

Maintainer: Arjan Scherpenisse
"""

from twisted.trial import unittest
from twisted.internet import reactor, defer
from twisted.protocols import osc

class TestBlobArgument(unittest.TestCase):
    """
    Encoding and decoding of a string argument.
    """
    def testToBinary(self):
        self.assertEqual(osc.BlobArgument("").toBinary(), "\0\0\0\0\0\0\0\0")
        self.assertEqual(osc.BlobArgument("a").toBinary(), "\0\0\0\1a\0\0\0")
        self.assertEqual(osc.BlobArgument("hi").toBinary(), "\0\0\0\2hi\0\0")
        self.assertEqual(osc.BlobArgument("hello").toBinary(), "\0\0\0\5hello\0\0\0")

    def testFromBinary(self):
        data = "\0\0\0\2hi\0\0\0\0\0\5hello\0\0\0"
        first, leftover = osc.BlobArgument.fromBinary(data)
        self.assertEqual(first.value, "hi")
        self.assertEqual(leftover, "\0\0\0\5hello\0\0\0")

        second, leftover = osc.BlobArgument.fromBinary(leftover)
        self.assertEqual(second.value, "hello")
        self.assertEqual(leftover, "")


class TestStringArgument(unittest.TestCase):
    """
    Encoding and decoding of a string argument.
    """
    def testToBinary(self):
        self.assertEqual(osc.StringArgument("").toBinary(), "\0\0\0\0")
        self.assertEqual(osc.StringArgument("OSC").toBinary(), "OSC\0")
        self.assertEqual(osc.StringArgument("Hello").toBinary(), "Hello\0\0\0")

    def testFromBinary(self):
        data = "aaa\0bb\0\0c\0\0\0dddd"
        first, leftover = osc.StringArgument.fromBinary(data)
        #padding with 0 to make strings length multiples of 4 chars
        self.assertEqual(first.value, "aaa")
        self.assertEqual(leftover, "bb\0\0c\0\0\0dddd")

        second, leftover = osc.StringArgument.fromBinary(leftover)
        self.assertEqual(second.value, "bb")
        self.assertEqual(leftover, "c\0\0\0dddd")

        third, leftover = osc.StringArgument.fromBinary(leftover)
        self.assertEqual(third.value, "c")
        self.assertEqual(leftover, "dddd")

class TestFloatArgument(unittest.TestCase):

    def testToAndFromBinary(self):
        binary = osc.FloatArgument(3.14159).toBinary()
        float_arg = osc.FloatArgument.fromBinary(binary)[0]
        #FIXME: how should we compare floats? use decimal?
        if float_arg.value < 3.1415:
            self.fail("value is too small")
        if float_arg.value > 3.1416:
            self.fail("value is too big")

class TestIntArgument(unittest.TestCase):

    def testToAndFromBinary(self):
        def test(value):
            int_arg = osc.IntArgument.fromBinary(osc.IntArgument(value).toBinary())[0]
            self.assertEqual(int_arg.value, value)
        test(0)
        test(1)
        test(-1)
        test(1<<31-1)
        test(-1<<31)

    def testIntOverflow(self):
        self.assertRaises(OverflowError, osc.IntArgument(1<<31).toBinary)
        self.assertRaises(OverflowError, osc.IntArgument((-1<<31) - 1).toBinary)


class TestTimeTagArgument(unittest.TestCase):
    def testToBinary(self):
        # 1 second since Jan 1, 1900
        arg = osc.TimeTagArgument(1)
        binary = arg.toBinary()
        self.assertEqual(binary, "\0\0\0\1\0\0\0\0")

    def testFromBinary(self):
        # 1 second since Jan 1, 1900
        val = osc.TimeTagArgument.fromBinary("\0\0\0\1\0\0\0\0")[0].value
        self.assertEqual(val, 1.0)

    def testToAndFromBinary(self):
        # 1 second since Jan 1, 1900
        def test(value):
            timetag_arg, leftover = osc.TimeTagArgument.fromBinary(osc.TimeTagArgument(value).toBinary())
            self.assertEqual(leftover, "")
            #self.assertEqual(value, timetag_arg.value)
            # time tags should not differ more than 200 picoseconds
            delta = 200 * (10 ** -12)
            self.assertTrue(abs(value - timetag_arg.value) <= delta, "Timetag precision")

        test(1.0)
        #test(1.101)

    #testFromBinary.skip = "TimeTagArgument.fromBinary is not yet implemented"


class TestMessage(unittest.TestCase):

    def testEquality(self):
        m = osc.Message("/example")

        m2 = osc.Message("/example")
        self.assertEqual(m, m2)
        m2 = osc.Message("/example2")
        self.assertNotEqual(m, m2)
        m2 = osc.Message("/example", osc.IntArgument(1))
        self.assertNotEqual(m, m2)
        m = osc.Message("/example", osc.IntArgument(1))
        self.assertEqual(m, m2)


    def testGetTypeTag(self):
        m = osc.Message("/example")
        self.assertEqual(m.getTypeTags(), "")
        m.arguments.append(osc.StringArgument("egg"))
        self.assertEqual(m.getTypeTags(), "s")
        m.arguments.append(osc.StringArgument("spam"))
        self.assertEqual(m.getTypeTags(), "ss")

    def testToAndFromBinary(self):

        def test(m):
            binary = m.toBinary()
            m2, leftover = osc.Message.fromBinary(binary)
            self.assertEqual(leftover, "")
            self.assertEqual(m, m2)

        test(osc.Message("/example"))
        test(osc.Message("/example", osc.StringArgument("hello")))
        test(osc.Message("/example", osc.IntArgument(1), osc.IntArgument(2), osc.IntArgument(-1)))
        test(osc.Message("/example", osc.BooleanArgument(True)))
        test(osc.Message("/example", osc.BooleanArgument(False), osc.NullArgument(), osc.StringArgument("hello")))


class TestBundle(unittest.TestCase):

    def testEquality(self):
        b = osc.Bundle()
        b2 = osc.Bundle()
        self.assertEqual(b, b2)
        b2.add(osc.Message("/hello"))
        self.assertNotEqual(b, b2)
        b.add(osc.Message("/hello"))
        self.assertEqual(b, b2)

    def testToAndFromBinary(self):
        def test(b):
            binary = b.toBinary()
            b2, leftover = osc.Bundle.fromBinary(binary)
            self.assertEqual(leftover, "")
            self.assertEqual(b, b2)

        test(osc.Bundle())
        test(osc.Bundle([osc.Message("/foo")]))
        test(osc.Bundle([osc.Message("/foo"), osc.Message("/bar")]))
        test(osc.Bundle([osc.Message("/foo"), osc.Message("/bar", osc.StringArgument("hello"))]))

        nested = osc.Bundle([osc.Message("/hello")])
        test(osc.Bundle([nested, osc.Message("/foo")]))

    def testGetMessages(self):

        m1 = osc.Message("/foo")
        m2 = osc.Message("/bar")
        m3 = osc.Message("/foo/baz")

        b = osc.Bundle()
        b.add(m1)
        self.assertEqual(b.getMessages(), set([m1]))

        b = osc.Bundle()
        b.add(m1)
        b.add(m2)
        self.assertEqual(b.getMessages(), set([m1, m2]))

        b = osc.Bundle()
        b.add(m1)
        b.add(osc.Bundle([m2]))
        b.add(osc.Bundle([m3]))
        self.assertEqual(b.getMessages(), set([m1, m2, m3]))



class TestAddressNode(unittest.TestCase):
    """
    Test the L{osc.AddressNode}; adding/removing/dispatching callbacks, wildcard matching.
    """

    def testAddRemoveCallback(self):

        def callback(m):
            pass
        n = osc.AddressNode()
        n.addCallback("/foo", callback)
        self.assertEqual(n.getCallbacks("/foo"), set([callback]))
        n.removeCallback("/foo", callback)
        self.assertEqual(n.getCallbacks("/foo"), set())


    def testRemoveAllCallbacks(self):

        def callback(m):
            pass
        def callback2(m):
            pass
        def callback3(m):
            pass
        n = osc.AddressNode()
        n.addCallback("/foo", callback)
        self.assertEqual(n.getCallbacks("/*"), set([callback]))
        n.removeAllCallbacks("/*")
        self.assertEqual(n.getCallbacks("/*"), set())

        n = osc.AddressNode()
        n.addCallback("/foo", callback)
        n.addCallback("/foo/bar", callback2)
        n.removeAllCallbacks("/foo")
        self.assertEqual(n.getCallbacks("/*"), set([callback2]))


    def testAddInvalidCallback(self):
        n = osc.AddressNode()
        self.assertRaises(ValueError, n.addCallback, "/foo bar/baz", lambda m: m)
        self.assertEqual(n.addCallback("/foo/*/baz", lambda m: m), None)


    def testRemoveNonExistingCallback(self):
        n = osc.AddressNode()
        self.assertRaises(KeyError, n.removeCallback, "/foo", lambda m: m)

    def testMatchExact(self):

        def callback(m):
            pass
        n = osc.AddressNode()
        n.addCallback("/foo", callback)

        self.assertEqual(n.matchCallbacks(osc.Message("/foo")), set([callback]))
        self.assertEqual(n.matchCallbacks(osc.Message("/bar")), set())

    def testMatchCallbackWildcards(self):

        def callback(m):
            pass
        n = osc.AddressNode()
        n.addCallback("/foo/*", callback)

        self.assertEqual(n.matchCallbacks(osc.Message("/foo")), set())
        self.assertEqual(n.matchCallbacks(osc.Message("/foo/bar")), set([callback]))
        self.assertEqual(n.matchCallbacks(osc.Message("/bar")), set())
        self.assertEqual(n.matchCallbacks(osc.Message("/foo/bar/baz")), set([callback]))

        n = osc.AddressNode()
        n.addCallback("/*", callback)
        self.assertEqual(n.matchCallbacks(osc.Message("/")), set([callback]))
        self.assertEqual(n.matchCallbacks(osc.Message("/foo/bar")), set([callback]))

        n = osc.AddressNode()
        n.addCallback("/*/baz", callback)
        self.assertEqual(n.matchCallbacks(osc.Message("/foo/bar")), set())
        self.assertEqual(n.matchCallbacks(osc.Message("/foo/baz")), set([callback]))

    def testMatchCallbackRangeWildcards(self):

        def callback1(m): pass
        def callback2(m): pass
        n = osc.AddressNode()
        n.addCallback("/foo1", callback1)
        n.addCallback("/foo2", callback2)

        self.assertEqual(n.matchCallbacks(osc.Message("/foo[1]")), set([callback1]))
        self.assertEqual(n.matchCallbacks(osc.Message("/foo[1-10]")), set([callback1, callback2]))
        self.assertEqual(n.matchCallbacks(osc.Message("/foo[4-6]")), set([]))
    testMatchCallbackRangeWildcards.skip = "Range matching"

    def testMatchMessageWithWildcards(self):

        def fooCallback(m):
            pass
        def barCallback(m):
            pass
        def bazCallback(m):
            pass
        def foobarCallback(m):
            pass
        n = osc.AddressNode()
        n.addCallback("/foo", fooCallback)
        n.addCallback("/bar", barCallback)
        n.addCallback("/baz", bazCallback)
        n.addCallback("/foo/bar", foobarCallback)

        self.assertEqual(n.matchCallbacks(osc.Message("/*")), set([fooCallback, barCallback, bazCallback, foobarCallback]))
        self.assertEqual(n.matchCallbacks(osc.Message("/spam")), set())
        self.assertEqual(n.matchCallbacks(osc.Message("/ba*")), set([barCallback, bazCallback]))
        self.assertEqual(n.matchCallbacks(osc.Message("/b*r")), set([barCallback]))
        self.assertEqual(n.matchCallbacks(osc.Message("/ba?")), set([barCallback, bazCallback]))


    def testMatchMessageWithRange(self):

        def firstCallback(m):
            pass
        def secondCallback(m):
            pass
        n = osc.AddressNode()
        n.addCallback("/foo/1", firstCallback)
        n.addCallback("/foo/2", secondCallback)

        self.assertEqual(n.matchCallbacks(osc.Message("/baz")), set())
        self.assertEqual(n.matchCallbacks(osc.Message("/foo/[1-2]")), set([firstCallback, secondCallback]))
    testMatchMessageWithRange.skip = "Range matching"


    def testWildcardMatching(self):
        self.assertTrue(osc.AddressNode.matchesWildcard("foo", "foo"))
        self.assertTrue(osc.AddressNode.matchesWildcard("foo", "*"))
        self.assertFalse(osc.AddressNode.matchesWildcard("foo", "bar"))
        self.assertTrue(osc.AddressNode.matchesWildcard("foo", "f*"))
        self.assertTrue(osc.AddressNode.matchesWildcard("foo", "f?o"))
        self.assertTrue(osc.AddressNode.matchesWildcard("foo", "fo?"))
        self.assertTrue(osc.AddressNode.matchesWildcard("fo", "f*o"))
        self.assertTrue(osc.AddressNode.matchesWildcard("foo", "f*o"))

    def testWildcardRangeMatching(self):
        self.assertTrue(osc.AddressNode.matchesWildcard("bar1", "bar[1-3]"))
        self.assertTrue(osc.AddressNode.matchesWildcard("bar23", "bar[20-30]"))
        self.assertFalse(osc.AddressNode.matchesWildcard("bar4", "bar[1-3]"))
    testWildcardRangeMatching.skip = "Range matching"


    def testAddressNodeNesting(self):

        def cb():
            pass
        child = osc.AddressNode()
        child.addCallback("/bar", cb)

        parent = osc.AddressNode()
        parent.addNode("foo", child)

        self.assertEqual(parent.getCallbacks("/foo/bar"), set([cb]))
        self.assertEqual(parent.getCallbacks("/foo/b*"), set([cb]))
        self.assertEqual(parent.getCallbacks("/foo/baz"), set())

    def testAddressNodeNestingMultiple(self):

        class MyNode(osc.AddressNode):
            def __init__(self):
                osc.AddressNode.__init__(self)
                self.addCallback("/trigger", self.trigger)

            def trigger(self):
                pass

        c1 = MyNode()
        c2 = MyNode()
        parent = osc.AddressNode()
        parent.addNode("foo", c1)
        parent.addNode("bar", c2)

        self.assertEqual(parent.getCallbacks("/foo/*"), set([c1.trigger]))
        self.assertEqual(parent.getCallbacks("/bar/*"), set([c2.trigger]))
        self.assertEqual(parent.getCallbacks("/*/trigger"), set([c1.trigger, c2.trigger]))


    def testAddressNodeRenaming(self):

        def cb():
            pass
        child = osc.AddressNode()
        child.addCallback("/bar", cb)

        parent = osc.AddressNode()
        parent.addNode("foo", child)

        self.assertEqual(parent.getCallbacks("/foo/bar"), set([cb]))
        child.setName("bar")
        self.assertEqual(parent.getCallbacks("/bar/bar"), set([cb]))


    def testAddressNodeReparenting(self):

        def cb():
            pass
        child = osc.AddressNode()
        child.addCallback("/bar", cb)

        baz = osc.AddressNode()

        parent = osc.AddressNode()
        parent.addNode("foo", child)
        parent.addNode("baz", baz) # empty node

        self.assertEqual(parent.getCallbacks("/foo/bar"), set([cb]))
        child.setParent(baz)
        self.assertEqual(parent.getCallbacks("/foo/bar"), set([]))
        self.assertEqual(parent.getCallbacks("/baz/foo/bar"), set([cb]))



class TestReceiver(unittest.TestCase):
    """
    Test the L{osc.Receiver} class.
    """

    def testDispatching(self):

        hello = osc.Message("/hello")
        there = osc.Message("/there")
        addr = ("0.0.0.0", 17777)

        def cb(message, a):
            self.assertEqual(message, hello)
            self.assertEqual(addr, a)
            state['cb'] = True
        def cb2(message, a):
            self.assertEqual(message, there)
            self.assertEqual(addr, a)
            state['cb2'] = True

        recv = osc.Receiver()
        recv.addCallback("/hello", cb)
        recv.addCallback("/there", cb2)

        state = {}
        recv.dispatch(hello, addr)
        self.assertEqual(state, {'cb': True})

        state = {}
        recv.dispatch(osc.Bundle([hello, there]), addr)
        self.assertEqual(state, {'cb': True, 'cb2': True})


class TestSenderAndReceiver(unittest.TestCase):
    """
    Test the L{osc.Sender} and L{osc.Receiver} over UDP via localhost.
    """

    def setUp(self):
        self.receiver = osc.Receiver()
        self.port = reactor.listenUDP(17777, self.receiver.getProtocol())
        self.sender = osc.Sender()


    def tearDown(self):
        return defer.DeferredList([self.port.stopListening(), self.sender.stop()])


    def _send(self, element):
        self.sender.send(element, ("127.0.0.1", 17777))


    def testSingleElement(self):
        pingMsg = osc.Message("/ping")
        d = defer.Deferred()

        def ping(m, addr):
            self.assertEqual(m, pingMsg)
            d.callback(True)

        self.receiver.addCallback("/ping", ping)
        self._send(pingMsg)
        return d



class TestReceiverWithExternalClient(unittest.TestCase):
    """
    This test needs python-liblo.
    """
    pass


class TestClientWithExternalReceiver(unittest.TestCase):
    """
    This test needs python-liblo.
    """
    pass


import unittest

from PikaBus.tools import PikaTools


class FakeIncomingMessage:
    """Stands in for aio_pika's AbstractIncomingMessage - no broker needed."""

    def __init__(self):
        self.headers = {'PikaBus.MessageId': 'an-id'}
        self.delivery_tag = 7
        self.routing_key = 'myQueue'


class TestPikaToolsHeaderFrameShim(unittest.TestCase):
    """
    The 1.x compatibility shim for data['incomingMessage']['headerFrame'].

    Nothing else in the repo uses it - everything was migrated to DATA_KEY_HEADERS - so without this
    test the shim would ship untested.
    """

    def setUp(self):
        self.message = FakeIncomingMessage()
        self.shim = PikaTools.DeprecatedHeaderFrame(self.message)

    def test_headers_still_readable_but_warns(self):
        with self.assertWarns(DeprecationWarning):
            headers = self.shim.headers
        self.assertEqual(headers, self.message.headers)

    def test_delivery_tag_still_readable_but_warns(self):
        with self.assertWarns(DeprecationWarning):
            self.assertEqual(self.shim.delivery_tag, 7)

    def test_other_attributes_forward_to_the_message(self):
        with self.assertWarns(DeprecationWarning):
            self.assertEqual(self.shim.routing_key, 'myQueue')


class TestPikaToolsNormalizeTopics(unittest.TestCase):
    """All three topic shapes PikaBus has accepted since 1.x."""

    def test_single_topic(self):
        self.assertEqual(PikaTools.NormalizeTopics('myTopic'), [('myTopic', None)])

    def test_list_of_topics(self):
        self.assertEqual(PikaTools.NormalizeTopics(['a', 'b']), [('a', None), ('b', None)])

    def test_dict_entries_carry_their_own_arguments(self):
        arguments = {'x-match': 'all'}
        self.assertEqual(
            PikaTools.NormalizeTopics([{'topic': 'a', 'arguments': arguments}, 'b'],
                                      arguments={'default': True}),
            [('a', arguments), ('b', {'default': True})])


class TestPikaToolsCallMaybeAwaitable(unittest.IsolatedAsyncioTestCase):
    """The dispatch that lets handlers and pipeline steps be either sync or async."""

    async def test_calls_a_sync_function(self):
        self.assertEqual(await PikaTools.CallMaybeAwaitable(lambda value: value * 2, 21), 42)

    async def test_awaits_an_async_function(self):
        async def Double(value):
            return value * 2
        self.assertEqual(await PikaTools.CallMaybeAwaitable(Double, 21), 42)

    async def test_awaits_an_async_callable_object(self):
        # iscoroutinefunction() is False for this, which is why the dispatch inspects the returned
        # value instead of the callable.
        class AsyncCallable:
            async def __call__(self, value):
                return value * 2
        self.assertEqual(await PikaTools.CallMaybeAwaitable(AsyncCallable(), 21), 42)

    async def test_awaits_a_partial_wrapped_coroutine(self):
        import functools

        async def Double(value):
            return value * 2
        self.assertEqual(await PikaTools.CallMaybeAwaitable(functools.partial(Double, 21)), 42)


if __name__ == '__main__':
    unittest.main()

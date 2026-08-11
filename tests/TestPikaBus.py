import asyncio
import datetime
import logging
import unittest

import aio_pika
import aio_pika.exceptions

from tests import TestTools
from tests.PikaMessageHandler import PikaMessageHandler, SyncPikaMessageHandler
from PikaBus.abstractions.AbstractPikaBus import AbstractPikaBus
from PikaBus.PikaProperties import PikaProperties, LEGACY_TIME_FORMAT


logging.basicConfig(format=f'[%(levelname)s] %(name)s - %(message)s', level='INFO')


class TestPikaBus(unittest.IsolatedAsyncioTestCase):
    """
    IsolatedAsyncioTestCase builds a fresh event loop per test method, and a PikaBusSetup is bound to
    the loop it first connected on - so every test constructs its own setups and closes them.
    """

    async def asyncSetUp(self):
        # Instance, not class, attributes. The 1.x suite shared these across test methods.
        self.receivedIds = []
        self.additionalSentAnswerIds = []
        self.asyncMethodReceivedIds = []
        await TestTools.WaitUntilRabbitLives()

    async def messageHandlerMethod(self, **kwargs):
        """An asynchronous **kwargs callable handler. It publishes, so it must be async."""
        bus: AbstractPikaBus = kwargs['bus']
        payload: dict = kwargs['payload']
        id = payload['id']
        reply = payload['reply']
        self.receivedIds.append(id)
        print(payload)
        if id in self.additionalSentAnswerIds:
            return

        if reply:
            topic = payload['topic']
            replyPayload = TestTools.GetPayload()
            answerPayload = TestTools.GetPayload()
            answerPayloadPublished = TestTools.GetPayload()
            self.additionalSentAnswerIds.append(replyPayload['id'])
            self.additionalSentAnswerIds.append(answerPayload['id'])
            self.additionalSentAnswerIds.append(answerPayloadPublished['id'])
            await bus.Reply(replyPayload)
            await bus.Send(answerPayload)
            await bus.Publish(answerPayloadPublished, topic)

    def syncMessageHandlerMethod(self, **kwargs):
        """A synchronous **kwargs callable handler. Must not publish and must not block."""
        self.asyncMethodReceivedIds.append(kwargs['payload']['id'])

    async def test_bus_consumer(self):
        messageHandler = PikaMessageHandler()
        syncMessageHandler = SyncPikaMessageHandler()
        errorMessageHandler = PikaMessageHandler(actAsErrorHandler=True)
        listenerQueue = TestTools.GetRandomQueue()
        errorQueue = TestTools.GetRandomQueue('error')
        topic = TestTools.GetRandomTopic()
        sentOutsideTransactionPayload = TestTools.GetPayload()
        sentPayload = TestTools.GetPayload(reply=True, topic=topic)
        deferrededPayload = TestTools.GetPayload()
        publisedPayload = TestTools.GetPayload()
        failingPayload = TestTools.GetPayload(failing=True)
        pikaBusSetup = TestTools.GetPikaBusSetup(listenerQueue=listenerQueue, errorQueue=errorQueue,
                                                topics=topic)
        pikaBusErrorSetup = TestTools.GetPikaBusSetup(listenerQueue=errorQueue)
        # All four handler shapes at once: async ABC subclass, sync ABC subclass,
        # async **kwargs callable, sync **kwargs callable.
        pikaBusSetup.AddMessageHandler(messageHandler)
        pikaBusSetup.AddMessageHandler(syncMessageHandler)
        pikaBusSetup.AddMessageHandler(self.messageHandlerMethod)
        pikaBusSetup.AddMessageHandler(self.syncMessageHandlerMethod)
        pikaBusErrorSetup.AddMessageHandler(errorMessageHandler)

        try:
            busCreatedBeforeStart = await pikaBusSetup.CreateBus()
            tasks = await pikaBusSetup.StartConsumers(consumerCount=2)
            errorTasks = await pikaBusErrorSetup.StartConsumers()

            bus = await pikaBusSetup.CreateBus()
            reusedConnection = await aio_pika.connect_robust(TestTools.GetDefaultConnectionUrl())
            busReuseConnection = await pikaBusSetup.CreateBus(connection=reusedConnection)
            await busReuseConnection.Send(payload=sentOutsideTransactionPayload)
            await busCreatedBeforeStart.Publish(topic=topic, payload=sentOutsideTransactionPayload,
                                               mandatory=False)
            await bus.Subscribe(topic)
            await bus.Subscribe([topic, topic])
            await bus.Send(payload=sentOutsideTransactionPayload)
            async with pikaBusSetup.CreateBus() as busWithTransaction:
                busWithTransaction: AbstractPikaBus = busWithTransaction
                await busWithTransaction.Send(payload=sentPayload)
                await busWithTransaction.Defer(payload=deferrededPayload,
                                               delay=datetime.timedelta(seconds=2))
                await busWithTransaction.Publish(payload=publisedPayload, topic=topic)
            await bus.Send(payload=failingPayload)

            # assertRaises cannot take a coroutine function - it would build a coroutine, never await
            # it, and pass vacuously. The context-manager form is required for async calls.
            with self.assertRaises(Exception):
                await bus.Reply(sentPayload)

            self.assertTrue(await pikaBusSetup.HealthCheck())
            messagesCount = await pikaBusSetup.QueueMessagesCount()
            self.assertTrue(messagesCount >= 0)

            sentOutsideTransactionPayloadId = sentOutsideTransactionPayload['id']
            sentPayloadId = sentPayload['id']
            deferrededPayloadId = deferrededPayload['id']
            publisedPayloadId = publisedPayload['id']
            failingPayloadId = failingPayload['id']
            expectedIds = [sentOutsideTransactionPayloadId, sentPayloadId,
                           deferrededPayloadId, publisedPayloadId]

            # Poll instead of sleeping a fixed 5 seconds: returns as soon as everything has arrived,
            # and reports precisely what is missing when it does not.
            arrived = await TestTools.WaitUntil(
                lambda: all(id in messageHandler.receivedIds for id in expectedIds)
                and all(id in self.receivedIds for id in self.additionalSentAnswerIds)
                and failingPayloadId in errorMessageHandler.receivedIds,
                timeout=45)
            self.assertTrue(arrived,
                            f'Timed out waiting for messages. '
                            f'handler={messageHandler.receivedIds} '
                            f'method={self.receivedIds} '
                            f'error={errorMessageHandler.receivedIds}')

            await pikaBusSetup.StopConsumers()
            await pikaBusErrorSetup.StopConsumers()
            await TestTools.CompleteTask(tasks + errorTasks)

            for expectedId in expectedIds:
                self.assertIn(expectedId, messageHandler.receivedIds)
            self.assertIn(sentOutsideTransactionPayloadId, self.receivedIds)
            self.assertIn(sentPayloadId, self.receivedIds)
            self.assertIn(publisedPayloadId, self.receivedIds)
            for additionalSentAnswerId in self.additionalSentAnswerIds:
                self.assertIn(additionalSentAnswerId, self.receivedIds)
            self.assertIn(failingPayloadId, errorMessageHandler.receivedIds)

            # Both synchronous handler shapes ran too.
            self.assertIn(sentOutsideTransactionPayloadId, syncMessageHandler.receivedIds)
            self.assertIn(sentOutsideTransactionPayloadId, self.asyncMethodReceivedIds)

            await bus.Unsubscribe(topic)
            await bus.Unsubscribe([topic, topic])
            await bus.Close()
            await busCreatedBeforeStart.Close()
            await busReuseConnection.Close()
            await reusedConnection.close()
        finally:
            await pikaBusSetup.Close()
            await pikaBusErrorSetup.Close()

    async def test_bus_publisher(self):
        topic = TestTools.GetRandomTopic()
        publisedPayload = TestTools.GetPayload()
        pikaBusSetup = TestTools.GetPikaBusSetup(topics=topic)
        try:
            await pikaBusSetup.Init()
            bus = await pikaBusSetup.CreateBus()
            # The regression anchor for on_return_raises. aio-pika defaults on_return_raises to False,
            # which would make an unroutable mandatory publish resolve successfully and silently drop
            # the message - quietly deleting the library's headline delivery guarantee. Asserting the
            # specific exception rather than bare Exception is what makes this test able to catch that.
            with self.assertRaises(aio_pika.exceptions.DeliveryError):
                await bus.Publish(payload=publisedPayload, topic=topic)
            await bus.Publish(payload=publisedPayload, topic=topic, mandatory=False)
            await bus.Close()
        finally:
            await pikaBusSetup.Close()

    async def test_healthcheck_is_false_without_consumers(self):
        """1.x returned True unconditionally here, so the check could never fail."""
        listenerQueue = TestTools.GetRandomQueue()
        pikaBusSetup = TestTools.GetPikaBusSetup(listenerQueue=listenerQueue)
        try:
            # A publisher-only setup is healthy with no consumers.
            self.assertTrue(await pikaBusSetup.HealthCheck())
            self.assertFalse(await pikaBusSetup.HealthCheck(channelId='no-such-channel'))
            tasks = await pikaBusSetup.StartConsumers()
            self.assertTrue(await pikaBusSetup.HealthCheck())
            await pikaBusSetup.StopConsumers()
            await TestTools.CompleteTask(tasks)
        finally:
            await pikaBusSetup.Close()

    async def test_stop_then_restart_consumers(self):
        """
        In 1.x StopConsumers() shut down the shared thread pool, so restarting was impossible.
        """
        listenerQueue = TestTools.GetRandomQueue()
        payload = TestTools.GetPayload()
        messageHandler = PikaMessageHandler()
        pikaBusSetup = TestTools.GetPikaBusSetup(listenerQueue=listenerQueue)
        pikaBusSetup.AddMessageHandler(messageHandler)
        try:
            tasks = await pikaBusSetup.StartConsumers()
            await pikaBusSetup.StopConsumers()
            await TestTools.CompleteTask(tasks)

            tasks = await pikaBusSetup.StartConsumers()
            bus = await pikaBusSetup.CreateBus()
            await bus.Send(payload=payload)
            arrived = await TestTools.WaitUntil(
                lambda: payload['id'] in messageHandler.receivedIds, timeout=30)
            self.assertTrue(arrived, 'Consumer did not work after a stop/start cycle.')
            await bus.Close()
            await pikaBusSetup.StopConsumers()
            await TestTools.CompleteTask(tasks)
        finally:
            await pikaBusSetup.Close()

    async def test_deferred_message_waits_without_blocking_the_queue(self):
        """
        A pending defer must not stall the consumer.

        A not-yet-due message is republished and acked, so it bounces off the broker rather than
        being awaited in-process. Waiting in-process would hold a prefetch and concurrency slot for
        the whole delay, so an ordinary message sent behind a defer would not be handled until the
        defer expired. Here the deferred message must arrive no earlier than its delay, and a
        message sent right after it must be handled long before that.
        """
        listenerQueue = TestTools.GetRandomQueue()
        deferredPayload = TestTools.GetPayload()
        sentPayload = TestTools.GetPayload()
        messageHandler = PikaMessageHandler()
        # Concurrency 1, i.e. the default: nothing but the republish keeps the consumer free.
        pikaBusSetup = TestTools.GetPikaBusSetup(listenerQueue=listenerQueue)
        pikaBusSetup.AddMessageHandler(messageHandler)
        try:
            tasks = await pikaBusSetup.StartConsumers()
            bus = await pikaBusSetup.CreateBus()
            delaySeconds = 3
            loop = asyncio.get_running_loop()
            start = loop.time()
            await bus.Defer(payload=deferredPayload, delay=datetime.timedelta(seconds=delaySeconds))
            await bus.Send(payload=sentPayload)

            # The message queued behind the defer goes through while the defer is still pending.
            overtook = await TestTools.WaitUntil(
                lambda: sentPayload['id'] in messageHandler.receivedIds, timeout=delaySeconds - 1)
            self.assertTrue(overtook, 'A pending deferred message blocked the queue behind it.')
            self.assertNotIn(deferredPayload['id'], messageHandler.receivedIds,
                             'Deferred message was handled before its deferred time.')

            arrived = await TestTools.WaitUntil(
                lambda: deferredPayload['id'] in messageHandler.receivedIds, timeout=30)
            elapsed = loop.time() - start
            self.assertTrue(arrived, 'Deferred message never arrived.')
            # Timestamps are microsecond precise since 2.0, so the deadline is exact rather than
            # rounded to the second - only scheduling slack needs tolerating.
            self.assertGreaterEqual(elapsed, delaySeconds - 0.05,
                                    'Deferred message was handled too early.')
            await bus.Close()
            await pikaBusSetup.StopConsumers()
            await TestTools.CompleteTask(tasks)
        finally:
            await pikaBusSetup.Close()

    async def test_sub_second_defer(self):
        """
        Newly possible in 2.0. The 1.x timestamp format had second resolution, so a sub-second delay
        either rounded away entirely or cost a full second.
        """
        listenerQueue = TestTools.GetRandomQueue()
        payload = TestTools.GetPayload()
        messageHandler = PikaMessageHandler()
        pikaBusSetup = TestTools.GetPikaBusSetup(listenerQueue=listenerQueue)
        pikaBusSetup.AddMessageHandler(messageHandler)
        try:
            tasks = await pikaBusSetup.StartConsumers()
            bus = await pikaBusSetup.CreateBus()
            loop = asyncio.get_running_loop()
            start = loop.time()
            await bus.Defer(payload=payload, delay=datetime.timedelta(milliseconds=400))
            arrived = await TestTools.WaitUntil(
                lambda: payload['id'] in messageHandler.receivedIds, timeout=30)
            elapsed = loop.time() - start
            self.assertTrue(arrived, 'Sub-second deferred message never arrived.')
            self.assertGreaterEqual(elapsed, 0.35, 'Sub-second defer was not honoured.')
            self.assertLess(elapsed, 5, 'Sub-second defer took far longer than asked.')
            await bus.Close()
            await pikaBusSetup.StopConsumers()
            await TestTools.CompleteTask(tasks)
        finally:
            await pikaBusSetup.Close()

    async def test_consumes_a_message_carrying_1x_format_timestamps(self):
        """
        End-to-end proof of the timestamp dual-parse fallback.

        This is the rolling-upgrade path: a PikaBus 1.x publisher writes '%m/%d/%Y %H:%M:%S'
        timestamps, a 2.0 consumer picks the message up. Without the fallback, StringToDatetime raises
        inside the pipeline, which the pipeline treats as a message failure - so every in-flight
        message would drain into the error queue during a deployment. The message must be *handled*,
        and the error queue must stay empty.
        """
        listenerQueue = TestTools.GetRandomQueue()
        errorQueue = TestTools.GetRandomQueue('error')
        payload = TestTools.GetPayload()
        messageHandler = PikaMessageHandler()
        pikaBusSetup = TestTools.GetPikaBusSetup(listenerQueue=listenerQueue, errorQueue=errorQueue)
        pikaBusSetup.AddMessageHandler(messageHandler)
        # Declare the error queue up front so counting it below is meaningful. Otherwise it would not
        # exist at all - which is itself the right outcome, but makes the count raise NOT_FOUND.
        errorQueueSetup = TestTools.GetPikaBusSetup(listenerQueue=errorQueue)
        try:
            await errorQueueSetup.Init()
            tasks = await pikaBusSetup.StartConsumers()

            # Publish exactly what a 1.x process would: legacy TimeSent and a legacy DeferredTime
            # already in the past, so the deferral step has to parse it too.
            legacyProperties = PikaProperties(timeFormat=LEGACY_TIME_FORMAT)
            past = legacyProperties.DatetimeToString(
                datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=5))
            async with pikaBusSetup.CreateBus() as bus:
                await bus.Send(payload=payload, headers={
                    legacyProperties.timeSentHeaderKey: past,
                    legacyProperties.deferredTimeHeaderKey: past,
                })

            arrived = await TestTools.WaitUntil(
                lambda: payload['id'] in messageHandler.receivedIds, timeout=30)
            self.assertTrue(arrived,
                            'A message with 1.x format timestamps was not handled - the dual-parse '
                            'fallback is broken, and a rolling upgrade would dead-letter live traffic.')
            self.assertEqual(await pikaBusSetup.QueueMessagesCount(queue=errorQueue), 0,
                             'A 1.x timestamp should not send the message to the error queue.')

            await pikaBusSetup.StopConsumers()
            await TestTools.CompleteTask(tasks)
        finally:
            await pikaBusSetup.Close()
            await errorQueueSetup.Close()

    async def test_sync_context_manager_raises_helpfully(self):
        """`with CreateBus()` was valid in 1.x; it must fail with a message that says what to do."""
        pikaBusSetup = TestTools.GetPikaBusSetup(listenerQueue=TestTools.GetRandomQueue())
        try:
            bus = await pikaBusSetup.CreateBus()
            with self.assertRaises(TypeError) as context:
                with bus:
                    pass
            self.assertIn('async with', str(context.exception))
            await bus.Close()
        finally:
            await pikaBusSetup.Close()


if __name__ == '__main__':
    unittest.main()

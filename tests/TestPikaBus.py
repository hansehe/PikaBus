import unittest
import time
import datetime
import logging
from tests import TestTools
from tests.PikaMessageHandler import PikaMessageHandler
from PikaBus.abstractions.AbstractPikaBus import AbstractPikaBus


logging.basicConfig(format=f'[%(levelname)s] %(name)s - %(message)s', level='INFO')


class TestPikaBus(unittest.TestCase):
    receivedIds = []
    additionalSentAnswerIds = []

    def messageHandlerMethod(self, **kwargs):
        data: dict = kwargs['data']
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
            bus.Reply(replyPayload)
            bus.Send(answerPayload)
            bus.Publish(answerPayloadPublished, topic)

    def test_bus_consumer(self):
        TestTools.WaitUntilRabbitLives()
        messageHandler = PikaMessageHandler()
        errorMessageHandler = PikaMessageHandler(actAsErrorHandler=True)
        listenerQueue = TestTools.GetRandomQueue()
        errorQueue = TestTools.GetRandomQueue('error')
        topic = TestTools.GetRandomTopic()
        sentOutsideTransactionPayload = TestTools.GetPayload()
        sentPayload = TestTools.GetPayload(reply=True, topic=topic)
        deferrededPayload = TestTools.GetPayload()
        publisedPayload = TestTools.GetPayload()
        failingPayload = TestTools.GetPayload(failing=True)
        pikaBusSetup = TestTools.GetPikaBusSetup(listenerQueue=listenerQueue, errorQueue=errorQueue, topics=topic)
        pikaBusErrorSetup = TestTools.GetPikaBusSetup(listenerQueue=errorQueue)
        pikaBusSetup.AddMessageHandler(messageHandler)
        pikaBusSetup.AddMessageHandler(self.messageHandlerMethod)
        pikaBusErrorSetup.AddMessageHandler(errorMessageHandler)
        busCreatedBeforeStart = pikaBusSetup.CreateBus()
        busCreatedBeforeStart.Publish(topic=topic, payload=sentOutsideTransactionPayload, mandatory=False)
        tasks = pikaBusSetup.StartAsync(consumers=2)
        errorTasks = pikaBusErrorSetup.StartAsync()
        try:
            bus = pikaBusSetup.CreateBus()
            busSeparateChannel = pikaBusSetup.CreateBus(createNewConnection=True)
            busSeparateChannel.Send(payload=sentOutsideTransactionPayload)
            bus.Subscribe(topic)
            bus.Subscribe([topic, topic])
            bus.Send(payload=sentOutsideTransactionPayload)
            bus.StartTransaction()
            bus.Send(payload=sentPayload)
            bus.Defer(payload=deferrededPayload, delay=datetime.timedelta(seconds=2))
            bus.Publish(payload=publisedPayload, topic=topic)
            bus.CommitTransaction()
            bus.Send(payload=failingPayload)
            self.assertRaises(Exception, bus.Reply, sentPayload)
        finally:
            time.sleep(5)
            pikaBusSetup.Stop()
            pikaBusErrorSetup.Stop()
            TestTools.CompleteTask(tasks + errorTasks)
        sentOutsideTransactionPayloadId = sentOutsideTransactionPayload['id']
        sentPayloadId = sentPayload['id']
        deferrededPayloadId = deferrededPayload['id']
        publisedPayloadId = publisedPayload['id']
        failingPayloadId = failingPayload['id']
        self.assertTrue(sentOutsideTransactionPayloadId in messageHandler.receivedIds)
        self.assertTrue(sentPayloadId in messageHandler.receivedIds)
        self.assertTrue(deferrededPayloadId in messageHandler.receivedIds)
        self.assertTrue(publisedPayloadId in messageHandler.receivedIds)
        self.assertTrue(sentOutsideTransactionPayloadId in self.receivedIds)
        self.assertTrue(sentPayloadId in self.receivedIds)
        self.assertTrue(publisedPayloadId in self.receivedIds)
        for additionalSentAnswerId in self.additionalSentAnswerIds:
            self.assertTrue(additionalSentAnswerId in self.receivedIds)

        self.assertTrue(failingPayloadId in errorMessageHandler.receivedIds)
        bus.Unsubscribe(topic)
        bus.Unsubscribe([topic, topic])

    def test_bus_publisher(self):
        TestTools.WaitUntilRabbitLives()
        topic = TestTools.GetRandomTopic()
        publisedPayload = TestTools.GetPayload()
        pikaBusSetup = TestTools.GetPikaBusSetup(topics=topic)
        pikaBusSetup.Init()
        bus = pikaBusSetup.CreateBus()
        self.assertRaises(Exception, bus.Publish, payload=publisedPayload, topic=topic)
        bus.Publish(payload=publisedPayload, topic=topic, mandatory=False)


if __name__ == '__main__':
    unittest.main()

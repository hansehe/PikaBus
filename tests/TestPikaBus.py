import unittest
import time
import warnings
from tests import TestTools
from tests.PikaMessageHandler import PikaMessageHandler


class TestPikaBus(unittest.TestCase):
    receivedIds = []
    additionalSentAnswerIds = []

    def messageHandlerMethod(self, **kwargs):
        data = kwargs['data']
        bus = kwargs['bus']
        payload = kwargs['payload']
        id = payload['id']
        reply = payload['reply']
        self.receivedIds.append(id)
        print(payload)
        if id in self.additionalSentAnswerIds:
            return

        if reply:
            topic = payload['topic']
            answerPayload = TestTools.GetPayload()
            answerPayloadPublished = TestTools.GetPayload()
            self.additionalSentAnswerIds.append(answerPayload['id'])
            self.additionalSentAnswerIds.append(answerPayloadPublished['id'])
            bus.Send(answerPayload)
            bus.Publish(answerPayloadPublished, topic)

    def test_bus_consumer(self):
        TestTools.WaitUntilRabbitLives()
        messageHandler = PikaMessageHandler()
        errorMessageHandler = PikaMessageHandler(actAsErrorHandler=True)
        listenerQueue = TestTools.GetRandomQueue()
        errorQueue = 'error'
        topic = TestTools.GetRandomTopic()
        sentOutsideTransactionPayload = TestTools.GetPayload()
        sentPayload = TestTools.GetPayload(reply=True, topic=topic)
        publisedPayload = TestTools.GetPayload()
        failingPayload = TestTools.GetPayload(failing=True)
        pikaBusSetup = TestTools.GetPikaBusSetup(listenerQueue=listenerQueue)
        pikaBusErrorSetup = TestTools.GetPikaBusSetup(listenerQueue=errorQueue)
        pikaBusSetup.AddMessageHandler(messageHandler)
        pikaBusSetup.AddMessageHandler(self.messageHandlerMethod)
        pikaBusErrorSetup.AddMessageHandler(errorMessageHandler)
        task = pikaBusSetup.StartAsync()
        errorTask = pikaBusErrorSetup.StartAsync()
        try:
            bus = pikaBusSetup.CreateBus()
            bus.Subscribe(topic)
            bus.Send(payload=sentOutsideTransactionPayload)
            bus.StartTransaction()
            bus.Send(payload=sentPayload)
            bus.Publish(payload=publisedPayload, topic=topic)
            bus.CommitTransaction()
            bus.Send(payload=failingPayload)
        finally:
            time.sleep(5)
            pikaBusSetup.Stop()
            pikaBusErrorSetup.Stop()
            TestTools.CompleteTask([task, errorTask])
        sentOutsideTransactionPayloadId = sentOutsideTransactionPayload['id']
        sentPayloadId = sentPayload['id']
        publisedPayloadId = publisedPayload['id']
        failingPayloadId = failingPayload['id']
        self.assertTrue(sentOutsideTransactionPayloadId in messageHandler.receivedIds)
        self.assertTrue(sentPayloadId in messageHandler.receivedIds)
        self.assertTrue(publisedPayloadId in messageHandler.receivedIds)
        self.assertTrue(sentOutsideTransactionPayloadId in self.receivedIds)
        self.assertTrue(sentPayloadId in self.receivedIds)
        self.assertTrue(publisedPayloadId in self.receivedIds)
        for additionalSentAnswerId in self.additionalSentAnswerIds:
            self.assertTrue(additionalSentAnswerId in self.receivedIds)

        self.assertTrue(failingPayloadId in errorMessageHandler.receivedIds)


if __name__ == '__main__':
    unittest.main()

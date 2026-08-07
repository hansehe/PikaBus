import abc


class AbstractPikaErrorHandler(abc.ABC):
    @abc.abstractmethod
    async def HandleFailure(self, data: dict, exception: Exception):
        """
        Deal with a message whose pipeline raised - typically by retrying it with a backoff and
        eventually moving it to an error queue.

        Changed in 2.0: this is a coroutine, since it publishes and acknowledges.

        The implementation owns acknowledging the message. If it cannot - because the channel died -
        it must leave the message unacked rather than raise, so the broker can redeliver. Raising here
        is treated as a double fault by the consumer, which then rejects the message.

        :param dict data: General data holder
        :param Exception exception: The exception raised by the pipeline
        """
        pass

import abc

from PikaBus.abstractions.AbstractPikaBus import AbstractPikaBus


class AbstractPikaMessageHandler(abc.ABC):
    @abc.abstractmethod
    def HandleMessage(self, data: dict, bus: AbstractPikaBus, payload: dict):
        """
        Handle an incoming message.

        May be implemented as either `def HandleMessage(...)` or `async def HandleMessage(...)`.
        The signature is declared synchronously here on purpose: declaring it `async def` would force
        every existing subclass to become a coroutine.

        A synchronous implementation cannot publish. bus.Send/Publish/Reply/Defer are coroutines in
        2.0, so calling one from a plain `def` handler creates a coroutine that is never awaited and
        silently does nothing. Any handler that publishes must be `async def`. A synchronous handler
        also runs directly on the event loop, so it must not block.

        Read incoming headers with:
            data[PikaConstants.DATA_KEY_INCOMING_MESSAGE][PikaConstants.DATA_KEY_HEADERS]
        and reach the raw aio-pika message with:
            data[PikaConstants.DATA_KEY_INCOMING_MESSAGE][PikaConstants.DATA_KEY_MESSAGE]

        :param dict data: General data holder
        :param AbstractPikaBus bus: Bus to send, publish, defer or reply with. Already inside a transaction.
        :param dict payload: The deserialized incoming payload
        """
        pass

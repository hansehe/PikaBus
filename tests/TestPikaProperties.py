import datetime
import unittest

import aio_pika

from PikaBus.PikaProperties import PikaProperties, LEGACY_TIME_FORMAT
from PikaBus.tools import PikaConstants


def GetOutgoingMessage(headers: dict = None, body: bytes = b'{}'):
    return {
        PikaConstants.DATA_KEY_HEADERS: {} if headers is None else headers,
        PikaConstants.DATA_KEY_INTENT: PikaConstants.INTENT_COMMAND,
        PikaConstants.DATA_KEY_MESSAGE_TYPE: 'MyMessageType',
        PikaConstants.DATA_KEY_CONTENT_TYPE: 'application/json',
        PikaConstants.DATA_KEY_CONTENT_ENCODING: 'utf-8',
        PikaConstants.DATA_KEY_BODY: body,
        PikaConstants.DATA_KEY_EXCEPTION: None,
    }


class TestPikaProperties(unittest.TestCase):
    """Broker-free unit tests for the properties layer."""

    def setUp(self):
        self.properties = PikaProperties()
        self.data = {PikaConstants.DATA_KEY_LISTENER_QUEUE: 'myQueue'}

    def test_returns_an_aio_pika_message(self):
        message = self.properties.GetPikaProperties(self.data, GetOutgoingMessage())
        self.assertIsInstance(message, aio_pika.Message)
        self.assertEqual(message.body, b'{}')
        # Persistent by default. aio_pika.Message defaults to NOT_PERSISTENT, so this has to be set
        # explicitly - forgetting it would silently make every message non-durable.
        self.assertEqual(int(message.delivery_mode), 2)
        self.assertEqual(message.content_type, 'application/json')
        self.assertEqual(message.content_encoding, 'utf-8')
        self.assertEqual(message.type, 'MyMessageType')
        self.assertEqual(message.reply_to, 'myQueue')

    def test_timestamp_is_utc(self):
        """
        Regression test for the mktime bug.

        1.x did int(time.mktime(utcTimestamp.timetuple())), which interprets a naive UTC datetime as
        *local* time - so the published AMQP timestamp was off by the machine's UTC offset, and by a
        different amount either side of a DST change. This asserts the timestamp matches the
        PikaBus.TimeSent header interpreted as UTC, which fails on any machine not set to UTC if the
        bug returns.
        """
        outgoingMessage = GetOutgoingMessage()
        message = self.properties.GetPikaProperties(self.data, outgoingMessage)
        timeSent = outgoingMessage[PikaConstants.DATA_KEY_HEADERS][self.properties.timeSentHeaderKey]
        expected = self.properties.StringToDatetime(timeSent).replace(tzinfo=datetime.timezone.utc)
        self.assertEqual(message.timestamp.timestamp(), expected.timestamp())

    def test_default_headers_are_set(self):
        outgoingMessage = GetOutgoingMessage()
        self.properties.GetPikaProperties(self.data, outgoingMessage)
        headers = outgoingMessage[PikaConstants.DATA_KEY_HEADERS]
        for key in (self.properties.messageIdHeaderKey,
                    self.properties.timeSentHeaderKey,
                    self.properties.replyToAddressHeaderKey,
                    self.properties.originatingAddressHeaderKey,
                    self.properties.intentHeaderKey,
                    self.properties.messageTypeHeaderKey,
                    self.properties.contentTypeHeaderKey,
                    self.properties.contentEncodingHeaderKey,
                    self.properties.correlationIdHeaderKey):
            self.assertIn(key, headers)

    def test_correlation_id_is_propagated_from_the_incoming_message(self):
        correlationId = 'a-correlation-id'
        self.data[PikaConstants.DATA_KEY_INCOMING_MESSAGE] = {
            PikaConstants.DATA_KEY_HEADERS: {self.properties.correlationIdHeaderKey: correlationId},
        }
        outgoingMessage = GetOutgoingMessage()
        message = self.properties.GetPikaProperties(self.data, outgoingMessage)
        self.assertEqual(message.correlation_id, correlationId)

    def test_timestamps_are_iso_8601_with_an_offset(self):
        written = self.properties.DatetimeToString()
        # Parseable by any ISO 8601 reader, not just PikaBus.
        parsed = datetime.datetime.fromisoformat(written)
        self.assertIsNotNone(parsed.tzinfo, 'Timestamps must carry an offset.')
        self.assertEqual(parsed.utcoffset(), datetime.timedelta(0))
        self.assertIn('T', written)

    def test_time_format_round_trips(self):
        original = datetime.datetime(2026, 8, 7, 12, 34, 56, 123456,
                                     tzinfo=datetime.timezone.utc)
        written = self.properties.DatetimeToString(original)
        self.assertEqual(self.properties.StringToDatetime(written), original)

    def test_sub_second_precision_is_preserved(self):
        """
        1.x's format had second resolution, which put a one second floor under Defer() and under every
        error-handler retry backoff. Microseconds now survive the round trip.
        """
        original = datetime.datetime(2026, 8, 7, 12, 34, 56, 500000,
                                     tzinfo=datetime.timezone.utc)
        roundTripped = self.properties.StringToDatetime(
            self.properties.DatetimeToString(original))
        self.assertEqual(roundTripped.microsecond, 500000)

    def test_parses_a_z_suffix_and_a_non_utc_offset(self):
        self.assertEqual(
            self.properties.StringToDatetime('2026-08-07T12:34:56Z'),
            datetime.datetime(2026, 8, 7, 12, 34, 56, tzinfo=datetime.timezone.utc))
        # A sender in another timezone still compares correctly.
        self.assertEqual(
            self.properties.StringToDatetime('2026-08-07T14:34:56+02:00'),
            datetime.datetime(2026, 8, 7, 12, 34, 56, tzinfo=datetime.timezone.utc))

    def test_naive_datetimes_are_treated_as_utc(self):
        naive = datetime.datetime(2026, 8, 7, 12, 34, 56)
        written = self.properties.DatetimeToString(naive)
        self.assertEqual(self.properties.StringToDatetime(written),
                         naive.replace(tzinfo=datetime.timezone.utc))

    def test_a_custom_strftime_format_is_still_honoured(self):
        """The timeFormat hook still works, for anyone who needs to match a foreign consumer."""
        properties = PikaProperties(timeFormat=LEGACY_TIME_FORMAT)
        written = properties.DatetimeToString(
            datetime.datetime(2026, 8, 7, 12, 34, 56, tzinfo=datetime.timezone.utc))
        self.assertEqual(written, '08/07/2026 12:34:56')
        # Formats without an offset are read back as UTC, so comparisons never mix aware and naive.
        self.assertEqual(properties.StringToDatetime(written).tzinfo, datetime.timezone.utc)

    def test_misspelled_message_type_key_still_works_but_warns(self):
        with self.assertWarns(DeprecationWarning):
            key = self.properties.messsageTypeHeaderKey
        self.assertEqual(key, self.properties.messageTypeHeaderKey)


class TestPikaPropertiesTimestampFallback(unittest.TestCase):
    """
    The dual-parse fallback that makes a rolling 1.x to 2.0 upgrade safe.

    Without it, a 2.0 consumer handed a 1.x timestamp raises inside the pipeline, which is treated as
    a message failure - so the whole queue would drain into the error queue mid-deployment.
    """

    LEGACY = '08/07/2026 12:34:56'
    ISO = '2026-08-07T12:34:56.123456+00:00'
    EXPECTED_LEGACY = datetime.datetime(2026, 8, 7, 12, 34, 56, tzinfo=datetime.timezone.utc)

    def test_iso_configured_reads_a_legacy_1x_timestamp(self):
        """A 2.0 consumer reading a message published by a 1.x process."""
        properties = PikaProperties()
        self.assertEqual(properties.StringToDatetime(self.LEGACY), self.EXPECTED_LEGACY)

    def test_legacy_configured_reads_an_iso_timestamp(self):
        """
        The reverse: a service pinned to the legacy format during a staged rollout still reads
        messages from an already-upgraded publisher.
        """
        properties = PikaProperties(timeFormat=LEGACY_TIME_FORMAT)
        parsed = properties.StringToDatetime(self.ISO)
        self.assertEqual(parsed,
                         datetime.datetime(2026, 8, 7, 12, 34, 56, 123456,
                                           tzinfo=datetime.timezone.utc))

    def test_a_fully_custom_format_falls_back_to_both_known_formats(self):
        properties = PikaProperties(timeFormat='%Y%m%d%H%M%S')
        self.assertEqual(properties.StringToDatetime('20260807123456'), self.EXPECTED_LEGACY)
        self.assertEqual(properties.StringToDatetime(self.LEGACY), self.EXPECTED_LEGACY)
        self.assertIsNotNone(properties.StringToDatetime(self.ISO))

    def test_the_fallback_warns_once_per_format(self):
        properties = PikaProperties()
        with self.assertLogs('PikaBus.PikaProperties', level='WARNING') as logs:
            properties.StringToDatetime(self.LEGACY)
        self.assertEqual(len(logs.records), 1)
        self.assertIn('still', logs.records[0].getMessage())
        # Repeated fallbacks must not flood the log, one per message.
        with self.assertNoLogs('PikaBus.PikaProperties', level='WARNING'):
            properties.StringToDatetime(self.LEGACY)
            properties.StringToDatetime('01/02/2027 03:04:05')

    def test_the_primary_format_does_not_warn(self):
        properties = PikaProperties()
        with self.assertNoLogs('PikaBus.PikaProperties', level='WARNING'):
            properties.StringToDatetime(self.ISO)

    def test_an_unparseable_timestamp_raises_a_clear_error(self):
        properties = PikaProperties()
        with self.assertRaises(ValueError) as context:
            properties.StringToDatetime('not a timestamp at all')
        message = str(context.exception)
        self.assertIn('not a timestamp at all', message)
        self.assertIn('ISO 8601', message)
        self.assertIn('%m/%d/%Y', message)


if __name__ == '__main__':
    unittest.main()

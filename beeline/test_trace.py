from collections import defaultdict
from mock import ANY, Mock, call, patch
import datetime
import unittest
import uuid

from libhoney import Event

from beeline.trace import (
    _should_sample, SynchronousTracer, marshal_trace_context,
    unmarshal_trace_context, Span
)

class TestTraceSampling(unittest.TestCase):
    def test_deterministic(self):
        ''' test a specific id that should always work with the given sample rate '''
        trace_id = 'b8d674f1-04ed-4ea8-b16d-b4dbbe87c78e'
        n = 0
        while n < 1000:
            self.assertTrue(_should_sample(trace_id, 1000))
            n += 1

    def test_deterministic_interop(self):
        '''test a specific set of ids that should always have the given result (at sample rate 2)
        Ensures interoperability with other beelines'''
        ids = [
            "4YeYygWjTZ41zOBKUoYUaSVxPGm78rdU",
            "iow4KAFBl9u6lF4EYIcsFz60rXGvu7ph",
            "EgQMHtruEfqaqQqRs5nwaDXsegFGmB5n",
            "UnVVepVdyGIiwkHwofyva349tVu8QSDn",
            "rWuxi2uZmBEprBBpxLLFcKtXHA8bQkvJ",
            "8PV5LN1IGm5T0ZVIaakb218NvTEABNZz",
            "EMSmscnxwfrkKd1s3hOJ9bL4zqT1uud5",
            "YiLx0WGJrQAge2cVoAcCscDDVidbH4uE",
            "IjD0JHdQdDTwKusrbuiRO4NlFzbPotvg",
            "ADwiQogJGOS4X8dfIcidcfdT9fY2WpHC",
            "DyGaS7rfQsMX0E6TD9yORqx7kJgUYvNR",
            "MjOCkn11liCYZspTAhdULMEfWJGMHvpK",
            "wtGa41YcFMR5CBNr79lTfRAFi6Vhr6UF",
            "3AsMjnpTBawWv2AAPDxLjdxx4QYl9XXb",
            "sa2uMVNPiZLK52zzxlakCUXLaRNXddBz",
            "NYH9lkdbvXsiUFKwJtjSkQ1RzpHwWloK",
            "8AwzQeY5cudY8YUhwxm3UEP7Oos61RTY",
            "ADKWL3p5gloRYO3ptarTCbWUHo5JZi3j",
            "UAnMARj5x7hkh9kwBiNRfs5aYDsbHKpw",
            "Aes1rgTLMNnlCkb9s6bH7iT5CbZTdxUw",
            "eh1LYTOfgISrZ54B7JbldEpvqVur57tv",
            "u5A1wEYax1kD9HBeIjwyNAoubDreCsZ6",
            "mv70SFwpAOHRZt4dmuw5n2lAsM1lOrcx",
            "i4nIu0VZMuh5hLrUm9w2kqNxcfYY7Y3a",
            "UqfewK2qFZqfJ619RKkRiZeYtO21ngX1",
        ]
        expected = [
            False,
            True,
            True,
            True,
            True,
            False,
            True,
            True,
            False,
            False,
            True,
            False,
            True,
            False,
            False,
            False,
            False,
            False,
            True,
            True,
            False,
            False,
            True,
            True,
            False,
        ]

        for i in range(len(ids)):
            self.assertEqual(_should_sample(ids[i], 2), expected[i])


    def test_probability(self):
        ''' test that _should_sample approximates 1 in N sampling for random IDs '''
        tests_count = 50000
        error_margin = 0.05

        sample_rates = [1, 2, 10]

        for rate in sample_rates:
            sampled = n = 0

            while n < tests_count:
                n += 1
                if _should_sample(str(uuid.uuid4()), rate):
                    sampled += 1

            expected = tests_count // rate

            acceptable_lower_bound = int(expected - (expected * error_margin))
            acceptable_upper_bound = int(expected + (expected * error_margin))

            self.assertLessEqual(sampled, acceptable_upper_bound)
            self.assertGreaterEqual(sampled, acceptable_lower_bound)

class TestSynchronousTracer(unittest.TestCase):
    def test_trace_context_manager_exception(self):
        ''' ensure that span is sent even if an exception is
        raised inside the context manager '''
        m_client = Mock()
        tracer = SynchronousTracer(m_client)
        tracer.start_trace = Mock()
        mock_span = Mock()
        tracer.start_trace.return_value = mock_span
        tracer.finish_trace = Mock()
        try:
            with tracer('foo'):
                raise Exception('boom!')
        except Exception:
            pass
        tracer.finish_trace.assert_called_once_with(mock_span)

    def test_trace_context_manager_starts_span_if_trace_active(self):
        m_client = Mock()
        tracer = SynchronousTracer(m_client)
        tracer.start_span = Mock()
        tracer.start_trace = Mock()
        tracer.get_active_trace_id = Mock(return_value='asdf')
        mock_span = Mock()
        tracer.start_span.return_value = mock_span
        tracer.finish_span = Mock()

        with tracer('foo') as span:
            self.assertEqual(span, mock_span, 'tracer context manager should yield the span')

        tracer.start_span.assert_called_once_with(context={'name': 'foo'}, parent_id=None)
        tracer.start_trace.assert_not_called()
        tracer.finish_span.assert_called_once_with(mock_span)

    def test_trace_context_manager_passes_parent_id_if_supplied(self):
        ''' ensure parent_id gets passed to start_span if supplied '''
        m_client = Mock()
        tracer = SynchronousTracer(m_client)
        tracer.start_span = Mock()
        mock_span = Mock()
        tracer.start_span.return_value = mock_span
        tracer.finish_span = Mock()

        with tracer('foo', parent_id='zyxw'):
            pass

        tracer.start_span.assert_called_once_with(context={'name': 'foo'}, parent_id='zyxw')
        tracer.finish_span.assert_called_once_with(mock_span)

    def test_trace_context_manager_starts_trace_if_trace_id_supplied(self):
        ''' ensure trace_id and parent_id get passed to start_trace if supplied '''
        m_client = Mock()
        tracer = SynchronousTracer(m_client)
        tracer.start_trace = Mock()
        mock_span = Mock()
        tracer.start_trace.return_value = mock_span
        tracer.finish_span = Mock()

        with tracer('foo', trace_id='asdf', parent_id='zyxw'):
            pass

        tracer.start_trace.assert_called_once_with(context={'name': 'foo'}, trace_id='asdf', parent_span_id='zyxw')
        tracer.finish_span.assert_called_once_with(mock_span)

    def test_start_trace(self):
        m_client = Mock()
        tracer = SynchronousTracer(m_client)

        span = tracer.start_trace(context={'big': 'important_stuff'})
        self.assertIsInstance(span.event.start_time, datetime.datetime)
        # make sure our context got passed on to the event
        m_client.new_event.return_value.add.assert_has_calls([
            call(data={'big': 'important_stuff'}),
            call(data={
                'trace.trace_id': span.trace_id,
                'trace.parent_id': span.parent_id,
                'trace.span_id': span.id,
            }),
        ])
        self.assertEqual(tracer._state.stack[0], span)
        # ensure we started a trace by setting a trace_id
        self.assertIsNotNone(tracer._state.trace_id)

    def test_start_span(self):
        m_client = Mock()
        tracer = SynchronousTracer(m_client)

        span = tracer.start_trace(context={'big': 'important_stuff'})
        # make sure this is the only event in the stack
        self.assertEqual(tracer._state.stack[0], span)
        self.assertEqual(len(tracer._state.stack), 1)

        span2 = tracer.start_span(context={'more': 'important_stuff'})
        # should still have the root span as the first item in the stack
        self.assertEqual(tracer._state.stack[0], span)
        self.assertEqual(tracer._state.stack[-1], span2)
        # should have the first span id as its parent
        # should share the same trace id
        self.assertEqual(span.trace_id, span2.trace_id)
        self.assertEqual(span.id, span2.parent_id)
        # trace id should match what the tracer has
        self.assertEqual(span.trace_id, tracer._state.trace_id)
        m_client.new_event.return_value.add.assert_has_calls([
            call(data={'more': 'important_stuff'}),
            call(data={
                'trace.trace_id': span2.trace_id,
                'trace.parent_id': span2.parent_id,
                'trace.span_id': span2.id,
            }),
        ])

    def test_start_span_returns_none_if_no_trace(self):
        m_client = Mock()
        tracer = SynchronousTracer(m_client)

        span = tracer.start_span(context={'more': 'important_stuff'})
        # should still have the root span as the first item in the stack
        self.assertIsNone(span)
        self.assertEqual(len(tracer._state.stack), 0)

    def test_finish_trace(self):
        # implicitly tests finish_span
        m_client = Mock()
        # these values are used before sending
        m_client.new_event.return_value.start_time = datetime.datetime.now()
        m_client.new_event.return_value.sample_rate = 1
        tracer = SynchronousTracer(m_client)

        span = tracer.start_trace(context={'big': 'important_stuff'})
        self.assertEqual(tracer._state.stack[0], span)

        tracer.finish_trace(span)
        # ensure the event is sent
        span.event.send_presampled.assert_called_once_with()
        # ensure the stack is clean
        self.assertEqual(len(tracer._state.stack), 0)
        # ensure the trace_id is reset to None
        self.assertIsNone(tracer._state.trace_id)

    def test_start_trace_with_trace_id_set(self):
        m_client = Mock()
        tracer = SynchronousTracer(m_client)

        span = tracer.start_trace(trace_id='123456', parent_span_id='999999')
        self.assertEqual(span.trace_id, '123456')
        self.assertEqual(span.parent_id, '999999')
        self.assertEqual(tracer._state.trace_id, '123456')

        m_client.new_event.return_value.add.assert_has_calls([
            call(data={
                'trace.trace_id': span.trace_id,
                'trace.parent_id': span.parent_id,
                'trace.span_id': span.id,
            }),
        ])

    def test_add_trace_field_propagates(self):
        m_client = Mock()
        tracer = SynchronousTracer(m_client)

        span = tracer.start_trace(context={'big': 'important_stuff'})
        # make sure this is the only event in the stack
        self.assertEqual(tracer._state.stack[0], span)
        self.assertEqual(len(tracer._state.stack), 1)

        m_client.new_event.reset_mock()

        tracer.add_trace_field('another', 'important_thing')
        tracer.add_trace_field('wide', 'events_are_great')

        span2 = tracer.start_span(context={'more': 'important_stuff'})
        # should still have the root span as the first item in the stack
        self.assertEqual(tracer._state.stack[0], span)
        self.assertEqual(tracer._state.stack[-1], span2)
        # should have the first span id as its parent
        # should share the same trace id
        self.assertEqual(span.trace_id, span2.trace_id)
        self.assertEqual(span.id, span2.parent_id)
        # trace id should match what the tracer has
        self.assertEqual(span.trace_id, tracer._state.trace_id)
        m_client.new_event.assert_called_once_with(data={
                'app.another': 'important_thing',
                'app.wide': 'events_are_great'
        })
        m_client.new_event.return_value.add.assert_has_calls([
            call(data={'more': 'important_stuff'}),
            call(data={
                'trace.trace_id': span2.trace_id,
                'trace.parent_id': span2.parent_id,
                'trace.span_id': span2.id,
            }),
        ])

        m_client.new_event.reset_mock()
        m_client.new_event.return_value.fields.return_value = {}
        # swap out some trace fields
        tracer.add_trace_field('more', 'data!')
        tracer.remove_trace_field('another')

        span3 = tracer.start_span(context={'more': 'important_stuff'})
        self.assertEqual(tracer._state.stack[0], span)
        self.assertEqual(tracer._state.stack[1], span2)
        self.assertEqual(tracer._state.stack[-1], span3)
        # should have the second span id as its parent
        # should share the same trace id
        self.assertEqual(span.trace_id, span3.trace_id)
        self.assertEqual(span2.id, span3.parent_id)
        m_client.new_event.assert_called_once_with(data={
                'app.wide': 'events_are_great',
                'app.more': 'data!',
        })

    def test_add_rollup_field_propagates(self):
        m_client = Mock()
        tracer = SynchronousTracer(m_client)
        tracer._run_hooks_and_send = Mock()

        span1 = tracer.start_trace(context={'name': 'root'})
        event1 = m_client.new_event.return_value

        span2 = tracer.start_span(context={'name': 'middle'})
        event2 = m_client.new_event.return_value

        span3 = tracer.start_span(context={'name': 'inner1'})
        event3 = m_client.new_event.return_value

        tracer.add_rollup_field('database_ms', 17)
        tracer.add_rollup_field('calories', 180)
        tracer.add_rollup_field('database_ms', 23.1)

        event3.add_field.reset_mock()
        tracer.finish_span(span3)
        event3.add_field.assert_has_calls([
            call('database_ms', 17.0 + 23.1),
            call('calories', 180.0),
            call('duration_ms', ANY),
        ], any_order=True)

        span4 = tracer.start_span(context={'name': 'inner2'})
        event4 = m_client.new_event.return_value

        tracer.add_rollup_field('calories', 120)

        event4.add_field.reset_mock()
        tracer.finish_span(span4)
        event4.add_field.assert_has_calls([
            call('calories', 120.0),
            call('duration_ms', ANY),
        ], any_order=True)

        event2.add_field.reset_mock()
        tracer.finish_span(span2)
        event2.add_field.assert_has_calls([
            # This intermediate span doesn't get any rollup fields.
            call('duration_ms', ANY),
        ], any_order=True)

        event1.add_field.reset_mock()
        tracer.finish_span(span1)
        event1.add_field.assert_has_calls([
            call('rollup.database_ms', 17.0 + 23.1),
            call('rollup.calories', 180.0 + 120.0),
            call('duration_ms', ANY),
        ], any_order=True)

    def test_get_active_span(self):
        m_client = Mock()
        tracer = SynchronousTracer(m_client)
        span = tracer.start_trace()
        self.assertEquals(tracer.get_active_span().id, span.id)

    def test_run_hooks_and_send_no_hooks(self):
        ''' ensure send works when no hooks defined '''
        m_client = Mock()
        tracer = SynchronousTracer(m_client)
        m_span = Mock()

        with patch('beeline.trace._should_sample') as m_sample_fn:
            m_sample_fn.return_value = True
            tracer._run_hooks_and_send(m_span)

        # no hooks - trace's _should_sample is rigged to always return True, so we
        # always call send_presampled
        # send should never be called because at a minimum we always do deterministic
        # sampling
        m_span.event.send.assert_not_called() # pylint: disable=no-member
        m_span.event.send_presampled.assert_called_once_with() # pylint: disable=no-member

    def test_run_hooks_and_send_sampler(self):
        ''' ensure send works with a sampler hook defined '''
        m_client = Mock()
        tracer = SynchronousTracer(m_client)
        m_span = Mock()

        def _sampler_drop_all(fields):
            return False, 0

        tracer.register_hooks(sampler=_sampler_drop_all)

        with patch('beeline.trace._should_sample') as m_sample_fn:
            m_sample_fn.return_value = True
            tracer._run_hooks_and_send(m_span)

        # sampler ensures we drop everything
        m_span.event.send.assert_not_called() # pylint: disable=no-member
        m_span.event.send_presampled.assert_not_called() # pylint: disable=no-member

        def _sampler_drop_none(fields):
            return True, 100

        tracer.register_hooks(sampler=_sampler_drop_none)
        m_span.reset_mock()

        with patch('beeline.trace._should_sample') as m_sample_fn:
            m_sample_fn.return_value = True
            tracer._run_hooks_and_send(m_span)

        # sampler drops nothing, _should_sample rigged to always return true so
        # we always call send_presampled
        m_span.event.send.assert_not_called() # pylint: disable=no-member
        m_span.event.send_presampled.assert_called_once_with() # pylint: disable=no-member
        # ensure event is updated with new sample rate
        self.assertEqual(m_span.event.sample_rate, 100)

    def test_run_hooks_and_send_presend_hook(self):
        ''' ensure send works when presend hook is defined '''
        m_client = Mock()
        tracer = SynchronousTracer(m_client)
        m_span = Mock()

        def _presend_hook(fields):
            fields["thing i want"] = "put it there"
            del fields["thing i don't want"]

        m_span = Mock()
        m_span.event.fields.return_value = {
            "thing i don't want": "get it out of here",
            "happy data": "so happy",
        }

        tracer.register_hooks(presend=_presend_hook)

        with patch('beeline.trace._should_sample') as m_sample_fn:
            m_sample_fn.return_value = True
            tracer._run_hooks_and_send(m_span)

        m_span.event.send_presampled.assert_called_once_with() # pylint: disable=no-member
        self.assertDictEqual(
            m_span.event.fields(),
            {
                "thing i want": "put it there",
                "happy data": "so happy",
            },
        )

    def test_run_hooks_and_send_adds_trace_fields(self):
        ''' ensure trace fields are propagated backwards '''
        m_client = Mock()
        tracer = SynchronousTracer(m_client)
        m_span = Mock()
        m_span.event = Event()
        m_span.event.start_time = datetime.datetime.now()
        # set an existing trace field
        m_span.event.add_field('app.a', 1)
        m_span.rollup_fields = defaultdict(float)

        with patch('beeline.trace._should_sample') as m_sample_fn:
            m_sample_fn.return_value = True
            # add some trace fields
            tracer.add_trace_field('a', 0)
            tracer.add_trace_field('b', 2)
            tracer.add_trace_field('c', 3)
            tracer.finish_span(m_span)

        # ensure we only added fields b and c and did not try to overwrite a
        self.assertDictContainsSubset({'app.a': 1, 'app.b': 2, 'app.c': 3}, m_span.event.fields())

    def test_trace_context_manager_does_not_crash_if_span_is_none(self):
        m_client = Mock()
        tracer = SynchronousTracer(m_client)
        tracer.start_span = Mock()
        tracer.start_span.return_value = None
        tracer.finish_span = Mock()

        with tracer('foo'):
            pass

        tracer.start_span.assert_called_once_with(context={'name': 'foo'}, parent_id=None)

class TestTraceContext(unittest.TestCase):
    def test_marshal_trace_context(self):
        trace_id = "123456"
        parent_id = "654321"
        trace_fields = {"i": "like", "to": "trace"}

        trace_context = marshal_trace_context(trace_id, parent_id, trace_fields)

        trace_id_u, parent_id_u, trace_fields_u = unmarshal_trace_context(trace_context)
        self.assertEqual(trace_id_u, trace_id, "unmarshaled trace id should match original")
        self.assertEqual(parent_id_u, parent_id, "unmarshaled parent id should match original")
        self.assertDictEqual(trace_fields_u, trace_fields, "unmarshaled trace fields should match original")


class TestSpan(unittest.TestCase):
    def test_span_context(self):
        ev = Event()
        span = Span('', '', '', ev)
        span.add_context_field("some", "value")
        span.add_context({"another": "value"})
        self.assertDictEqual({
            "some": "value",
            "another": "value"
        }, ev.fields())
        span.remove_context_field("another")
        self.assertDictEqual({
            "some": "value",
        }, ev.fields())
"""Tests of reading server-sent events, as a client reads a job's stream (ADR 0138)."""

from azathoth.remote.server import server_sent
from azathoth.remote.sse import ServerSentEvent, read_server_sent


def read(
    text: str,
) -> list[ServerSentEvent]:
    return list(read_server_sent(text.split("\n")))


def test_each_event_is_read_with_its_name_data_and_id() -> None:
    assert read("id: 1\nevent: event\ndata: {}\n\nid: 2\nevent: finished\ndata: []\n\n") == [
        ServerSentEvent(name="event", data="{}", event_id="1"),
        ServerSentEvent(name="finished", data="[]", event_id="2"),
    ]


def test_what_a_remote_sends_is_read_back_as_it_was_sent() -> None:
    sent = server_sent("event", '{"type": "run_started"}', event_id=7)

    assert read(sent) == [
        ServerSentEvent(name="event", data='{"type": "run_started"}', event_id="7")
    ]


def test_a_comment_is_skipped_and_data_on_several_lines_is_joined() -> None:
    assert read(": still running\n\ndata: one\ndata: two\n\n") == [
        ServerSentEvent(name=None, data="one\ntwo", event_id=None)
    ]


def test_an_event_the_stream_ends_before_finishing_is_not_read() -> None:
    assert read("id: 1\nevent: event\ndata: {}") == []


def test_a_carriage_return_ends_a_line_as_a_line_break_does() -> None:
    assert read("event: finished\r\ndata: {}\r\n\r\n") == [
        ServerSentEvent(name="finished", data="{}", event_id=None)
    ]

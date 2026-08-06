"""Tests for PyAV video probing and frame decoding."""

from conversion.video import parse_frame_rate, probe_video_stream


def test_parse_frame_rate():
    assert parse_frame_rate("30/1") == 30.0
    assert parse_frame_rate("15") == 15.0
    assert parse_frame_rate("invalid") == 15.0
    assert parse_frame_rate("30/0") == 15.0


def test_probe_video_stream_invalid_data():
    duration, fps, frames = probe_video_stream(b"invalid data")
    assert duration == 0.0
    assert fps == 15.0
    assert frames == 0

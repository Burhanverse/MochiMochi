"""Tests for animated WebP decimation ladder and WebP output checks."""

from PIL import Image

from conversion.animated import (
    _count_webp_frames,
    _encode_animated_webp_under_limit,
    is_valid_webp_output,
)


def test_encode_animated_webp_under_limit():
    frames = [Image.new("RGBA", (512, 512), (i * 20, 100, 100, 255)) for i in range(5)]
    output = _encode_animated_webp_under_limit(frames, frame_duration_ms=100)
    data = output.getvalue()
    output.close()
    for f in frames:
        f.close()

    assert len(data) > 0
    valid, reason = is_valid_webp_output(data, require_animated=True)
    assert valid is True, f"Failed validation: {reason}"
    assert _count_webp_frames(data) >= 2

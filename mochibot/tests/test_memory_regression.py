"""Memory regression test using tracemalloc to assert RSS growth bounds across sticker conversions."""

import tracemalloc

from PIL import Image

from conversion.animated import _encode_animated_webp_under_limit
from conversion.static import convert_to_whatsapp_static


def test_memory_regression_static_conversion():
    tracemalloc.start()
    snapshot1 = tracemalloc.take_snapshot()

    # Repeatedly convert images
    for _ in range(50):
        with Image.new("RGBA", (512, 512), (100, 150, 200, 255)) as img:
            out = convert_to_whatsapp_static(img)
            _ = out.getvalue()
            out.close()

    snapshot2 = tracemalloc.take_snapshot()
    top_stats = snapshot2.compare_to(snapshot1, 'lineno')

    total_diff = sum(item.size_diff for item in top_stats)
    tracemalloc.stop()

    # Assert net memory growth over 50 iterations stays under 2MB
    assert total_diff < 2 * 1024 * 1024, f"Memory growth too high: {total_diff / (1024*1024):.2f} MB"


def test_memory_regression_animated_conversion():
    tracemalloc.start()
    snapshot1 = tracemalloc.take_snapshot()

    for _ in range(10):
        frames = [Image.new("RGBA", (512, 512), (i * 30, 50, 150, 255)) for i in range(5)]
        out = _encode_animated_webp_under_limit(frames, frame_duration_ms=100)
        _ = out.getvalue()
        out.close()
        for f in frames:
            f.close()

    snapshot2 = tracemalloc.take_snapshot()
    top_stats = snapshot2.compare_to(snapshot1, 'lineno')

    total_diff = sum(item.size_diff for item in top_stats)
    tracemalloc.stop()

    # Assert net memory growth over 10 iterations stays under 3MB
    assert total_diff < 3 * 1024 * 1024, f"Memory growth too high: {total_diff / (1024*1024):.2f} MB"

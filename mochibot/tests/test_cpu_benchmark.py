"""CPU load-test benchmark for batch sticker conversion."""

import os
import time

from PIL import Image

from conversion.animated import _encode_animated_webp_under_limit
from conversion.static import convert_to_whatsapp_static


def test_batch_conversion_cpu_load():
    start_time = time.process_time()
    start_wall = time.monotonic()

    # Simulate converting a 30-sticker pack (15 static + 15 animated)
    static_count = 15
    anim_count = 15

    for _ in range(static_count):
        with Image.new("RGBA", (512, 512), (100, 200, 100, 255)) as img:
            out = convert_to_whatsapp_static(img)
            _ = out.getvalue()
            out.close()

    for _ in range(anim_count):
        frames = [Image.new("RGBA", (512, 512), (i * 20, 120, 200, 255)) for i in range(4)]
        out = _encode_animated_webp_under_limit(frames, frame_duration_ms=100)
        _ = out.getvalue()
        out.close()
        for f in frames:
            f.close()

    end_wall = time.monotonic()
    end_time = time.process_time()

    wall_duration = end_wall - start_wall
    cpu_duration = end_time - start_time
    cpu_utilization = (cpu_duration / wall_duration * 100.0) if wall_duration > 0 else 0.0

    print("\n--- CPU Load Test Results ---")
    print(f"Host Cores: {os.cpu_count()}")
    print("Batch: 30 stickers (15 static + 15 animated)")
    print(f"Wall-clock duration: {wall_duration:.2f} seconds")
    print(f"CPU time: {cpu_duration:.2f} seconds")
    print(f"Sustained CPU utilization: {cpu_utilization:.1f}%")
    print("------------------------------")

    # Assert 30-sticker batch completes reasonably fast (< 10 wall-clock seconds)
    assert wall_duration < 10.0, f"Batch conversion took too long ({wall_duration:.2f}s)"

"""Test suite configuration and shared fixtures."""

from io import BytesIO

import numpy as np
import pytest
from PIL import Image


@pytest.fixture
def sample_static_image_bytes():
    # Create a 512x512 image with noise so PNG size > 3KB (to pass min_size verification check)
    arr = np.random.randint(0, 255, (512, 512, 4), dtype=np.uint8)
    arr[:, :, 3] = 255  # fully opaque
    img = Image.fromarray(arr, mode="RGBA")
    buf = BytesIO()
    img.save(buf, format="PNG")
    val = buf.getvalue()
    buf.close()
    img.close()
    return val


@pytest.fixture
def sample_transparent_image_bytes():
    img = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    buf = BytesIO()
    img.save(buf, format="PNG")
    val = buf.getvalue()
    buf.close()
    img.close()
    return val

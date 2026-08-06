"""Tests for static WebP conversion and sticker verification."""

from io import BytesIO

import pytest
from PIL import Image

from conversion.static import (
    convert_to_whatsapp_one_frame_animation,
    convert_to_whatsapp_static,
    verify_sticker,
)


def test_convert_to_whatsapp_static(sample_static_image_bytes):
    with Image.open(BytesIO(sample_static_image_bytes)) as img:
        output = convert_to_whatsapp_static(img)
        val = output.getvalue()
        output.close()
        assert len(val) > 0
        assert len(val) <= 100 * 1024
        with Image.open(BytesIO(val)) as result:
            assert result.size == (512, 512)
            assert result.format == "WEBP"


def test_convert_to_whatsapp_one_frame_animation(sample_static_image_bytes):
    with Image.open(BytesIO(sample_static_image_bytes)) as img:
        output = convert_to_whatsapp_one_frame_animation(img)
        val = output.getvalue()
        output.close()
        assert len(val) > 0
        assert len(val) <= 500 * 1024


@pytest.mark.asyncio
async def test_verify_sticker(sample_static_image_bytes):
    res = await verify_sticker(sample_static_image_bytes, is_animated=False, is_video=False, file_id="test12345")
    assert res['valid'] is True
    assert res['reason'] == ''


@pytest.mark.asyncio
async def test_verify_sticker_too_small():
    res = await verify_sticker(b"tiny", is_animated=False, is_video=False, file_id="test12345")
    assert res['valid'] is False
    assert "too small" in res['reason']

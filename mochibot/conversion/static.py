"""Static sticker conversion and verification functions."""

import gzip
import logging
from io import BytesIO

import numpy as np
from PIL import Image

from config import WA_MAX_BYTES

logger = logging.getLogger(__name__)


def convert_to_whatsapp_static(img: Image.Image) -> BytesIO:
    """Converts a PIL Image to a 512x512 static WebP under 100KB."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    canvas = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    try:
        frame = img.copy()
        frame.thumbnail((512, 512), Image.LANCZOS)
        position = ((512 - frame.width) // 2, (512 - frame.height) // 2)
        canvas.paste(frame, position, frame)
        frame.close()
    finally:
        pass

    output = BytesIO()
    quality = 95
    max_attempts = 10
    for attempt in range(max_attempts):
        output.seek(0)
        output.truncate(0)
        canvas.save(output, format="WEBP", quality=quality)
        size = output.tell()
        if size <= 100 * 1024:
            break
        if quality > 75:
            quality -= 5
        elif quality > 50:
            quality -= 10
        else:
            quality -= 15
        if quality < 5:
            logger.warning(f"Static sticker is {size/1024:.1f}KB, exceeds 100KB limit")
            break

    canvas.close()
    output.seek(0)
    return output


def _convert_static_bytes_to_webp(sticker_data: bytes) -> BytesIO:
    with Image.open(BytesIO(sticker_data)) as img:
        return convert_to_whatsapp_static(img)


def convert_to_whatsapp_one_frame_animation(img: Image.Image) -> BytesIO:
    """Converts a static PIL image to a 2-frame loop WebP to satisfy WhatsApp animated sticker requirements."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    canvas = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    try:
        frame = img.copy()
        frame.thumbnail((512, 512), Image.LANCZOS)
        position = ((512 - frame.width) // 2, (512 - frame.height) // 2)
        canvas.paste(frame, position, frame)
        frame.close()

        frame2 = canvas.copy()
        px = frame2.load()
        r, g, b, a = px[0, 0]
        px[0, 0] = (r, g, b, 1 if a == 0 else 0)

        output = BytesIO()
        attempts = [
            (85, 0, 90), (75, 0, 85), (65, 4, 80),
            (55, 4, 75), (45, 6, 70), (35, 6, 65),
        ]
        for quality, method, alpha_quality in attempts:
            output.seek(0)
            output.truncate(0)
            canvas.save(
                output, format="WEBP", save_all=True,
                append_images=[frame2],
                duration=[100, 100], loop=0,
                quality=quality, method=method,
                alpha_quality=alpha_quality,
                background=(0, 0, 0, 0), lossless=False
            )
            if output.tell() <= WA_MAX_BYTES:
                frame2.close()
                canvas.close()
                output.seek(0)
                return output

        frame2.close()
    finally:
        canvas.close()

    raise Exception("Could not encode one-frame animation under 500KB")


async def verify_sticker(sticker_data: bytes, is_animated: bool, is_video: bool, file_id: str) -> dict:
    """Validates raw sticker data prior to conversion."""
    result = {'valid': True, 'reason': '', 'warnings': []}
    try:
        min_size = 3 * 1024
        if len(sticker_data) < min_size:
            result['valid'] = False
            result['reason'] = f"File too small ({len(sticker_data)} bytes, minimum: {min_size} bytes) - likely corrupt or invalid"
            return result

        max_size = 500 * 1024
        if len(sticker_data) > max_size:
            result['warnings'].append(f"Large file ({len(sticker_data)} bytes), will be compressed")

        if is_animated:
            try:
                with gzip.open(BytesIO(sticker_data), 'rb') as f:
                    json_data = f.read()
                    if len(json_data) < 50:
                        result['valid'] = False
                        result['reason'] = "TGS file appears empty or corrupt"
                        return result
            except Exception as e:
                result['valid'] = False
                result['reason'] = f"Invalid TGS format: {e!s}"
                return result

        elif is_video:
            if not (len(sticker_data) >= 4 and sticker_data[:4] == b'\x1a\x45\xdf\xa3'):
                result['valid'] = False
                result['reason'] = "Not a valid WebM file (bad magic bytes)"
                return result

        else:
            try:
                with Image.open(BytesIO(sticker_data)) as img:
                    img.verify()
                with Image.open(BytesIO(sticker_data)) as img:
                    if img.width < 10 or img.height < 10:
                        result['valid'] = False
                        result['reason'] = f"Image too small ({img.width}x{img.height})"
                        return result

                    if img.width > 5000 or img.height > 5000:
                        result['warnings'].append(f"Large dimensions ({img.width}x{img.height}), will be resized")

                    if img.mode in ('RGBA', 'LA'):
                        alpha = np.array(img.convert('RGBA'))[:, :, 3]
                        max_alpha = int(alpha.max())
                        if max_alpha == 0:
                            result['valid'] = False
                            result['reason'] = "Image is completely transparent (empty)"
                            return result
                        transparency_ratio = float((alpha < 10).sum()) / alpha.size
                        if transparency_ratio > 0.95:
                            result['warnings'].append(f"Image is {transparency_ratio*100:.1f}% transparent")

                    extrema = img.convert('RGB').getextrema()
                    if all(min_val == max_val for min_val, max_val in extrema):
                        result['warnings'].append("Image appears to be solid color")

            except Exception as e:
                result['valid'] = False
                result['reason'] = f"Invalid image format: {e!s}"
                return result

        logger.info(f"Sticker {file_id[-8:]} verified: valid={result['valid']}, warnings={len(result['warnings'])}")
        return result

    except Exception as e:
        result['valid'] = False
        result['reason'] = f"Verification error: {e!s}"
        return result

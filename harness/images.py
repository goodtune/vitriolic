"""Photographs for the seeded news: a coloured block with the title in type.

Nothing is downloaded and nothing real is photographed. The colour comes from
the title, so the same title always draws the same picture.
"""

import hashlib
import io
import textwrap

from django.core.files.base import ContentFile
from django.utils.text import slugify
from PIL import Image, ImageDraw, ImageFont

#: The title type is this fraction of the picture's height.
TYPE_SIZE = 0.09


def _colours(title: str) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """A dark and a lighter shade of one hue, taken from a hash of the title."""
    digest = hashlib.sha256(title.encode()).digest()
    base = tuple(40 + digest[i] % 120 for i in range(3))
    lighter = tuple(min(255, channel + 70) for channel in base)
    return base, lighter  # type: ignore[return-value]


def photo(title: str, size: tuple[int, int] = (1200, 800)) -> ContentFile:
    """A JPEG of ``size``: a diagonal blend of two shades and ``title`` on it."""
    width, height = size
    dark, light = _colours(title)

    # Draw the blend small and enlarge it: smooth, and quick for any size.
    blend = Image.new("RGB", (2, 2))
    blend.putdata([dark, light, light, dark])
    image = blend.resize(size, Image.Resampling.BICUBIC)

    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=round(height * TYPE_SIZE))
    average_character = draw.textlength("n", font=font)
    columns = max(8, int(width * 0.8 // average_character))
    text = "\n".join(textwrap.wrap(title, columns))
    draw.multiline_text(
        (width // 2, height // 2),
        text,
        font=font,
        fill=(255, 255, 255),
        anchor="mm",
        align="center",
        spacing=round(height * 0.02),
    )

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    return ContentFile(buffer.getvalue(), name="%s.jpg" % slugify(title))

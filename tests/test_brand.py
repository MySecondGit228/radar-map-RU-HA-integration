"""Brand asset packaging tests."""

from __future__ import annotations

import struct
from pathlib import Path

BRAND_DIR = Path(__file__).parents[1] / "custom_components" / "radar_map" / "brand"


def _png_size(path: Path) -> tuple[int, int]:
    """Read dimensions directly from a PNG IHDR chunk."""
    data = path.read_bytes()[:24]
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


def test_brand_icons_have_home_assistant_dimensions() -> None:
    """Ship both standard and high-DPI square integration icons."""
    assert _png_size(BRAND_DIR / "icon.png") == (256, 256)
    assert _png_size(BRAND_DIR / "icon@2x.png") == (512, 512)

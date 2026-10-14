"""Synthetic file headers exercise image rules without a pixel decoder."""

import struct
from typing import Any

import pytest

from pptviper.image_headers import dimensions, image_checks


def header(kind, width=300, height=200):
    if kind == "PNG":
        return (
            b"\x89PNG\r\n\x1a\n"
            + struct.pack(">I", 13)
            + b"IHDR"
            + struct.pack(">II", width, height)
            + bytes(9)
        )
    if kind == "GIF":
        return b"GIF89a" + struct.pack("<HH", width, height)
    if kind == "BMP":
        return b"BM" + bytes(12) + struct.pack("<Iii", 40, width, height) + bytes(28)
    return (
        b"\xff\xd8\xff\xc0"
        + struct.pack(">HBHHB", 8, 8, height, width, 3)
        + b"\xff\xd9"
    )


@pytest.mark.parametrize("kind", ["PNG", "JPEG", "GIF", "BMP"])
def test_dimensions_and_exact_aspect(kind):
    info = dimensions(header(kind))
    assert info["width"] == 300 and info["height"] == 200 and not info["unknown"]
    meta: dict[str, Any] = dict(header=info, size=["914400", "609600"], crop={})
    assert not image_checks(meta)["image-distorted"].hit
    meta["size"][0] = "914401"
    assert image_checks(meta)["image-distorted"].hit


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"not an image",
        b"\xff\xd8\xff\xe0\x00\x01",
        b"\xff\xd8\xff",
        header("PNG")[:20],
    ],
)
def test_unsupported_or_truncated(data):
    assert dimensions(data)["unknown"]


def test_dpi_boundary_and_crop():
    meta: dict[str, Any] = dict(
        header=dimensions(header("PNG", 150, 150)), size=["914400", "914400"], crop={}
    )
    assert not image_checks(meta)["image-low-resolution"].hit
    meta["size"][0] = "914401"
    assert image_checks(meta)["image-low-resolution"].hit
    meta["crop"] = {"l": "-1"}
    assert image_checks(meta)["image-crop-outside"].hit
    meta["crop"] = {"l": "100000"}
    assert image_checks(meta)["image-distorted"].unknown

"""Bounded image header inspection, without decoding image pixels."""

import struct
from fractions import Fraction as F
from typing import Any


def dimensions(data: bytes) -> dict[str, Any]:
    """Read dimensions from at most the caller's bounded prefix (64 KiB in OPC)."""
    width = height = 0
    kind = "unknown"
    try:
        if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 33:
            if data[8:16] != b"\0\0\0\rIHDR":
                raise ValueError
            width, height = struct.unpack(">II", data[16:24])
            kind = "PNG"
        elif data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
            width, height = struct.unpack("<HH", data[6:10])
            kind = "GIF"
        elif data.startswith(b"BM") and len(data) >= 26:
            dib = struct.unpack("<I", data[14:18])[0]
            if dib == 12:
                width, height = struct.unpack("<HH", data[18:22])
            elif dib >= 40 and len(data) >= 54:
                width, height = struct.unpack("<ii", data[18:26])
                height = abs(height)
            else:
                raise ValueError
            kind = "BMP"
        elif data.startswith(b"\xff\xd8"):
            offset = 2
            while offset < len(data):
                if data[offset] != 255:
                    raise ValueError
                while offset < len(data) and data[offset] == 255:
                    offset += 1
                marker = data[offset]
                offset += 1
                if marker in (0xD9, 0xDA):
                    break
                if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                    continue
                length = int.from_bytes(data[offset : offset + 2], "big")
                if length < 2 or offset + length > len(data):
                    raise ValueError
                if marker in (
                    0xC0,
                    0xC1,
                    0xC2,
                    0xC3,
                    0xC5,
                    0xC6,
                    0xC7,
                    0xC9,
                    0xCA,
                    0xCB,
                    0xCD,
                    0xCE,
                    0xCF,
                ):
                    if length < 8:
                        raise ValueError
                    height, width = struct.unpack(">HH", data[offset + 3 : offset + 7])
                    kind = "JPEG"
                    break
                offset += length
        if width <= 0 or height <= 0:
            raise ValueError
        return dict(format=kind, width=width, height=height, unknown=[])
    except (ValueError, IndexError, struct.error):
        return dict(
            format=kind,
            width=None,
            height=None,
            unknown=[
                "Unsupported, invalid or truncated image header (64 KiB prefix limit)"
            ],
        )


def image_checks(meta: dict[str, Any]) -> dict[str, Any]:
    """Exact cross products and DPI for the stored unrotated picture extent."""
    from pptviper.rules import Result, missing

    crop = meta.get("crop", {})
    try:
        left, top, right, bottom = (F(crop.get(k, "0")) for k in ("l", "t", "r", "b"))
    except (ValueError, TypeError, ZeroDivisionError):
        return {
            rule: missing("Invalid saved crop")
            for rule in (
                "image-crop-outside",
                "image-distorted",
                "image-low-resolution",
            )
        }
    results = {
        "image-crop-outside": Result(
            hit=min(left, top, right, bottom) < 0,
            value=min(left, top, right, bottom),
            unit="crop-percent",
            details=dict(crop=crop),
            threshold=0,
        )
    }
    info = meta.get("header", {})
    try:
        pixels_w = F(info["width"]) * (1 - (left + right) / 100000)
        pixels_h = F(info["height"]) * (1 - (top + bottom) / 100000)
        width, height = map(F, meta["size"])
        if min(pixels_w, pixels_h, width, height) <= 0:
            raise ValueError
    except (KeyError, ValueError, TypeError, ZeroDivisionError):
        reason = "Image dimensions, visible crop or displayed extent are unavailable"
        results.update(
            {
                name: missing(reason)
                for name in ("image-distorted", "image-low-resolution")
            }
        )
        return results
    cross = width * pixels_h - height * pixels_w
    dpi = min(pixels_w * 914400 / width, pixels_h * 914400 / height)
    results["image-distorted"] = Result(
        hit=cross != 0,
        value=abs(cross),
        unit="EMU-pixels",
        details=dict(
            display_emu=[str(width), str(height)],
            visible_pixels=[str(pixels_w), str(pixels_h)],
            cross_product=str(cross),
        ),
        threshold=0,
    )
    results["image-low-resolution"] = Result(
        hit=dpi < 150,
        value=dpi,
        unit="dpi",
        details=dict(
            horizontal_dpi=str(pixels_w * 914400 / width),
            vertical_dpi=str(pixels_h * 914400 / height),
        ),
        threshold=150,
    )
    return results

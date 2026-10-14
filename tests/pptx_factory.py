"""Minimal helpers for generating PPTX fixtures and malformed inputs."""

from io import BytesIO
from zipfile import ZipFile

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Emu


def single_shape_pptx(*, x: int, y: int, width: int, height: int) -> bytes:
    """Create one shape with integer EMU coordinates and dimensions."""
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(x), Emu(y), Emu(width), Emu(height))
    stream = BytesIO()
    presentation.save(stream)
    return stream.getvalue()


def replace_part(package: bytes, name: str, content: bytes | None) -> bytes:
    """Replace an existing part, or delete it when content is None."""
    output = BytesIO()
    with ZipFile(BytesIO(package)) as source, ZipFile(output, "w") as target:
        if name not in source.namelist():
            raise KeyError(name)
        for entry in source.infolist():
            if entry.filename == name:
                if content is not None:
                    target.writestr(entry, content)
            else:
                target.writestr(entry, source.read(entry))
    return output.getvalue()


def truncate_zip(package: bytes, offset: int) -> bytes:
    """Truncate the ZIP archive at the specified byte offset."""
    if not 0 <= offset < len(package):
        raise ValueError("Truncation offset must be within the ZIP byte array")
    return package[:offset]

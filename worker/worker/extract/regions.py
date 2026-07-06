"""Vertical region bands of the standard Fiche Suiveuse template.

A single full-page scan downsamples the dense operations table below the VLM's
effective resolution, so cramped handwritten digits/matricules get misread and
rows near blank stretches get misaligned. Cropping the page into focused bands
and extracting each in its own short call (see GroqClient) gives the model far
more effective resolution per row and a much shorter output to keep aligned.

Bands are expressed as fractions of page height and overlap slightly so a row
straddling a boundary stays fully visible in at least one crop. They track the
fixed printed template, not any one scan's content.
"""

from dataclasses import dataclass, field
from io import BytesIO

from fiche_schema import PARTIE_1_OPERATIONS, PARTIE_2_OPERATIONS
from PIL import Image

from .prompt import P1_INDICES, P2_INDICES, build_controls_prompt, build_header_prompt, build_operations_prompt

_OPERATIONS = PARTIE_1_OPERATIONS + PARTIE_2_OPERATIONS


@dataclass(frozen=True)
class Region:
    name: str
    y0: float  # top, as a fraction of page height
    y1: float  # bottom, as a fraction of page height
    prompt: str
    # Which top-level keys this region's response is expected to contribute,
    # used to assemble the combined raw dict before merge_extraction.
    contributes: tuple[str, ...]
    # For operations regions: {canonical operation name → global row index}, so
    # a label-anchored response can be mapped back to the right row (fuzzy).
    op_names: dict[str, int] = field(default_factory=dict)


def _op_names(indices: tuple[int, ...]) -> dict[str, int]:
    return {_OPERATIONS[i]: i for i in indices}


# Header/operations_p1 used to overlap by only 1% (0.16-0.17) — too thin: on
# a real scan the "Qté:" label landed just past 0.17, outside the header crop
# entirely, so the header-extraction call had no pixels to read it from
# (qte came back unread). Widened header's bottom edge and operations_p2's
# bottom edge so a few percent of per-page layout variance can't push a
# field/row outside every crop that's supposed to cover it.
REGIONS: tuple[Region, ...] = (
    Region("header", 0.04, 0.20, build_header_prompt(), ("header",)),
    Region("operations_p1", 0.16, 0.50, build_operations_prompt(P1_INDICES), ("operations",), _op_names(P1_INDICES)),
    Region("operations_p2", 0.47, 0.88, build_operations_prompt(P2_INDICES), ("operations",), _op_names(P2_INDICES)),
    Region("controls", 0.80, 1.0, build_controls_prompt(), ("controls", "items")),
)


def crop_band(image_bytes: bytes, region: Region, *, jpeg_quality: int = 92) -> bytes:
    """Crop the full-page raster to `region`'s vertical band, full width."""
    im = Image.open(BytesIO(image_bytes)).convert("RGB")
    w, h = im.size
    band = im.crop((0, int(h * region.y0), w, int(h * region.y1)))
    buf = BytesIO()
    band.save(buf, format="JPEG", quality=jpeg_quality)
    return buf.getvalue()

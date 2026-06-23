"""Auto-orient a scanned fiche before extraction.

Fiches are landscape forms, but phone scanners (CamScanner, TapScanner…) often
export pages rotated 90/180/270°. A sideways page wrecks both the on-screen
view and the VLM's reading accuracy, so we upright it first.

Primary signal: the **Agilink logo**, which sits in the top-left only when the
page is upright. We template-match it across the four rotations (multi-scale)
and pick the one where it lands strongly in the top-left — a document-specific
anchor that proved more reliable than text OSD on these scans. Tesseract OSD is
the fallback when the logo can't be found (poor scan / non-fiche page), and a
portrait-vs-landscape heuristic is the last resort.
"""

import io
import os

import cv2
import numpy as np
from PIL import Image

try:  # tesseract is optional; degrade gracefully if the binary is missing
    import pytesseract

    _HAS_TESS = True
except Exception:  # noqa: BLE001
    _HAS_TESS = False

_LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "agilink_logo.png")
_TEMPLATE = cv2.imread(_LOGO_PATH, cv2.IMREAD_GRAYSCALE)
# Correct rotations score ~0.39–0.62 on real scans; below this the logo wasn't
# confidently found at any rotation, so we defer to OSD instead of guessing.
_LOGO_FLOOR = 0.34
_DETECT_LONG_SIDE = 1400  # downscale before matching — orientation needs no detail

_ROT = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}


def _rot(img: np.ndarray, r: int) -> np.ndarray:
    return img if r == 0 else cv2.rotate(img, _ROT[r])


def _logo_rotation(gray: np.ndarray) -> tuple[int, float]:
    """Clockwise degrees that put the Agilink logo upright in the top-left,
    plus the match score (best across rotations/scales)."""
    if _TEMPLATE is None:
        return 0, 0.0
    th0, tw0 = _TEMPLATE.shape
    best_r, best = 0, -9.0
    for r in (0, 90, 180, 270):
        rot = _rot(gray, r)
        h, w = rot.shape
        score = -9.0
        for s in (0.07, 0.09, 0.11, 0.14, 0.17, 0.21):  # logo width as fraction of page width
            tw = int(w * s)
            if tw < 24:
                continue
            th = max(1, int(th0 * tw / tw0))
            if th >= h or tw >= w:
                continue
            res = cv2.matchTemplate(rot, cv2.resize(_TEMPLATE, (tw, th)), cv2.TM_CCOEFF_NORMED)
            _, maxv, _, maxloc = cv2.minMaxLoc(res)
            in_tl = maxloc[0] < w * 0.45 and maxloc[1] < h * 0.22  # only top-left when upright
            score = max(score, maxv if in_tl else maxv - 0.25)
        if score > best:
            best, best_r = score, r
    return best_r, best


def _osd_rotation(pil: "Image.Image") -> int | None:
    if not _HAS_TESS:
        return None
    try:
        osd = pytesseract.image_to_osd(pil, output_type=pytesseract.Output.DICT)
        return int(osd.get("rotate", 0)) % 360
    except Exception:  # noqa: BLE001 — OSD has no confident reading
        return None


def correct_orientation(image_bytes: bytes) -> tuple[bytes, int]:
    """Return (upright_jpeg_bytes, clockwise_degrees_applied). The angle is one
    of 0/90/180/270 and is stored on the fiche so the API renders the scan the
    same way up."""
    try:
        pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:  # noqa: BLE001
        return image_bytes, 0

    # Downscale a copy just for detection (matching full-res is needlessly slow).
    det = pil.copy()
    det.thumbnail((_DETECT_LONG_SIDE, _DETECT_LONG_SIDE))
    gray = cv2.cvtColor(np.asarray(det), cv2.COLOR_RGB2GRAY)

    r, score = _logo_rotation(gray)
    if score < _LOGO_FLOOR:  # logo not found → text OSD, then shape heuristic
        r = _osd_rotation(det)
        if r is None:
            r = 90 if pil.height > pil.width else 0
    r = (r or 0) % 360
    if r == 0:
        return image_bytes, 0

    corrected = pil.rotate(-r, expand=True)  # PIL rotates CCW; -r == clockwise r
    buf = io.BytesIO()
    corrected.save(buf, format="JPEG", quality=92)
    return buf.getvalue(), r

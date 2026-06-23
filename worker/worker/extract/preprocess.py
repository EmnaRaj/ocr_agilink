"""Deterministic image enhancement, run before any model/OCR call.

A scanned blue-pen fiche has low contrast between ink and the slightly grey
paper. Normalising it — grayscale + CLAHE (local contrast) + an unsharp mask —
makes the handwritten strokes darker and crisper, which measurably reduces
digit confusion downstream, for both the VLM and (later) a dedicated OCR
engine. Pure OpenCV, no model, fully deterministic.

Deliberately conservative: no aggressive deskew/binarisation here — the scanner
app already deskews, and over-processing amplifies scan noise. Tune via the
constants below.
"""

from io import BytesIO

import cv2
import numpy as np

_CLAHE_CLIP = 2.0
_CLAHE_GRID = (8, 8)
_UNSHARP_AMOUNT = 0.6  # 0 = none, 1 = strong
_JPEG_QUALITY = 92


def enhance(image_bytes: bytes) -> bytes:
    """Grayscale + CLAHE + gentle unsharp mask; returns JPEG bytes.

    Returns the original bytes unchanged if decoding fails, so a preprocessing
    hiccup can never break extraction.
    """
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return image_bytes

    clahe = cv2.createCLAHE(clipLimit=_CLAHE_CLIP, tileGridSize=_CLAHE_GRID)
    img = clahe.apply(img)

    if _UNSHARP_AMOUNT > 0:
        blur = cv2.GaussianBlur(img, (0, 0), sigmaX=2.0)
        img = cv2.addWeighted(img, 1 + _UNSHARP_AMOUNT, blur, -_UNSHARP_AMOUNT, 0)

    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, _JPEG_QUALITY])
    return buf.tobytes() if ok else image_bytes

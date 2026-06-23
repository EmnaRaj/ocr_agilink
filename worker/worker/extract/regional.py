import base64
import json
import logging
import time
from abc import abstractmethod
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher

from fiche_schema import FicheExtraction, merge_extraction

from .base import VLMClient
from .errors import VLMExtractionError
from .preprocess import enhance
from .regions import REGIONS, Region, crop_band

logger = logging.getLogger(__name__)

# Even at temperature=0, hosted inference isn't perfectly deterministic; a few
# retries absorb transient flakiness (malformed-JSON 400s, transient 5xx)
# without masking a genuinely broken prompt/schema (which fails every attempt).
_MAX_ATTEMPTS = 3


class RegionalVLMClient(VLMClient):
    """Shared region-by-region extraction; backends differ only in `_complete`.

    A single full-page A4 scan downsamples the dense operations table below the
    VLM's effective resolution, causing digit misreads and row misalignment.
    Instead, the page is cropped into focused section bands (header, Partie 1,
    Partie 2, controls) and each is read in its own short, focused call, then
    the partial results are assembled onto the canonical skeleton (regions.py,
    `merge_extraction`). This orchestration is provider-agnostic — Groq (cloud
    POC) and self-hosted vLLM/Qwen2.5-VL (production) only differ in how a
    single chat-completion request is made, which is `_complete`.
    """

    _model: str  # set by each subclass's __init__

    def extract(self, image_bytes: bytes, *, mime_type: str = "image/png") -> FicheExtraction:
        # Deterministic enhancement (contrast/sharpen) before any model call —
        # makes the handwriting crisper for the VLM. See preprocess.enhance.
        image_bytes = enhance(image_bytes)
        combined: dict = {}
        failures: list[str] = []

        # Whole-section crops (header, the two operation Parties, controls). A
        # strong VLM (Qwen3-VL) reads a full section correctly — it maps each
        # filled row to its printed label (no shift) AND, seeing the whole
        # column, leaves blank heure_fin/outillage cells blank instead of
        # fabricating them. The four calls are independent, so run them in
        # parallel.
        def do_region(region: Region) -> tuple[Region, dict | None, Exception | None]:
            try:
                return region, self._extract_region(image_bytes, region), None
            except VLMExtractionError as exc:
                return region, None, exc

        with ThreadPoolExecutor(max_workers=len(REGIONS)) as pool:
            results = list(pool.map(do_region, REGIONS))

        for region, raw, exc in results:
            if exc is not None:
                logger.warning("region %s extraction failed: %s", region.name, exc)
                failures.append(region.name)
            else:
                _absorb(combined, region, raw)

        if len(failures) == len(REGIONS):
            raise VLMExtractionError(f"All extraction regions failed: {', '.join(failures)}")

        try:
            return merge_extraction(combined, model_name=self._model)
        except (KeyError, ValueError, TypeError) as exc:
            raise VLMExtractionError(f"Assembled response didn't match the expected shape: {exc}") from exc

    def _extract_region(self, image_bytes: bytes, region: Region) -> dict:
        band = crop_band(image_bytes, region)
        data_uri = "data:image/jpeg;base64," + base64.b64encode(band).decode()
        return self._complete_with_retry(data_uri, region.prompt)

    def _complete_with_retry(self, data_uri: str, prompt: str, temperature: float = 0.0) -> dict:
        last_error: VLMExtractionError | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                return self._complete(data_uri, prompt, temperature=temperature)
            except VLMExtractionError as exc:
                last_error = exc
                time.sleep(0.4 * (attempt + 1))  # gentle backoff for rate limits
        raise last_error

    @abstractmethod
    def _complete(self, data_uri: str, prompt: str, temperature: float = 0.0) -> dict:
        """Run ONE chat-completion on a region crop and return the parsed JSON.

        Implementations MUST translate any provider/transport/truncation/parse
        failure into a `VLMExtractionError` so the retry loop and per-region
        degradation above can handle every backend uniformly.
        """


def _parse_json_response(content: str | None, finish_reason: str | None, *, backend: str) -> dict:
    """Shared response handling for OpenAI-compatible backends."""
    if finish_reason == "length":
        raise VLMExtractionError(
            f"{backend} response was truncated (hit max tokens); got {len(content or '')} chars"
        )
    if not content:
        raise VLMExtractionError(f"{backend} returned an empty response")
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise VLMExtractionError(f"{backend} response was not valid JSON: {exc}\n{content!r}") from exc


def _match_operation(label: object, op_names: dict[str, int]) -> int | None:
    """Fuzzy-map a printed operation label the model read to its global row index.

    The model copies the printed label off the form (its strength); we snap it to
    the canonical name. A high cutoff avoids mapping a misread onto the wrong row.
    """
    if not label or not op_names:
        return None
    s = str(label).strip().lower()
    best_idx, best_score = None, 0.0
    for name, idx in op_names.items():
        score = SequenceMatcher(None, s, name.lower()).ratio()
        if score > best_score:
            best_idx, best_score = idx, score
    return best_idx if best_score >= 0.6 else None


def _absorb(combined: dict, region: Region, raw: dict) -> None:
    """Fold one region's raw response into the combined whole-sheet dict."""
    for key in region.contributes:
        if key == "operations":
            combined.setdefault("operations", {})
            rows = raw.get("rows")
            if isinstance(rows, list):
                # Label-anchored: each row carries the printed operation name it
                # read; map it to the canonical index instead of trusting order.
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    idx = _match_operation(row.get("operation"), region.op_names)
                    if idx is not None:
                        combined["operations"][str(idx)] = {
                            k: v for k, v in row.items() if k != "operation"
                        }
            else:
                # Backward-compatible: tolerate an index-keyed object.
                ops = raw.get("operations")
                if not isinstance(ops, dict):
                    ops = {k: v for k, v in raw.items() if k.isdigit()}
                combined["operations"].update(ops)
        elif key == "items":
            if isinstance(raw.get("items"), list):
                combined["items"] = raw["items"]
        else:  # "header" or "controls"
            if isinstance(raw.get(key), dict):
                combined[key] = raw[key]

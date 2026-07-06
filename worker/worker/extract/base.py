from abc import ABC, abstractmethod

from fiche_schema import FicheExtraction, vote_extractions


class VLMClient(ABC):
    """Provider-agnostic interface: image bytes in, validated FicheExtraction out.

    Groq backs this for the cloud POC; vLLM/Qwen2.5-VL (self-hosted, on-prem)
    implements the same interface for production — swapping backends is a
    config change (VLM_BACKEND), not a code change.
    """

    @abstractmethod
    def extract(
        self, image_bytes: bytes, *, mime_type: str = "image/png", temperature: float = 0.0
    ) -> FicheExtraction: ...

    def extract_voted(
        self,
        image_bytes: bytes,
        *,
        mime_type: str = "image/png",
        passes: int = 3,
        temperature: float = 0.4,
    ) -> FicheExtraction:
        """Run `extract` `passes` times and majority-vote per cell
        (self-consistency). Cancels random per-run VLM misreads and turns
        inter-run agreement into a calibrated confidence (see fiche_schema.voting).
        Passes run at a non-zero temperature so they actually vary; passes<=1
        falls back to a single deterministic pass."""
        if passes <= 1:
            return self.extract(image_bytes, mime_type=mime_type)
        runs = [
            self.extract(image_bytes, mime_type=mime_type, temperature=temperature)
            for _ in range(passes)
        ]
        return vote_extractions(runs)

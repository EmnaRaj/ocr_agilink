from abc import ABC, abstractmethod

from fiche_schema import FicheExtraction


class VLMClient(ABC):
    """Provider-agnostic interface: image bytes in, validated FicheExtraction out.

    Groq backs this for the cloud POC; vLLM/Qwen2.5-VL (self-hosted, on-prem)
    implements the same interface for production — swapping backends is a
    config change (VLM_BACKEND), not a code change.
    """

    @abstractmethod
    def extract(self, image_bytes: bytes, *, mime_type: str = "image/png") -> FicheExtraction: ...

# VLM extraction clients (Groq now, vLLM/Qwen2.5-VL on-prem later) behind a
# shared interface (see base.py), plus docTR for printed fields in Phase 2.
from .base import VLMClient
from .errors import VLMExtractionError

__all__ = ["VLMClient", "VLMExtractionError"]

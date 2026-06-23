import base64
import os
import time

from .celery_app import celery_app
from .extract import VLMClient
from .extract.groq_client import GroqClient


@celery_app.task(name="worker.ping")
def ping() -> str:
    """Phase 0 smoke-test task — confirms the Celery/Redis wiring works."""
    return "pong"


_vlm_client: VLMClient | None = None


def _get_vlm_client() -> VLMClient:
    global _vlm_client
    if _vlm_client is None:
        backend = os.environ.get("VLM_BACKEND", "groq")
        if backend == "groq":
            _vlm_client = GroqClient(
                api_key=os.environ["GROQ_API_KEY"],
                model=os.environ.get("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"),
            )
        elif backend == "vllm":
            # On-prem production: self-hosted Qwen2.5-VL via vLLM. Imported
            # lazily so a Groq-only deploy doesn't pay for the openai import.
            from .extract.vllm_client import VllmClient

            _vlm_client = VllmClient(
                base_url=os.environ.get("VLLM_BASE_URL", "http://vllm:8000/v1"),
                model=os.environ.get("VLLM_MODEL", "Qwen/Qwen2.5-VL-7B-Instruct"),
                api_key=os.environ.get("VLLM_API_KEY", "EMPTY"),
            )
        else:
            raise ValueError(f"Unknown VLM_BACKEND={backend!r} (expected 'groq' or 'vllm')")
    return _vlm_client


@celery_app.task(name="worker.extract_fiche")
def extract_fiche(image_b64: str, mime_type: str = "image/png") -> dict:
    image_bytes = base64.b64decode(image_b64)
    client = _get_vlm_client()

    start = time.monotonic()
    extraction = client.extract(image_bytes, mime_type=mime_type)
    extraction.meta.processing_ms = int((time.monotonic() - start) * 1000)

    return extraction.model_dump(mode="json")

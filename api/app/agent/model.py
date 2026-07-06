"""Build the chat model from settings — the provider-agnostic seam.

Any OpenAI-compatible endpoint works (OpenRouter / Groq / self-hosted vLLM):
only base_url + api_key + model name change, never the code. CHAT_* config is
independent of the VLM; it falls back to the VLLM_* connection only when CHAT_*
is unset (back-compat).
"""

from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from ..config import settings

# The OpenAI client retries transient failures (429 / 5xx / connection) with
# exponential backoff before the stream starts. Terminal errors (e.g. 402 out of
# credits, 4xx) are NOT retried — they degrade straight to the friendly message.
_MAX_RETRIES = 3


def build_chat_model() -> OpenAIChatModel:
    base_url = settings.chat_base_url or settings.vllm_base_url
    api_key = settings.chat_api_key or settings.vllm_api_key or "EMPTY"
    client = AsyncOpenAI(base_url=base_url, api_key=api_key, max_retries=_MAX_RETRIES)
    return OpenAIChatModel(settings.chat_model, provider=OpenAIProvider(openai_client=client))

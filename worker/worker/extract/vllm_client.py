from openai import OpenAI, OpenAIError

from .errors import VLMExtractionError
from .regional import RegionalVLMClient, _parse_json_response


class VllmClient(RegionalVLMClient):
    """Production backend — talks to a self-hosted vLLM server serving an
    open-source Qwen2.5-VL model over its OpenAI-compatible API.

    Nothing leaves the premises: `base_url` points at the on-prem vLLM
    container (see the `vllm` service in docker-compose.yml). Region
    orchestration lives in RegionalVLMClient; this class only knows how to make
    one vLLM chat-completion call. vLLM is API-compatible with OpenAI, so the
    request shape is identical to GroqClient's apart from `max_tokens`.
    """

    def __init__(self, base_url: str, model: str, api_key: str = "EMPTY") -> None:
        # vLLM ignores the key by default but the OpenAI client requires a
        # non-empty string; set VLLM_API_KEY if the server was started with one.
        self._client = OpenAI(base_url=base_url, api_key=api_key or "EMPTY")
        self._model = model

    def _complete(self, data_uri: str, prompt: str, temperature: float = 0.0) -> dict:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                temperature=temperature,
                max_tokens=4000,
                # vLLM enforces this via guided decoding (xgrammar/outlines), so
                # the model can't drift off the JSON shape.
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_uri}},
                        ],
                    }
                ],
            )
        except OpenAIError as exc:
            raise VLMExtractionError(f"vLLM API error: {exc}") from exc

        choice = response.choices[0]
        return _parse_json_response(choice.message.content, choice.finish_reason, backend="vLLM")

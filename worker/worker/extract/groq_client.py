from groq import Groq, GroqError

from .errors import VLMExtractionError
from .regional import RegionalVLMClient, _parse_json_response


class GroqClient(RegionalVLMClient):
    """POC backend — sends the scan to Groq's hosted API. Data leaves the
    premises; production must use VLM_BACKEND=vllm (self-hosted Qwen2.5-VL).

    Region orchestration lives in RegionalVLMClient; this class only knows how
    to make one Groq chat-completion call.
    """

    def __init__(self, api_key: str, model: str) -> None:
        self._client = Groq(api_key=api_key)
        self._model = model

    def _complete(self, data_uri: str, prompt: str, temperature: float = 0.0) -> dict:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                temperature=temperature,
                max_completion_tokens=4000,
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
        except GroqError as exc:
            raise VLMExtractionError(f"Groq API error: {exc}") from exc

        choice = response.choices[0]
        return _parse_json_response(choice.message.content, choice.finish_reason, backend="Groq")

import logging
from collections.abc import Generator

from openai import OpenAI

from backend.domain.config import require_generation_settings

logger = logging.getLogger(__name__)
_client: OpenAI | None = None
_client_api_key: str | None = None
_client_base_url: str | None = None


def _get_client() -> OpenAI:
    global _client, _client_api_key, _client_base_url
    gs = require_generation_settings()
    if (
        _client is not None
        and _client_api_key == gs.deepseek_api_key
        and _client_base_url == gs.deepseek_base_url
    ):
        return _client
    _client = OpenAI(
        api_key=gs.deepseek_api_key,
        base_url=gs.deepseek_base_url,
    )
    _client_api_key = gs.deepseek_api_key
    _client_base_url = gs.deepseek_base_url
    logger.info(
        "Created OpenAI client base_url=%s model=%s",
        gs.deepseek_base_url, gs.deepseek_model,
    )
    return _client


def complete_text(prompt: str) -> str:
    client = _get_client()
    generation_settings = require_generation_settings()
    response = client.chat.completions.create(
        model=generation_settings.deepseek_model,
        messages=[{"role": "user", "content": prompt}],
        stream=False,
        temperature=0,
    )
    if not response.choices:
        raise RuntimeError("LLM response contained no choices")

    content = response.choices[0].message.content
    if content is None:
        raise RuntimeError("LLM response content was empty")
    if isinstance(content, str):
        return content
    return str(content)


def stream_completion_tokens(prompt: str) -> Generator[str, None, None]:
    client = _get_client()
    generation_settings = require_generation_settings()
    response = client.chat.completions.create(
        model=generation_settings.deepseek_model,
        messages=[{"role": "user", "content": prompt}],
        stream=True,
    )
    for chunk in response:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta

"""Thin wrapper around the local Ollama server.

Two helpers only. Everything the LLM returns is validated by the caller:
we never trust a 7B model blindly."""
import json
import logging

import httpx
import ollama

import config
from agent import settings

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Raised when the local model is unreachable or returns garbage."""


def _client() -> ollama.Client:
    return ollama.Client(host=settings.OLLAMA_HOST, timeout=settings.LLM_TIMEOUT_S)


def _chat(system: str, user: str, **kwargs) -> str:
    try:
        response = _client().chat(
            model=config.OLLAMA_MODEL,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            keep_alive=settings.OLLAMA_KEEP_ALIVE,
            **kwargs,
        )
        return response["message"]["content"]
    except (ollama.ResponseError, httpx.HTTPError, ConnectionError) as exc:
        raise LLMError(
            f"Local LLM unavailable ({exc}). Is Ollama running and is '{config.OLLAMA_MODEL}' pulled?"
        ) from exc


def chat_json(system: str, user: str, schema: dict, max_tokens: int = 120) -> dict:
    """Ask for JSON that follows `schema` (Ollama constrains the output)."""
    text = _chat(system, user, format=schema, options={"temperature": 0, "num_predict": max_tokens})
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError("The model did not return valid JSON.") from exc


def chat_text(system: str, user: str, max_tokens: int = 130) -> str:
    return _chat(system, user, options={"temperature": 0.2, "num_predict": max_tokens}).strip()

"""LLM engine abstraction for the rewrite step.

Engines are user-managed presets pointing at any OpenAI-compatible chat endpoint
(OpenAI, vLLM, llama-swap, Ollama /v1, LM Studio, Groq, OpenRouter, …). Provides
reachability status (online/offline) and a chat-completion call. Uses only the
standard library so the daemon needs no extra deps.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from .stt import reachable


@dataclass
class LLMEngine:
    name: str
    url: str = "https://api.openai.com/v1"   # base URL (incl. /v1)
    model: str = "gpt-4o-mini"
    api_key_env: str = "OPENAI_API_KEY"
    temperature: float = 0.3

    @property
    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env) if self.api_key_env else None


class LLMError(RuntimeError):
    pass


def status(engine: LLMEngine, timeout: float = 2.0) -> bool:
    """Reachable if the endpoint host:port accepts a TCP connection."""
    return reachable(engine.url, timeout)


def chat(
    engine: LLMEngine,
    system_prompt: str,
    user_text: str,
    *,
    model: str | None = None,
    temperature: float | None = None,
    timeout: int = 45,
) -> str:
    api_key = engine.api_key
    payload = json.dumps(
        {
            "model": model or engine.model,
            "temperature": engine.temperature if temperature is None else temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
        }
    ).encode("utf-8")

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(
        engine.url.rstrip("/") + "/chat/completions", data=payload, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise LLMError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise LLMError(f"Connection failed: {exc.reason}") from exc

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"Unexpected response: {str(body)[:300]}") from exc

    content = (content or "").strip()
    if not content:
        raise LLMError("Empty response from model.")
    return content

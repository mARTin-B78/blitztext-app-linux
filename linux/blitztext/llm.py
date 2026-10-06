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
from typing import Callable

from .stt import reachable


@dataclass
class LLMEngine:
    name: str
    url: str = "https://api.openai.com/v1"   # base URL (incl. /v1)
    model: str = "gpt-4o-mini"
    api_key_env: str = "OPENAI_API_KEY"
    temperature: float = 0.3
    type: str = "cloud"                       # "local" | "cloud" (label/category)

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
    on_token: Callable[[str], None] | None = None,
    abort_event=None,
) -> str:
    """Run a chat completion and return the full text.

    When ``on_token`` is given, the request is streamed and each content delta is
    handed to the callback as it arrives (so a UI can show the model writing in
    real time). The callback is best-effort — it never affects the return value,
    which is always the complete, stripped response.
    """
    stream = on_token is not None
    api_key = engine.api_key
    body_obj = {
        "model": model or engine.model,
        "temperature": engine.temperature if temperature is None else temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
    }
    if stream:
        body_obj["stream"] = True
    payload = json.dumps(body_obj).encode("utf-8")

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(
        engine.url.rstrip("/") + "/chat/completions", data=payload, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if stream:
                content = _read_stream(resp, on_token, abort_event)
            else:
                body = json.loads(resp.read().decode("utf-8"))
                content = body["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise LLMError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise LLMError(f"Connection failed: {exc.reason}") from exc
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"Unexpected response: {exc}") from exc
    except (TimeoutError, OSError) as exc:
        # socket.timeout (subclass of OSError / TimeoutError) fires when the server
        # stops sending data mid-stream. Not wrapped in URLError — must be caught
        # separately or it would propagate uncaught and kill the background thread.
        raise LLMError(f"Request timed out or connection lost: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise LLMError(f"Unexpected error: {exc}") from exc

    content = (content or "").strip()
    if not content:
        raise LLMError("Empty response from model.")
    return content


def _read_stream(resp, on_token: Callable[[str], None], abort_event=None) -> str:
    """Parse an OpenAI-style SSE stream, returning the accumulated content and
    feeding each delta to ``on_token``. Tolerant of keep-alive blanks and the
    trailing ``[DONE]`` sentinel."""
    parts: list[str] = []
    for raw in resp:
        if abort_event and abort_event.is_set():
            break
        line = raw.decode("utf-8", "replace").strip()
        if not line or not line.startswith("data:"):
            continue
        data = line[len("data:"):].strip()
        if data == "[DONE]":
            break
        try:
            obj = json.loads(data)
            delta = obj["choices"][0]["delta"].get("content")
        except (ValueError, KeyError, IndexError, TypeError):
            continue
        if delta:
            parts.append(delta)
            try:
                on_token(delta)
            except Exception:  # noqa: BLE001 - UI hiccups must not break delivery
                pass
    return "".join(parts)

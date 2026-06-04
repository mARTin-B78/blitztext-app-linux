"""Optional LLM rewrite via an OpenAI-compatible chat endpoint.

Uses only the standard library (urllib) so the daemon needs no extra deps for
the rewrite step. Works against OpenAI or any local server that implements the
/chat/completions API (e.g. vLLM, llama-swap).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request


class RewriteError(RuntimeError):
    pass


def rewrite(
    text: str,
    system_prompt: str,
    *,
    base_url: str,
    api_key: str | None,
    model: str,
    temperature: float = 0.3,
    timeout: int = 45,
) -> str:
    if not api_key:
        raise RewriteError(
            "No API key for rewrite. Set the env var named by rewrite.api_key_env, "
            "or use a local endpoint that ignores auth."
        )

    payload = json.dumps(
        {
            "model": model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RewriteError(f"HTTP {exc.code}: {detail[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RewriteError(f"Connection failed: {exc.reason}") from exc

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RewriteError(f"Unexpected response: {str(body)[:300]}") from exc

    content = (content or "").strip()
    if not content:
        raise RewriteError("Empty response from model.")
    return content

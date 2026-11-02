"""Shared OpenAI-compatible TTS connection settings."""

import os
import re
import json
import urllib.request
from urllib.parse import urlsplit


class _SameOriginRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        def origin(url):
            parsed = urlsplit(url)
            port = parsed.port
            if port is None:
                port = 443 if parsed.scheme == "https" else 80
            return parsed.scheme.lower(), parsed.hostname, port

        if origin(req.full_url) != origin(newurl):
            raise urllib.error.URLError("TTS redirect to another origin refused.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def urlopen(request, *, timeout):
    """Keep credentials and speech text on the configured origin."""
    return urllib.request.build_opener(_SameOriginRedirectHandler()).open(request, timeout=timeout)


# shortcut: keys live only in this process; use a system keyring if persistence is needed.
_session_keys: dict[str, str] = {}


def set_session_key(url: str, key: str) -> None:
    if not url.strip():
        return
    endpoint = base_url(url)
    if key:
        _session_keys[endpoint] = key
    else:
        _session_keys.pop(endpoint, None)


def session_key(url: str) -> str:
    return _session_keys.get(base_url(url), "") if url.strip() else ""


def validate_env_name(name: str) -> str:
    if name and not re.fullmatch(r"[A-Za-z_]\w*", name, re.ASCII):
        raise RuntimeError("API Key Env must contain an environment variable name, not the API key.")
    return name


def clean_env_name(name: str) -> str:
    """Valid env var name unchanged, anything else (e.g. a pasted key) -> "" (never echoed)."""
    return name if name and re.fullmatch(r"[A-Za-z_]\w*", name, re.ASCII) else ""


def base_url(url: str) -> str:
    base = (url or "").strip().rstrip("/")
    for suffix in ("/audio/speech", "/audio/voices", "/audio/models", "/voices", "/models"):
        if base.endswith(suffix):
            base = base[:-len(suffix)]
            break
    if not base:
        raise RuntimeError("No TTS URL configured.")
    return base if base.endswith("/v1") else base + "/v1"


def auth_headers(api_key_env: str, url: str = "") -> dict[str, str]:
    key = session_key(url)
    api_key_env = clean_env_name(api_key_env)  # an invalid name (pasted key) is ignored
    if not key and not api_key_env:
        return {}
    key = key or os.environ.get(api_key_env)
    if not key:
        raise RuntimeError("The API Key Env variable is not set. Set it in the app's launch environment and restart Blitztext.")
    if any(ord(char) < 33 or ord(char) > 126 for char in key):
        raise RuntimeError("The API key contains invalid characters. Check the API key field or launch environment.")
    return {"Authorization": f"Bearer {key}"}


def list_models(url: str, api_key_env: str = "", timeout: float = 5.0) -> list[str]:
    request = urllib.request.Request(base_url(url) + "/models", headers=auth_headers(api_key_env, url))
    try:
        with urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read())
        return [item["id"] for item in data.get("data", [])
                if isinstance(item, dict) and isinstance(item.get("id"), str)]
    except (OSError, ValueError, AttributeError, TypeError):
        return []

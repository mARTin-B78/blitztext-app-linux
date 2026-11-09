"""Shared OpenAI-compatible TTS connection settings."""

import logging
import os
import re
import json
import tempfile
from pathlib import Path
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


# API keys per endpoint URL (shared by STT, TTS and LLM). Kept in memory and persisted to
# $XDG_CONFIG_HOME/blitztext/keys.json (mode 0600, atomic write). ponytail: plaintext file, no
# keyring (not installed); use the `keyring` package if it becomes a dependency.
_session_keys: dict[str, str] = {}
_log = logging.getLogger(__name__)


def _keys_path() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "blitztext" / "keys.json"


def _load_stored() -> dict[str, str]:
    path = _keys_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError, AttributeError):
        _log.warning("API key store %s is unreadable or corrupt; ignoring it.", path)
        return {}


def _save_stored(keys: dict[str, str]) -> None:
    path = _keys_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".keys-")  # mkstemp creates 0600
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(keys, fh)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def set_session_key(url: str, key: str) -> bool:
    """Set (or, with an empty key, remove) the key for a URL; returns False if it could not be
    saved to disk (the key then only lives in memory)."""
    if not url.strip():
        return True
    endpoint = base_url(url)
    if key:
        _session_keys[endpoint] = key
    else:
        _session_keys[endpoint] = ""  # explicit removal, hides any stored copy
    stored = _load_stored()
    if key:
        stored[endpoint] = key
    else:
        stored.pop(endpoint, None)
    try:
        _save_stored(stored)
        return True
    except OSError:
        _log.warning("Could not write the API key store %s; key kept in memory only.", _keys_path())
        return False


def session_key(url: str) -> str:
    if not url.strip():
        return ""
    endpoint = base_url(url)
    if endpoint not in _session_keys:
        _session_keys[endpoint] = _load_stored().get(endpoint, "")
    return _session_keys[endpoint]


def adopt_literal_key(url: str, env_value: str) -> str:
    """An 'API key env' field that holds a literal key (not a valid env var name) is moved into
    the key store; returns the value the field should keep ("" if it was a key)."""
    if not env_value or clean_env_name(env_value) or not url.strip():
        return env_value
    if not session_key(url):
        set_session_key(url, env_value)
    return ""


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
        raise RuntimeError("No API key: the API Key Env variable is not set and no API key is saved for this URL. Enter it in Settings or set the variable in the launch environment.")
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

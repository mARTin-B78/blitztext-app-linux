"""Speech-to-text engine abstraction: local faster-whisper or remote endpoints.

Engines are user-managed presets. Each is either the in-process local
faster-whisper model, or a remote OpenAI-compatible server exposing
`/audio/transcriptions` (faster-whisper-server, Groq, WhisperX, whisper.cpp's
OpenAI shim, NVIDIA NIMs, …). Provides reachability checks (online/offline) and
a benchmark helper (transcript + elapsed seconds).
"""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


@dataclass
class STTEngine:
    name: str
    type: str = "local"        # "local" | "openai" | "riva_realtime"
    url: str = ""              # base URL incl. /v1 for remote, e.g. http://localhost:8010/v1
    model: str = ""            # remote model id, or local whisper size override
    api_key_env: str = ""      # env var holding a bearer key (optional)

    @property
    def is_local(self) -> bool:
        return self.type == "local"

    @property
    def is_streaming(self) -> bool:
        return self.type == "riva_realtime"


class STTError(RuntimeError):
    pass


# --- reachability ------------------------------------------------------------
def reachable(url: str, timeout: float = 2.0) -> bool:
    """True if a TCP connection to the URL's host:port succeeds."""
    host, port = _host_port(url)
    if not host:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def status(engine: STTEngine, timeout: float = 2.0) -> bool:
    """True if the engine is usable now (local always; remote = TCP reachable)."""
    if engine.is_local:
        return True
    return reachable(engine.url, timeout)


@dataclass
class ModelMeta:
    """Model id plus optional metadata (languages, etc.) from the server."""
    id: str
    languages: list[str] = field(default_factory=list)


def fmt_languages(langs: list[str]) -> str:
    """Compact display string for a language list, e.g. 'en, de, fr +45'."""
    if not langs:
        return "—"
    if len(langs) >= 50:
        return f"multilingual ({len(langs)})"
    if len(langs) > 5:
        return f"{', '.join(langs[:5])} +{len(langs) - 5}"
    return ", ".join(langs)


def list_models(base_url: str, api_key_env: str = "", timeout: float = 5.0) -> list[str]:
    """Fetch model ids from an OpenAI-compatible, Ollama-style, or Riva/NIM /models endpoint."""
    return [m.id for m in list_models_meta(base_url, api_key_env, timeout)]


def list_models_meta(base_url: str, api_key_env: str = "", timeout: float = 5.0) -> list[ModelMeta]:
    """Like list_models() but returns ModelMeta with language info when available."""
    import os

    if not base_url:
        return []
    base = base_url.rstrip("/")
    headers: dict[str, str] = {}
    key = os.environ.get(api_key_env) if api_key_env else None
    if key:
        headers["Authorization"] = f"Bearer {key}"

    def _get(url: str) -> dict | None:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, json.JSONDecodeError, OSError):
            return None

    # 1. Standard OpenAI /models — faster-whisper-server also returns "language"
    data = _get(base + "/models")
    if isinstance(data, dict):
        items = data.get("data")
        if isinstance(items, list):
            result = [ModelMeta(id=m["id"], languages=m.get("language") or [])
                      for m in items if isinstance(m, dict) and m.get("id")]
            if result:
                return result
        items = data.get("models")
        if isinstance(items, list):  # Ollama shape
            return [ModelMeta(id=m.get("name") or m.get("model", ""))
                    for m in items if m.get("name") or m.get("model")]

    # 2. NVIDIA Riva / NIM
    data = _get(base + "/metadata")
    if isinstance(data, dict):
        for info in data.get("modelInfo") or []:
            name = info.get("shortName") or info.get("modelUrl") or ""
            if name:
                return [ModelMeta(id=name.split(":")[0])]

    return []


def detect_remote_device(base_url: str, timeout: float = 3.0) -> str:
    """Best-effort GPU/CPU detection for a remote STT server.

    Tries faster-whisper-server's /info endpoint (returns {"device":"cuda",...}),
    then NVIDIA NIM /metadata (GPU-only service). Falls back to "remote".
    """
    if not base_url:
        return "remote"
    base = base_url.rstrip("/")
    try:
        req = urllib.request.Request(base + "/info")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if isinstance(data, dict):
            dev = str(data.get("device") or data.get("compute_type") or "")
            if "cuda" in dev.lower():
                return "CUDA"
            if dev:
                return dev.upper()[:16]
    except Exception:
        pass
    try:
        req = urllib.request.Request(base + "/metadata")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if isinstance(data, dict) and data.get("modelInfo"):
            return "CUDA"  # NVIDIA NIM is always GPU
    except Exception:
        pass
    return "remote"


def _host_port(url: str) -> tuple[str | None, int]:
    try:
        u = urlparse(url if "://" in url else "http://" + url)
        port = u.port or (443 if u.scheme == "https" else 80)
        return u.hostname, port
    except ValueError:
        return None, 0


# --- transcription -----------------------------------------------------------
def transcribe(
    engine: STTEngine,
    audio_path: Path,
    *,
    language: str = "",
    hotwords: str = "",
    local_transcriber=None,
    timeout: int = 60,
) -> str:
    if engine.is_local:
        if local_transcriber is None:
            raise STTError("Local engine selected but the model isn't loaded.")
        return local_transcriber.transcribe(audio_path, language=language, hotwords=hotwords)
    if engine.is_streaming:
        raise STTError("Streaming STT engines are live-only. Use a workflow with mode = \"stream\".")
    return _transcribe_remote(engine, audio_path, language=language, prompt=hotwords, timeout=timeout)


def _transcribe_remote(engine: STTEngine, audio_path: Path, *, language: str, prompt: str, timeout: int) -> str:
    import os

    base = engine.url.rstrip("/")
    endpoint = base + "/audio/transcriptions"
    fields: dict[str, str] = {"response_format": "json"}
    if engine.model:
        fields["model"] = engine.model
    if language:
        fields["language"] = language
    if prompt:
        fields["prompt"] = prompt

    headers = {}
    key = os.environ.get(engine.api_key_env) if engine.api_key_env else None
    if key:
        headers["Authorization"] = f"Bearer {key}"

    body, content_type = _multipart(fields, audio_path)
    headers["Content-Type"] = content_type
    req = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise STTError(f"HTTP {exc.code} from {endpoint}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise STTError(f"Cannot reach {endpoint}: {exc.reason}") from exc

    try:
        return (json.loads(raw).get("text") or "").strip()
    except json.JSONDecodeError:
        return raw.strip()  # some servers return plain text


def _multipart(fields: dict, audio_path: Path) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    nl = b"\r\n"
    out = bytearray()
    for k, v in fields.items():
        out += b"--" + boundary.encode() + nl
        out += f'Content-Disposition: form-data; name="{k}"'.encode() + nl + nl
        out += str(v).encode() + nl
    out += b"--" + boundary.encode() + nl
    out += f'Content-Disposition: form-data; name="file"; filename="{audio_path.name}"'.encode() + nl
    out += b"Content-Type: audio/wav" + nl + nl
    out += audio_path.read_bytes() + nl
    out += b"--" + boundary.encode() + b"--" + nl
    return bytes(out), f"multipart/form-data; boundary={boundary}"


# --- benchmark ---------------------------------------------------------------
@dataclass
class BenchResult:
    engine: str
    ok: bool
    text: str = ""
    seconds: float = 0.0
    error: str = ""


def benchmark(engine: STTEngine, audio_path: Path, *, language: str = "", local_transcriber=None) -> BenchResult:
    t0 = time.perf_counter()
    try:
        text = transcribe(engine, audio_path, language=language, local_transcriber=local_transcriber)
        return BenchResult(engine.name, True, text, time.perf_counter() - t0)
    except Exception as exc:  # noqa: BLE001 - report any failure to the UI
        return BenchResult(engine.name, False, "", time.perf_counter() - t0, str(exc))

"""Realtime STT client for Riva/NIM WebSocket transcription.

The NIM HTTP docs expose session creation, but the live audio path is a
WebSocket at /v1/realtime?intent=transcription. Audio is sent as base64 PCM16
chunks and transcript events arrive as interim deltas and completed segments.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import queue
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from copy import deepcopy
from dataclasses import dataclass
from typing import Callable

from .stt import STTEngine

TextCallback = Callable[[str, bool], None]
StatusCallback = Callable[[str], None]
ErrorCallback = Callable[[Exception], None]


class StreamingSTTError(RuntimeError):
    pass


@dataclass
class RealtimeURLs:
    session_url: str
    websocket_url: str


def realtime_urls(base_url: str) -> RealtimeURLs:
    """Build the HTTP session URL and WebSocket URL from a user base URL."""
    raw = (base_url or "").strip().rstrip("/")
    if not raw:
        raise StreamingSTTError("Missing realtime STT URL.")
    if "://" not in raw:
        raw = "http://" + raw

    parsed = urllib.parse.urlparse(raw)
    path = parsed.path.rstrip("/")
    if path.endswith("/realtime"):
        realtime_path = path
    elif path.endswith("/v1"):
        realtime_path = path + "/realtime"
    else:
        realtime_path = path + "/v1/realtime"

    http_scheme = "https" if parsed.scheme == "https" else "http"
    ws_scheme = "wss" if http_scheme == "https" else "ws"
    netloc = parsed.netloc
    session = urllib.parse.urlunparse((http_scheme, netloc, realtime_path + "/transcription_sessions", "", "", ""))
    ws = urllib.parse.urlunparse((ws_scheme, netloc, realtime_path, "", "intent=transcription", ""))
    return RealtimeURLs(session, ws)


class RivaRealtimeStreamer:
    """Owns one live microphone -> Riva WebSocket transcription session."""

    def __init__(
        self,
        engine: STTEngine,
        *,
        device: str = "",
        language: str = "",
        sample_rate: int = 16000,
        chunk_frames: int = 1600,
        on_text: TextCallback | None = None,
        on_status: StatusCallback | None = None,
        on_error: ErrorCallback | None = None,
    ):
        self.engine = engine
        self.device = device
        self.language = language.strip()
        self.sample_rate = sample_rate
        self.chunk_frames = chunk_frames
        self.on_text = on_text
        self.on_status = on_status
        self.on_error = on_error
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._error: Exception | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run_thread, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5.0)
        if self._error:
            raise self._error

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def _run_thread(self) -> None:
        try:
            asyncio.run(self._run())
        except Exception as exc:  # noqa: BLE001 - surfaced to daemon/UI
            self._error = exc
            self._ready.set()
            if self.on_error:
                self.on_error(exc)

    async def _run(self) -> None:
        try:
            import sounddevice as sd
            import websockets
        except ModuleNotFoundError as exc:
            raise StreamingSTTError(
                "Realtime streaming needs the Python packages 'websockets' and 'sounddevice'."
            ) from exc

        urls = realtime_urls(self.engine.url)
        session = self._create_session(urls.session_url)
        headers = self._auth_headers()
        websocket = await self._connect_websocket(websockets, urls.websocket_url, headers)
        audio_q: queue.Queue[bytes] = queue.Queue(maxsize=60)

        def audio_cb(indata, _frames, _time_info, status):
            if status and self.on_status:
                self.on_status(str(status))
            try:
                audio_q.put_nowait(bytes(indata))
            except queue.Full:
                pass

        try:
            await self._initialize_websocket(websocket, session)
            self._ready.set()
            if self.on_status:
                self.on_status("Streaming")

            with sd.RawInputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="int16",
                blocksize=self.chunk_frames,
                device=self._resolve_device(sd),
                callback=audio_cb,
            ):
                send_task = asyncio.create_task(self._send_audio(websocket, audio_q))
                recv_task = asyncio.create_task(self._receive_text(websocket))
                await send_task
                try:
                    await asyncio.wait_for(recv_task, timeout=8.0)
                except asyncio.TimeoutError:
                    recv_task.cancel()
        finally:
            await websocket.close()

    def _auth_headers(self) -> dict[str, str]:
        if not self.engine.api_key_env:
            return {}
        key = os.environ.get(self.engine.api_key_env)
        return {"Authorization": f"Bearer {key}"} if key else {}

    def _create_session(self, url: str) -> dict:
        body = b"{}"
        headers = {"Content-Type": "application/json", **self._auth_headers()}
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise StreamingSTTError(f"HTTP {exc.code} from {url}: {detail}") from exc
        except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
            raise StreamingSTTError(f"Cannot initialize realtime STT session at {url}: {exc}") from exc

    async def _connect_websocket(self, websockets, url: str, headers: dict[str, str]):
        try:
            return await websockets.connect(url, additional_headers=headers or None)
        except TypeError:
            return await websockets.connect(url, extra_headers=headers or None)

    async def _initialize_websocket(self, websocket, session: dict) -> None:
        first = json.loads(await asyncio.wait_for(websocket.recv(), timeout=5.0))
        if first.get("type") != "conversation.created":
            raise StreamingSTTError(f"Unexpected realtime greeting: {first}")

        updated = deepcopy(session)
        updated["input_audio_format"] = "pcm16"
        updated.setdefault("input_audio_params", {})
        updated["input_audio_params"]["sample_rate_hz"] = self.sample_rate
        updated["input_audio_params"]["num_channels"] = 1
        updated.setdefault("recognition_config", {})
        updated["recognition_config"]["max_alternatives"] = 1
        # Language: an explicit hint wins. Otherwise, if the server's session
        # default is a comma-list of codes (multi-language models report e.g.
        # "bn-IN,en-US,hi-IN,ta-IN,indic"), Riva's streaming backend rejects the
        # whole list and needs exactly one code — collapse it to a single code
        # (prefer en-US) so streaming works out of the box.
        lang = self.language
        if not lang:
            existing = (updated.get("input_audio_transcription") or {}).get("language", "")
            if "," in existing:
                codes = [c.strip() for c in existing.split(",") if c.strip()]
                lang = "en-US" if "en-US" in codes else (codes[0] if codes else "")
        if lang:
            updated.setdefault("input_audio_transcription", {})
            updated["input_audio_transcription"]["language"] = lang
        if self.engine.model:
            updated.setdefault("input_audio_transcription", {})
            updated["input_audio_transcription"]["model"] = self.engine.model

        await websocket.send(json.dumps({"type": "transcription_session.update", "session": updated}))
        response = json.loads(await asyncio.wait_for(websocket.recv(), timeout=5.0))
        if response.get("type") != "transcription_session.updated":
            raise StreamingSTTError(f"Realtime session update failed: {response}")

    async def _send_audio(self, websocket, audio_q: queue.Queue[bytes]) -> None:
        while not self._stop.is_set():
            try:
                chunk = await asyncio.to_thread(audio_q.get, True, 0.2)
            except queue.Empty:
                continue
            await self._send_chunk(websocket, chunk)

        drain_until = time.monotonic() + 0.3
        while time.monotonic() < drain_until:
            try:
                chunk = audio_q.get_nowait()
            except queue.Empty:
                break
            await self._send_chunk(websocket, chunk)
        await websocket.send(json.dumps({"type": "input_audio_buffer.done"}))

    async def _send_chunk(self, websocket, chunk: bytes) -> None:
        audio = base64.b64encode(chunk).decode("ascii")
        await websocket.send(json.dumps({"type": "input_audio_buffer.append", "audio": audio}))
        await websocket.send(json.dumps({"type": "input_audio_buffer.commit"}))

    async def _receive_text(self, websocket) -> None:
        while True:
            try:
                raw = await asyncio.wait_for(websocket.recv(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            event = json.loads(raw)
            kind = event.get("type", "")
            if kind == "conversation.item.input_audio_transcription.delta":
                text = (event.get("delta") or "").strip()
                if text and self.on_text:
                    self.on_text(text, False)
            elif kind == "conversation.item.input_audio_transcription.completed":
                text = (event.get("transcript") or "").strip()
                if text and self.on_text:
                    self.on_text(text, True)
                if event.get("is_last_result"):
                    return
            elif kind == "conversation.item.input_audio_transcription.failed":
                raise StreamingSTTError(event.get("error", {}).get("message", "Transcription failed."))
            elif kind == "error":
                err = event.get("error", {})
                raise StreamingSTTError(err.get("message") or str(err) or "Realtime STT error.")

    def _resolve_device(self, sd):
        if not self.device:
            return None
        try:
            for i, d in enumerate(sd.query_devices()):
                if d["max_input_channels"] > 0 and self.device in d["name"]:
                    return i
        except Exception:  # noqa: BLE001
            pass
        return None

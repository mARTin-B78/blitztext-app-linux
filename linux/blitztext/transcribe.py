"""Local speech-to-text via faster-whisper (CTranslate2).

The model is loaded once and reused. On this arm64 host the CTranslate2 wheel is
CPU-only, so device="auto" attempts CUDA and falls back to CPU automatically.
"""

from __future__ import annotations

import sys
from pathlib import Path


class Transcriber:
    def __init__(
        self,
        model: str = "small",
        device: str = "auto",
        compute_type: str = "auto",
        beam_size: int = 5,
    ):
        self.beam_size = beam_size
        self._model = self._load(model, device, compute_type)

    @staticmethod
    def _resolve_compute_type(device: str, requested: str) -> str:
        if requested != "auto":
            return requested
        return "float16" if device == "cuda" else "int8"

    def _load(self, model: str, device: str, compute_type: str):
        from faster_whisper import WhisperModel

        attempts: list[str]
        if device == "auto":
            attempts = ["cuda", "cpu"]
        else:
            attempts = [device]

        last_err: Exception | None = None
        for dev in attempts:
            try:
                ct = self._resolve_compute_type(dev, compute_type)
                m = WhisperModel(model, device=dev, compute_type=ct)
                print(f"[blitztext] Whisper '{model}' loaded on {dev} ({ct})", file=sys.stderr)
                return m
            except Exception as exc:  # noqa: BLE001 - CUDA libs may be absent
                last_err = exc
                if dev != attempts[-1]:
                    print(f"[blitztext] {dev} unavailable ({exc}); trying next device", file=sys.stderr)
        raise RuntimeError(f"Failed to load Whisper model '{model}': {last_err}")

    def transcribe(self, audio_path: Path, language: str = "", hotwords: str = "") -> str:
        kwargs = dict(language=language or None, beam_size=self.beam_size, vad_filter=True)
        if hotwords:
            # Bias recognition toward the routing keywords so they transcribe
            # reliably. Older faster-whisper builds lack `hotwords`; fall back.
            kwargs["hotwords"] = hotwords
        try:
            segments, _info = self._model.transcribe(str(audio_path), **kwargs)
        except TypeError:
            kwargs.pop("hotwords", None)
            segments, _info = self._model.transcribe(str(audio_path), **kwargs)
        return " ".join(seg.text.strip() for seg in segments).strip()

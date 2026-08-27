"""Live local wakeword confidence testing (no wyoming server round-trip).

Loads a downloaded .onnx model directly via the `openwakeword` Python
package and runs it against live microphone audio, yielding a continuous
confidence score per chunk — something the Wyoming protocol itself doesn't
provide (a wyoming-openwakeword server only ever emits a one-shot
"detection" event, never an ongoing score). Mirrors the live tester at
openwakeword.com/library, which gets the same continuous score by running
the model client-side in the browser instead of round-tripping to a server.

Only works for models that exist as an actual .onnx file in the server's
custom model folder — built-in models baked into the wyoming-openwakeword
docker image itself aren't reachable from the host filesystem.
"""
from __future__ import annotations

from pathlib import Path


def find_model_file(model_dir: str | Path | None, name: str) -> Path | None:
    if not model_dir:
        return None
    p = Path(model_dir) / f"{name}.onnx"
    return p if p.is_file() else None


class LiveModelTester:
    """Runs one openWakeWord .onnx model against live mic audio.

    ``on_score`` is called (~10x/s, from a background thread) with the
    model's raw confidence (0..1) for the latest ~100ms audio chunk.
    ``on_level`` gets the same chunk's plain RMS level, like the app's other
    input-level meters.
    """

    def __init__(self, model_path: str | Path, device: str = ""):
        self.model_path = str(model_path)
        self.device = device
        self._meter = None

    def start(self, on_score, on_level=None) -> bool:
        import numpy as np
        from openwakeword.model import Model

        from .audio import LevelMeter

        model = Model(wakeword_model_paths=[self.model_path])

        def _on_chunk(chunk: bytes) -> None:
            audio = np.frombuffer(chunk, dtype=np.int16)
            try:
                scores = model.predict(audio)
            except Exception:
                return
            if scores:
                on_score(float(next(iter(scores.values()))))

        self._meter = LevelMeter(device=self.device, on_level=on_level, on_chunk=_on_chunk)
        return self._meter.start()

    def stop(self) -> None:
        if self._meter:
            self._meter.stop()
            self._meter = None

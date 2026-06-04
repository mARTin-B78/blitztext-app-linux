"""Hotkey-driven engine: toggle recording per workflow, then transcribe + deliver.

Used by both the headless CLI (`run`) and the tkinter GUI. A status callback
lets the GUI reflect each phase; desktop notifications fire regardless.
"""

from __future__ import annotations

import sys
import threading
from typing import Callable

from .config import Config, Workflow
from .notify import notify
from .paste import active_window_id, deliver
from .recorder import Recording, detect_recorder
from .rewrite import RewriteError, rewrite
from .transcribe import Transcriber

# status_cb(state, workflow_name, message)
#   state in {"loading", "idle", "recording", "busy", "done", "error"}
StatusCallback = Callable[[str, str | None, str], None]


class Daemon:
    def __init__(self, cfg: Config, status_cb: StatusCallback | None = None):
        self.cfg = cfg
        self.status_cb = status_cb
        self._lock = threading.Lock()
        self._recording: Recording | None = None
        self._active_workflow: Workflow | None = None
        self._target_window: str | None = None
        self._busy = False
        self._listener = None

        self.recorder_name = detect_recorder(cfg.recorder)
        self.transcriber: Transcriber | None = None

    # -- feedback -------------------------------------------------------------
    def _notify(self, title: str, body: str = "", urgency: str = "normal") -> None:
        notify(title, body, urgency=urgency, enabled=self.cfg.notify)

    def _emit(self, state: str, workflow: str | None = None, message: str = "") -> None:
        if self.status_cb:
            try:
                self.status_cb(state, workflow, message)
            except Exception:  # noqa: BLE001 - never let UI errors break the engine
                pass

    # -- model load (slow; call off the UI thread) ----------------------------
    def prepare(self) -> None:
        self._emit("loading", None, f"Loading Whisper '{self.cfg.model}'…")
        self._notify("Loading model…", f"Whisper '{self.cfg.model}' ({self.cfg.device})")
        self.transcriber = Transcriber(
            model=self.cfg.model,
            device=self.cfg.device,
            compute_type=self.cfg.compute_type,
            beam_size=self.cfg.beam_size,
        )
        self._emit("idle", None, "Ready")

    @property
    def ready(self) -> bool:
        return self.transcriber is not None

    @property
    def is_recording(self) -> bool:
        return self._recording is not None

    # -- hotkey / button handler ----------------------------------------------
    def toggle(self, workflow: Workflow) -> None:
        """Called on each trigger: start recording, or stop + process."""
        with self._lock:
            if not self.ready:
                self._notify("Please wait", "Model still loading…", "low")
                return
            if self._busy:
                self._notify("Busy", "Still processing the last clip…", "low")
                return

            if self._recording is None:
                self._target_window = active_window_id()
                self._recording = Recording(self.recorder_name)
                self._active_workflow = workflow
                self._emit("recording", workflow.name, "Recording…")
                self._notify(f"● {workflow.name}", "Recording… trigger again to stop.")
                return

            rec, wf, win = self._recording, self._active_workflow, self._target_window
            self._recording = None
            self._active_workflow = None
            self._busy = True

        audio_path = rec.stop()
        threading.Thread(target=self._process, args=(audio_path, wf, win), daemon=True).start()

    # -- worker ---------------------------------------------------------------
    def _process(self, audio_path, workflow: Workflow, window_id) -> None:
        try:
            self._emit("busy", workflow.name, "Transcribing…")
            self._notify(f"⌛ {workflow.name}", "Transcribing…")
            text = self.transcriber.transcribe(audio_path, language=self.cfg.language)

            if not text:
                self._emit("idle", workflow.name, "No speech detected")
                self._notify("Nothing heard", "No speech detected.", "low")
                return

            if workflow.mode == "rewrite" and workflow.prompt:
                self._emit("busy", workflow.name, "Rewriting…")
                self._notify(f"⌛ {workflow.name}", "Rewriting…")
                try:
                    text = rewrite(
                        text,
                        workflow.prompt,
                        base_url=self.cfg.base_url,
                        api_key=self.cfg.api_key,
                        model=workflow.model or self.cfg.rewrite_model,
                        temperature=workflow.temperature if workflow.temperature is not None else self.cfg.temperature,
                        timeout=self.cfg.timeout,
                    )
                except RewriteError as exc:
                    self._emit("error", workflow.name, str(exc))
                    self._notify("Rewrite failed", str(exc), "critical")
                    return

            deliver(
                text,
                mode=self.cfg.output,
                window_id=window_id,
                type_delay_ms=self.cfg.type_delay_ms,
            )
            self._emit("done", workflow.name, text)
            self._notify(f"✓ {workflow.name}", text[:80] + ("…" if len(text) > 80 else ""))
        except Exception as exc:  # noqa: BLE001 - surface any failure
            self._emit("error", workflow.name, str(exc))
            self._notify("Error", str(exc), "critical")
            print(f"[blitztext] error: {exc}", file=sys.stderr)
        finally:
            audio_path.unlink(missing_ok=True)
            with self._lock:
                self._busy = False
            self._emit("idle", None, "Ready")

    # -- hotkeys --------------------------------------------------------------
    def start_hotkeys(self):
        """Register global hotkeys non-blocking; returns the pynput listener."""
        from pynput import keyboard

        mapping = {wf.hotkey: (lambda wf=wf: self.toggle(wf)) for wf in self.cfg.workflows}
        self._listener = keyboard.GlobalHotKeys(mapping)
        self._listener.start()
        return self._listener

    def stop_hotkeys(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    # -- headless run loop ----------------------------------------------------
    def run(self) -> None:
        self.prepare()
        lines = "\n".join(f"  {wf.hotkey}  →  {wf.name}" for wf in self.cfg.workflows)
        print(f"[blitztext] ready. Recorder: {self.recorder_name}. Hotkeys:\n{lines}", file=sys.stderr)
        self._notify("Blitztext ready", "Focus a text field and press a hotkey.")

        from pynput import keyboard

        mapping = {wf.hotkey: (lambda wf=wf: self.toggle(wf)) for wf in self.cfg.workflows}
        with keyboard.GlobalHotKeys(mapping) as listener:
            listener.join()

"""Hotkey-driven engine: toggle recording per workflow, then transcribe + deliver.

Used by the headless CLI (`run`) and the GTK GUI. A status callback lets the UI
reflect each phase; desktop notifications fire regardless. Supports voice-keyword
routing: one hotkey records, then the spoken keyword selects the preset.
"""

from __future__ import annotations

import sys
import threading
from typing import Callable

from . import llm, stt
from .config import Config, Workflow
from .llm import LLMError
from .notify import notify
from .paste import active_window_id, deliver
from .recorder import Recording, detect_recorder
from .routing import route
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
        self._prepared = False
        self._listener = None
        # Synthetic preset used by the voice-routing hotkey.
        self._route_workflow = Workflow(name="Voice", hotkey=cfg.routing_hotkey, mode="route")

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
        engine = self.cfg.active_stt
        if engine.is_local:
            model = engine.model or self.cfg.model
            self._emit("loading", None, f"Loading Whisper '{model}'…")
            self._notify("Loading model…", f"Whisper '{model}' ({self.cfg.device})")
            self.transcriber = Transcriber(
                model=model,
                device=self.cfg.device,
                compute_type=self.cfg.compute_type,
                beam_size=self.cfg.beam_size,
            )
        else:
            # Remote STT engine — no local model to load.
            self.transcriber = None
            self._emit("loading", None, f"Using {engine.name}")
        self._prepared = True
        self._emit("idle", None, "Ready")

    @property
    def ready(self) -> bool:
        return getattr(self, "_prepared", False)

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
        label = workflow.name
        try:
            self._emit("busy", label, "Transcribing…")
            self._notify(f"⌛ {label}", "Transcribing…")
            hotwords = ", ".join(self.cfg.all_keywords) if workflow.mode == "route" else ""
            text = stt.transcribe(
                self.cfg.active_stt,
                audio_path,
                language=self.cfg.language,
                hotwords=hotwords,
                local_transcriber=self.transcriber,
                timeout=self.cfg.timeout,
            )

            if not text:
                self._emit("idle", label, "No speech detected")
                self._notify("Nothing heard", "No speech detected.", "low")
                return

            # Voice routing: pick the preset from a spoken keyword, strip it.
            if workflow.mode == "route":
                res = route(text, self.cfg.workflows, threshold=self.cfg.routing_threshold)
                target = self.cfg.preset_by_name(res.preset_name) or self.cfg.default_preset
                text = res.text
                label = target.name if target else "Transcribe"
                via = f"“{res.keyword}”" if res.keyword else "default"
                self._emit("busy", label, f"→ {label} ({via})")
                self._notify(f"🎙 {label}", f"matched: {via}")
            else:
                target = workflow

            if target and target.mode == "rewrite" and target.prompt:
                if not text:
                    self._emit("idle", label, "Only a keyword heard")
                    self._notify("Nothing to do", "Only the keyword was heard.", "low")
                    return
                self._emit("busy", label, "Rewriting…")
                self._notify(f"⌛ {label}", "Rewriting…")
                try:
                    text = llm.chat(
                        self.cfg.active_llm,
                        target.prompt,
                        text,
                        model=target.model or None,
                        temperature=target.temperature,
                        timeout=self.cfg.timeout,
                    )
                except LLMError as exc:
                    self._emit("error", label, str(exc))
                    self._notify("Rewrite failed", str(exc), "critical")
                    return

            if not text:
                self._emit("idle", label, "Nothing to type")
                return

            deliver(
                text,
                mode=self.cfg.output,
                window_id=window_id,
                type_delay_ms=self.cfg.type_delay_ms,
            )
            self._emit("done", label, text)
            self._notify(f"✓ {label}", text[:80] + ("…" if len(text) > 80 else ""))
        except Exception as exc:  # noqa: BLE001 - surface any failure
            self._emit("error", label, str(exc))
            self._notify("Error", str(exc), "critical")
            print(f"[blitztext] error: {exc}", file=sys.stderr)
        finally:
            audio_path.unlink(missing_ok=True)
            with self._lock:
                self._busy = False
            self._emit("idle", None, "Ready")

    # -- hotkeys --------------------------------------------------------------
    def _build_mapping(self) -> dict:
        """hotkey -> callback, skipping empty hotkeys, plus the routing hotkey."""
        mapping: dict = {}
        for wf in self.cfg.workflows:
            if wf.hotkey:
                mapping[wf.hotkey] = (lambda wf=wf: self.toggle(wf))
        if self.cfg.routing_enabled and self.cfg.routing_hotkey:
            mapping[self.cfg.routing_hotkey] = (lambda: self.toggle(self._route_workflow))
        return mapping

    def start_hotkeys(self):
        """Register global hotkeys non-blocking; returns the pynput listener."""
        from pynput import keyboard

        self._listener = keyboard.GlobalHotKeys(self._build_mapping())
        self._listener.start()
        return self._listener

    def stop_hotkeys(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    # -- headless run loop ----------------------------------------------------
    def run(self) -> None:
        self.prepare()
        lines = [f"  {self.cfg.routing_hotkey}  →  Voice routing (speak a keyword)"] if self.cfg.routing_enabled else []
        lines += [f"  {wf.hotkey}  →  {wf.name}" for wf in self.cfg.workflows if wf.hotkey]
        print(f"[blitztext] ready. Recorder: {self.recorder_name}. Hotkeys:\n" + "\n".join(lines), file=sys.stderr)
        self._notify("Blitztext ready", "Focus a text field and press a hotkey.")

        from pynput import keyboard

        with keyboard.GlobalHotKeys(self._build_mapping()) as listener:
            listener.join()

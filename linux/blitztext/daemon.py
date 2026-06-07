"""Hotkey-driven engine: toggle recording per workflow, then transcribe + deliver.

Used by the headless CLI (`run`) and the GTK GUI. A status callback lets the UI
reflect each phase; desktop notifications fire regardless. Supports voice-keyword
routing: one hotkey records, then the spoken keyword selects the preset.
"""

from __future__ import annotations

import sys
import threading
from typing import Callable

from . import llm, quality, stt
from .config import Config, Workflow
from .llm import LLMError
from .logbuffer import log
from .notify import notify
from .paste import active_window_id, deliver
from .streaming import RivaRealtimeStreamer
from .recorder import Recording, detect_recorder
from .routing import route
from .transcribe import Transcriber

# status_cb(state, workflow_name, message)
#   state in {"loading", "idle", "recording", "streaming", "busy", "done", "error"}
StatusCallback = Callable[[str, str | None, str], None]


class Daemon:
    def __init__(self, cfg: Config, status_cb: StatusCallback | None = None):
        self.cfg = cfg
        self.status_cb = status_cb
        self._lock = threading.Lock()
        self._recording: Recording | None = None
        self._streaming: RivaRealtimeStreamer | None = None
        self._stream_segment_text = ""
        self._active_workflow: Workflow | None = None
        self._target_window: str | None = None
        self._busy = False
        self._prepared = False
        self._listener = None
        # Synthetic preset used by the voice-routing hotkey.
        self._route_workflow = Workflow(name="Voice", hotkey=cfg.routing_hotkey, mode="route")

        self.recorder_name = detect_recorder(cfg.recorder)
        self.transcriber: Transcriber | None = None
        self._wakeword_listener = None
        # When a session is started hands-free by the wakeword, its desktop
        # notifications are suppressed (kept quiet in the background).
        self._session_silent = False

    def _init_wakeword(self):
        if self.cfg.wakeword_enabled:
            from .wakeword import WakewordListener, is_muted
            if is_muted():
                # A stale flag silently disables detection — make it visible so
                # "the wakeword does nothing" has an obvious explanation/fix.
                log("[wakeword] Starting PAUSED — /tmp/wake_muted is present; "
                    "resume via the tray 'Pause wakeword' toggle.")
            self._wakeword_listener = WakewordListener(
                uri=self.cfg.wakeword_uri,
                model=self.cfg.wakeword_model,
                mic=self.cfg.mic,
                on_detect=self._on_wakeword,
            )
            self._wakeword_listener.start()

    def _on_wakeword(self):
        # Hands-free trigger: start a quiet (notification-suppressed) session.
        # We call start_dictation directly rather than toggle() so that a busy
        # or not-yet-ready state is ignored silently instead of popping a
        # "Busy"/"Please wait" notification — repeated false detections while a
        # clip is still transcribing were the source of the away-from-keyboard
        # notification storm.
        self.start_dictation(self._route_workflow, silent=True)

    # -- feedback -------------------------------------------------------------
    def _notify(self, title: str, body: str = "", urgency: str = "normal") -> None:
        notify(title, body, urgency=urgency, enabled=self.cfg.notify)

    def _dnotify(self, title: str, body: str = "", urgency: str = "normal") -> None:
        """Per-dictation notification — suppressed for hands-free (wakeword) sessions."""
        if not self._session_silent:
            self._notify(title, body, urgency=urgency)

    def _rnotify(self, title: str, body: str = "", urgency: str = "normal") -> None:
        """Routing feedback — which preset/keyword a voice command matched. Shown
        even for hands-free sessions (it has its own toggle) so you can always see
        what you triggered. Only fires on a real match, so it never spams silence."""
        notify(title, body, urgency=urgency, enabled=self.cfg.notify_routing)

    def _emit(self, state: str, workflow: str | None = None, message: str = "") -> None:
        if self.status_cb:
            try:
                self.status_cb(state, workflow, message)
            except Exception:  # noqa: BLE001 - never let UI errors break the engine
                pass

    # -- model load (slow; call off the UI thread) ----------------------------
    def prepare(self) -> None:
        engine = self.cfg.active_stt
        log(f"STT engine: {engine.name} ({'local' if engine.is_local else engine.url})")
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
            log(f"Using remote STT '{engine.name}' — no local model to load")
        self._prepared = True
        self._init_wakeword()
        log("Ready.")
        self._emit("idle", None, "Ready")

    @property
    def ready(self) -> bool:
        return getattr(self, "_prepared", False)

    @property
    def is_recording(self) -> bool:
        return self._recording is not None or self._streaming is not None

    def _vad_start(self) -> None:
        self._vad_stop()
        import time
        from . import audio
        from gi.repository import GLib
        
        self._vad_started_at = time.time()
        self._vad_last_speech = time.time()
        
        silence = max(0.5, self.cfg.wakeword_silence_seconds)
        def on_level(level):
            now = time.time()
            if level > 0.05:
                self._vad_last_speech = now
            elif now - self._vad_started_at > 2.0 and now - self._vad_last_speech > silence:
                if getattr(self, "is_recording", False):
                    GLib.idle_add(lambda: self.finish_dictation(send_enter=False))
                    self._vad_stop()

        self._vad_meter = audio.LevelMeter(self.cfg.mic, on_level=on_level)
        self._vad_meter.start()

    def _vad_stop(self) -> None:
        if getattr(self, '_vad_meter', None) is not None:
            self._vad_meter.stop()
            self._vad_meter = None

    def _play_sound(self, sound_name: str) -> None:
        if not self.cfg.sounds_enabled:
            return
        from . import sound
        sound.play(fallback=sound_name)

    def _play_cue(self, cue: str) -> None:
        """Audio feedback for a dictation session.

        Hands-free (wakeword) sessions play only their own dedicated cue, or
        nothing when it is unset — they are independent of the manual 'Play audio
        cues' switch, because the sound is the *only* feedback a hands-free
        session gets (its notifications are suppressed). Manual sessions use the
        [sounds] cues, gated by that switch, and fall back to a built-in system
        sound when no file is configured."""
        from . import sound
        if self._session_silent:
            # Hands-free: the chosen wakeword sound, or silence. No fallback, so
            # clearing the field is how you turn the cue off.
            path = self.cfg.wakeword_sound_detected if cue == "before" else self.cfg.wakeword_sound_done
            if path:
                sound.play(path)
            return
        if not self.cfg.sounds_enabled:
            return
        if cue == "before":
            sound.play(self.cfg.sound_before, fallback="device-added")
        else:
            sound.play(self.cfg.sound_after, fallback="complete")

    # -- recording control ----------------------------------------------------
    def start_dictation(self, workflow: Workflow | None = None, silent: bool = False) -> None:
        wf = workflow or self._route_workflow
        streamer: RivaRealtimeStreamer | None = None
        with self._lock:
            if not self.ready or self._busy or self.is_recording:
                return
            self._session_silent = silent
            self._target_window = active_window_id()
            self._active_workflow = wf
            if wf.mode == "stream":
                engine = self.cfg.active_stt
                if not engine.is_streaming:
                    self._active_workflow = None
                    self._emit("error", wf.name, "Active STT engine is not realtime streaming")
                    self._notify("Streaming unavailable", "Select a riva_realtime STT engine.", "critical")
                    return
                self._stream_segment_text = ""
                streamer = RivaRealtimeStreamer(
                    engine,
                    device=self.cfg.mic,
                    language=self._stream_language(),
                    on_text=self._on_stream_text,
                    on_status=lambda msg: log(f"stream: {msg}"),
                    on_error=lambda exc, label=wf.name: self._on_stream_error(label, exc),
                )
                self._streaming = streamer
            else:
                self._recording = Recording(self.recorder_name, self.cfg.mic)
                self._vad_start()

        if streamer is not None:
            self._emit("streaming", wf.name, "Live transcript…")
            self._dnotify(f"● {wf.name}", "Live transcript…")
            try:
                streamer.start()
            except Exception as exc:  # noqa: BLE001
                with self._lock:
                    if self._streaming is streamer:
                        self._streaming = None
                        self._active_workflow = None
                self._emit("error", wf.name, str(exc))
                self._notify("Streaming failed", str(exc), "critical")
            return

        self._emit("recording", wf.name, "Recording…")
        self._dnotify(f"● {wf.name}", "Recording…")
        self._play_cue("before")

    def finish_dictation(self, send_enter: bool = False) -> None:
        self._vad_stop()
        with self._lock:
            if self._streaming is not None:
                streamer, wf, win = self._streaming, self._active_workflow, self._target_window
                self._streaming = None
                self._active_workflow = None
                self._stream_segment_text = ""
            else:
                streamer = None
                if self._recording is None:
                    return
                rec, wf, win = self._recording, self._active_workflow, self._target_window
                self._recording = None
                self._active_workflow = None
                self._busy = True
        if streamer is not None:
            streamer.stop()
            if send_enter:
                from .paste import press_enter
                press_enter(win)
            self._emit("done", wf.name if wf else None, "Streaming stopped")
            self._emit("idle", None, "Ready")
            return

        audio_path = rec.stop()
        self._play_cue("after")
        threading.Thread(
            target=self._process, args=(audio_path, wf, win, send_enter), daemon=True
        ).start()

    def cancel_dictation(self) -> None:
        self._vad_stop()
        with self._lock:
            if self._streaming is not None:
                streamer = self._streaming
                self._streaming = None
                self._active_workflow = None
                self._stream_segment_text = ""
                rec = None
            else:
                streamer = None
                if self._recording is None:
                    return
                rec = self._recording
                self._recording = None
                self._active_workflow = None
        if streamer is not None:
            streamer.stop()
            self._emit("idle", None, "Cancelled")
            self._notify("Cancelled", "Streaming stopped.", "low")
            self._play_sound("device-removed")
            return
        rec.discard()
        self._emit("idle", None, "Cancelled")
        self._notify("Cancelled", "Recording discarded.", "low")
        self._play_sound("device-removed")

    def toggle(self, workflow: Workflow) -> None:
        """Start recording, or stop + process (used by GUI clicks and combos)."""
        if not self.ready:
            self._notify("Please wait", "Model still loading…", "low")
            return
        if self._busy:
            self._notify("Busy", "Still processing the last clip…", "low")
            return
        if not self.is_recording:
            self.start_dictation(workflow)
        else:
            self.finish_dictation(send_enter=False)

    # -- live streaming -------------------------------------------------------
    def _stream_language(self) -> str:
        lang = (self.cfg.language or "").strip()
        if lang.lower() == "en":
            return "en-US"
        if lang.lower().startswith("en-"):
            return lang
        return ""

    def _stable_stream_text(self, text: str, final: bool) -> str:
        text = quality.clean(text, strip_trailing_punctuation=False)
        if final:
            return text
        cut = max(text.rfind(" "), text.rfind("\n"), text.rfind("\t"))
        return text[:cut + 1] if cut >= 0 else ""

    def _on_stream_text(self, text: str, final: bool) -> None:
        stable = self._stable_stream_text(text, final)
        if not stable:
            return
        with self._lock:
            win = self._target_window
            current = self._stream_segment_text
        if not stable.startswith(current):
            if not final:
                return
            suffix = ""
        else:
            suffix = stable[len(current):]
        if suffix:
            deliver(suffix, mode="type", window_id=win, type_delay_ms=self.cfg.type_delay_ms)
        if final and (stable or current) and not stable.endswith((" ", "\n", "\t")):
            deliver(" ", mode="type", window_id=win, type_delay_ms=self.cfg.type_delay_ms)
        with self._lock:
            self._stream_segment_text = "" if final else stable

    def _on_stream_error(self, label: str, exc: Exception) -> None:
        with self._lock:
            self._streaming = None
            self._active_workflow = None
            self._stream_segment_text = ""
        self._emit("error", label, str(exc))
        self._notify("Streaming failed", str(exc), "critical")
        log(f"ERROR ({label} streaming): {exc}")

    # -- worker ---------------------------------------------------------------
    def _process(self, audio_path, workflow: Workflow, window_id, send_enter: bool = False) -> None:
        label = workflow.name
        try:
            # Quality gate: drop silent / too-short clips before we even transcribe.
            duration, rms = quality.analyze_wav(audio_path)
            if quality.too_quiet(duration, rms,
                                 min_seconds=self.cfg.min_speech_seconds,
                                 silence_rms=self.cfg.silence_rms):
                self._emit("idle", label, "Too quiet")
                log("Nothing heard — clip too quiet/short.")
                return

            self._emit("busy", label, "Transcribing…")
            self._dnotify(f"⌛ {label}", "Transcribing…")
            hotwords = ", ".join(self.cfg.all_keywords) if workflow.mode == "route" else ""
            text = stt.transcribe(
                self.cfg.active_stt,
                audio_path,
                language=self.cfg.language,
                hotwords=hotwords,
                local_transcriber=self.transcriber,
                timeout=self.cfg.timeout,
            )

            text = quality.clean(text, strip_trailing_punctuation=self.cfg.strip_trailing_punctuation)
            if not text or (self.cfg.reject_hallucinations and quality.is_hallucination(text, duration)):
                self._emit("idle", label, "No speech detected")
                log("Nothing heard — no speech detected.")
                return

            # Voice routing: pick the preset from a spoken keyword, strip it.
            if workflow.mode == "route":
                res = route(text, self.cfg.workflows, threshold=self.cfg.routing_threshold)
                target = self.cfg.preset_by_name(res.preset_name) or self.cfg.default_preset
                text = res.text
                label = target.name if target else "Transcribe"
                icon = (getattr(target, "icon", "") or "🎙") if target else "🎙"
                via = f"“{res.keyword}”" if res.keyword else "no keyword → default"
                self._emit("busy", label, f"→ {label} ({via})")
                self._rnotify(f"{icon} {label}", f"matched: {via}")
                log(f"→ routed to {label} (matched: {via})")
            else:
                target = workflow

            if target and target.mode == "rewrite" and target.prompt:
                if not text:
                    self._emit("idle", label, "Only a keyword heard")
                    log("Only the keyword was heard — nothing to type.")
                    return
                self._emit("busy", label, "Rewriting…")
                self._dnotify(f"⌛ {label}", "Rewriting…")
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
                    self._dnotify("Rewrite failed", str(exc), "critical")
                    log(f"ERROR ({label} rewrite): {exc}")
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
            if send_enter:
                from .paste import press_enter
                press_enter(window_id)
            self._emit("done", label, text)
            log(f"✓ {label}: {text[:120]}")
            self._dnotify(f"✓ {label}", text[:80] + ("…" if len(text) > 80 else ""))
        except Exception as exc:  # noqa: BLE001 - surface any failure
            self._emit("error", label, str(exc))
            self._dnotify("Error", str(exc), "critical")
            log(f"ERROR ({label}): {exc}")
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

    def start_input(self):
        """Start the configured input handler; returns its listener (joinable)."""
        if self.cfg.input_mode == "modifiers":
            from .inputmode import ModifierScheme

            self._scheme = ModifierScheme(
                self,
                start=self.cfg.key_start,
                stop=self.cfg.key_stop,
                send=self.cfg.key_send,
                cancel=self.cfg.key_cancel,
                push_to_talk=self.cfg.push_to_talk,
            )
            return self._scheme.start_listener()
        return self.start_hotkeys()

    def stop_input(self) -> None:
        scheme = getattr(self, "_scheme", None)
        if scheme is not None:
            scheme.stop_listener()
            self._scheme = None
        self.stop_hotkeys()
        if self._wakeword_listener:
            self._wakeword_listener.stop()

    def stop_hotkeys(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    # -- headless run loop ----------------------------------------------------
    def run(self) -> None:
        self.prepare()
        if self.cfg.input_mode == "modifiers":
            log(f"Recorder: {self.recorder_name}. Input: Ctrl+Win start · Ctrl stop+paste · Alt stop+paste+Enter · Esc cancel")
        else:
            keys = ", ".join([f"{self.cfg.routing_hotkey}→Voice"] if self.cfg.routing_enabled else [])
            log(f"Recorder: {self.recorder_name}. Hotkeys: {keys}")
        self._notify("Blitztext ready", "Focus a text field and start dictating.")

        listener = self.start_input()
        try:
            listener.join()
        finally:
            self.stop_input()

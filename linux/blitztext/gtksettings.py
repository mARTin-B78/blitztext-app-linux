"""GTK settings: dropdown + editor managers for prompt presets and engines.

Tabs:
  Presets  - prompt presets (select from a dropdown, edit, add, delete)
  Engines  - STT and LLM engine presets with online/offline status + STT test
  Input    - input scheme, keys, quality gate
  General  - mic (with live level meter), output, language, notifications, autostart
"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from . import audio, autostart, llm, stt  # noqa: E402
from .config import Config, save  # noqa: E402
from .llm import LLMEngine  # noqa: E402
from .stt import STTEngine  # noqa: E402
from .config import Workflow  # noqa: E402

RESP_SAVE = 1
RESP_SAVE_RESTART = 2
GREEN, RED, GREY = "#34c759", "#ff3b30", "#b8b8be"


def _dot(color: str) -> str:
    return f'<span foreground="{color}">●</span>'


def _labeled(parent: Gtk.Box, label: str, widget: Gtk.Widget, width: int = 130) -> Gtk.Widget:
    row = Gtk.Box(spacing=10)
    row.set_margin_top(3); row.set_margin_bottom(3)
    lbl = Gtk.Label(label=label, xalign=0.0); lbl.set_size_request(width, -1)
    row.pack_start(lbl, False, False, 0)
    row.pack_start(widget, True, True, 0)
    parent.pack_start(row, False, False, 0)
    return widget


def _entry(text="", placeholder="") -> Gtk.Entry:
    e = Gtk.Entry(); e.set_text(str(text)); e.set_hexpand(True)
    if placeholder:
        e.set_placeholder_text(placeholder)
    return e


def _combo(options, active=None) -> Gtk.ComboBoxText:
    c = Gtk.ComboBoxText()
    for o in options:
        c.append_text(o)
    if active in options:
        c.set_active(options.index(active))
    elif options:
        c.set_active(0)
    return c


def _page(nb: Gtk.Notebook, title: str) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    for m in ("top", "bottom", "start", "end"):
        getattr(box, f"set_margin_{m}")(12)
    nb.append_page(box, Gtk.Label(label=title))
    return box


class SettingsDialog:
    def __init__(self, parent: Gtk.Window, cfg: Config, daemon=None):
        self.cfg = cfg
        self.daemon = daemon
        self._meter = None
        self._wf_idx = self._stt_idx = self._llm_idx = 0

        self.dlg = Gtk.Dialog(title="Blitztext — Settings", transient_for=parent, modal=True)
        self.dlg.set_default_size(620, 600)
        self.dlg.add_button("Close", Gtk.ResponseType.CLOSE)
        self.dlg.add_button("Save", RESP_SAVE)
        self.dlg.add_button("Save & Restart", RESP_SAVE_RESTART)

        nb = Gtk.Notebook()
        self.dlg.get_content_area().pack_start(nb, True, True, 0)
        self._build_presets(_page(nb, "Presets"))
        self._build_engines(_page(nb, "Engines"))
        self._build_input(_page(nb, "Input"))
        self._build_general(_page(nb, "General"))

        self.dlg.connect("response", self._on_response)
        self.dlg.connect("destroy", lambda *_: self._stop_meter())

    # ===== Presets ==========================================================
    def _build_presets(self, page: Gtk.Box) -> None:
        self._wf_idx = 0
        bar = Gtk.Box(spacing=8)
        self.wf_combo = Gtk.ComboBoxText()
        for wf in self.cfg.workflows:
            self.wf_combo.append_text(wf.name)
        self.wf_combo.set_active(0)
        self.wf_combo.connect("changed", self._wf_changed)
        bar.pack_start(self.wf_combo, True, True, 0)
        add = Gtk.Button(label="+ Add"); add.connect("clicked", self._wf_add)
        rm = Gtk.Button(label="Delete"); rm.connect("clicked", self._wf_delete)
        bar.pack_start(add, False, False, 0); bar.pack_start(rm, False, False, 0)
        page.pack_start(bar, False, False, 4)

        form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        page.pack_start(form, True, True, 6)
        self.wf_name = _labeled(form, "Name", _entry(placeholder="Preset name"))
        self.wf_desc = _labeled(form, "Description", _entry(placeholder="Short description shown in the panel"))
        self.wf_keywords = _labeled(form, "Keywords (comma)", _entry(placeholder="nicer email, bessere email"))
        self.wf_hotkey = _labeled(form, "Hotkey (optional)", _entry(placeholder="<ctrl>+<alt>+e   (blank = none)"))
        self.wf_mode = _labeled(form, "Mode", _combo(["transcribe", "rewrite"]))
        self.wf_model = _labeled(form, "LLM model (opt.)", _entry(placeholder="blank = use the active LLM engine's model"))
        self.wf_temp = _labeled(form, "Temperature (opt.)", _entry(placeholder="blank = engine default (e.g. 0.3)"))

        form.pack_start(Gtk.Label(label="Prompt sent to the LLM (rewrite mode):", xalign=0.0), False, False, 6)
        frame = Gtk.Frame(); frame.set_shadow_type(Gtk.ShadowType.IN)
        sw = Gtk.ScrolledWindow(); sw.set_min_content_height(150)
        self.wf_prompt = Gtk.TextView(); self.wf_prompt.set_wrap_mode(Gtk.WrapMode.WORD)
        self.wf_prompt.set_left_margin(6); self.wf_prompt.set_top_margin(6)
        sw.add(self.wf_prompt); frame.add(sw)
        form.pack_start(frame, True, True, 0)
        self._wf_load(0)

    def _wf_load(self, idx: int) -> None:
        if not (0 <= idx < len(self.cfg.workflows)):
            return
        wf = self.cfg.workflows[idx]
        self.wf_name.set_text(wf.name)
        self.wf_desc.set_text(wf.description)
        self.wf_keywords.set_text(", ".join(wf.keywords))
        self.wf_hotkey.set_text(wf.hotkey)
        self.wf_mode.set_active(["transcribe", "rewrite"].index(wf.mode) if wf.mode in ("transcribe", "rewrite") else 0)
        self.wf_model.set_text(wf.model or "")
        self.wf_temp.set_text("" if wf.temperature is None else str(wf.temperature))
        self.wf_prompt.get_buffer().set_text(wf.prompt)
        self._wf_idx = idx

    def _wf_commit(self) -> None:
        idx = self._wf_idx
        if not (0 <= idx < len(self.cfg.workflows)):
            return
        wf = self.cfg.workflows[idx]
        wf.name = self.wf_name.get_text().strip() or wf.name
        wf.description = self.wf_desc.get_text().strip()
        wf.keywords = [k.strip() for k in self.wf_keywords.get_text().split(",") if k.strip()]
        wf.hotkey = self.wf_hotkey.get_text().strip()
        wf.mode = self.wf_mode.get_active_text() or "transcribe"
        wf.model = self.wf_model.get_text().strip() or None
        t = self.wf_temp.get_text().strip()
        wf.temperature = float(t) if _isfloat(t) else None
        b = self.wf_prompt.get_buffer()
        wf.prompt = b.get_text(b.get_start_iter(), b.get_end_iter(), True).strip()
        # reflect a possibly-changed name in the dropdown
        self.wf_combo.remove(idx); self.wf_combo.insert_text(idx, wf.name)
        self.wf_combo.set_active(idx)

    def _wf_changed(self, combo) -> None:
        new = combo.get_active()
        if new < 0 or new == self._wf_idx:
            return
        self._wf_commit()
        self._wf_load(new)

    def _wf_add(self, _b) -> None:
        self._wf_commit()
        wf = Workflow(name="New preset", hotkey="", mode="rewrite", prompt="", description="")
        self.cfg.workflows.append(wf)
        self.wf_combo.append_text(wf.name)
        self.wf_combo.set_active(len(self.cfg.workflows) - 1)
        self._wf_load(len(self.cfg.workflows) - 1)

    def _wf_delete(self, _b) -> None:
        if len(self.cfg.workflows) <= 1:
            return
        idx = self._wf_idx
        del self.cfg.workflows[idx]
        self.wf_combo.remove(idx)
        self._wf_idx = -1
        self.wf_combo.set_active(0)
        self._wf_load(0)

    # ===== Engines ==========================================================
    def _build_engines(self, page: Gtk.Box) -> None:
        page.pack_start(self._stt_section(), False, False, 4)
        page.pack_start(Gtk.Separator(), False, False, 8)
        page.pack_start(self._llm_section(), False, False, 4)
        self._refresh_status()

    def _stt_section(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.pack_start(Gtk.Label(label="Speech-to-text engine", xalign=0.0), False, False, 2)
        self._stt_idx = 0
        bar = Gtk.Box(spacing=8)
        self.stt_combo = Gtk.ComboBoxText()
        for e in self.cfg.stt_engines:
            self.stt_combo.append_text(e.name)
        self.stt_combo.set_active(self._index_of(self.cfg.stt_engines, self.cfg.stt_active))
        self.stt_combo.connect("changed", self._stt_changed)
        self.stt_dot = Gtk.Label(); self.stt_dot.set_markup(_dot(GREY))
        bar.pack_start(self.stt_dot, False, False, 0)
        bar.pack_start(self.stt_combo, True, True, 0)
        for label, cb in (("+ Add", self._stt_add), ("Delete", self._stt_delete),
                          ("Test", self._stt_test), ("Refresh", lambda _b: self._refresh_status())):
            b = Gtk.Button(label=label); b.connect("clicked", cb); bar.pack_start(b, False, False, 0)
        box.pack_start(bar, False, False, 2)

        form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL); box.pack_start(form, False, False, 2)
        self.stt_type = _labeled(form, "Type", _combo(["local", "openai"]))
        self.stt_url = _labeled(form, "URL", _entry(placeholder="http://localhost:8010/v1   (blank for local)"))
        self.stt_model = _labeled(form, "Model", _entry(placeholder="e.g. Systran/faster-whisper-base  ·  'small' for local"))
        self.stt_key = _labeled(form, "API key env", _entry(placeholder="env var name, e.g. GROQ_API_KEY   (optional)"))
        self.stt_result = Gtk.Label(xalign=0.0); self.stt_result.set_line_wrap(True)
        box.pack_start(self.stt_result, False, False, 2)
        self._stt_load(self.stt_combo.get_active())
        return box

    def _llm_section(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.pack_start(Gtk.Label(label="Language model (rewrite)", xalign=0.0), False, False, 2)
        self._llm_idx = 0
        bar = Gtk.Box(spacing=8)
        self.llm_combo = Gtk.ComboBoxText()
        for e in self.cfg.llm_engines:
            self.llm_combo.append_text(e.name)
        self.llm_combo.set_active(self._index_of(self.cfg.llm_engines, self.cfg.llm_active))
        self.llm_combo.connect("changed", self._llm_changed)
        self.llm_dot = Gtk.Label(); self.llm_dot.set_markup(_dot(GREY))
        bar.pack_start(self.llm_dot, False, False, 0)
        bar.pack_start(self.llm_combo, True, True, 0)
        for label, cb in (("+ Add", self._llm_add), ("Delete", self._llm_delete),
                          ("Refresh", lambda _b: self._refresh_status())):
            b = Gtk.Button(label=label); b.connect("clicked", cb); bar.pack_start(b, False, False, 0)
        box.pack_start(bar, False, False, 2)

        form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL); box.pack_start(form, False, False, 2)
        self.llm_url = _labeled(form, "Base URL", _entry(placeholder="http://localhost:28080/v1  ·  https://api.openai.com/v1"))
        self.llm_model = _labeled(form, "Model", _entry(placeholder="e.g. gpt-4o-mini, Qwen3.5-4B"))
        self.llm_key = _labeled(form, "API key env", _entry(placeholder="env var name, e.g. OPENAI_API_KEY   (blank for local)"))
        self.llm_temp = _labeled(form, "Temperature", _entry(placeholder="0.3"))
        self._llm_load(self.llm_combo.get_active())
        return box

    # -- STT engine editor ---
    def _stt_load(self, idx: int) -> None:
        if not (0 <= idx < len(self.cfg.stt_engines)):
            return
        e = self.cfg.stt_engines[idx]
        self.stt_type.set_active(["local", "openai"].index(e.type) if e.type in ("local", "openai") else 0)
        self.stt_url.set_text(e.url); self.stt_model.set_text(e.model); self.stt_key.set_text(e.api_key_env)
        self._stt_idx = idx

    def _stt_commit(self) -> None:
        idx = self._stt_idx
        if not (0 <= idx < len(self.cfg.stt_engines)):
            return
        e = self.cfg.stt_engines[idx]
        e.type = self.stt_type.get_active_text() or "local"
        e.url = self.stt_url.get_text().strip().rstrip("/")
        e.model = self.stt_model.get_text().strip()
        e.api_key_env = self.stt_key.get_text().strip()

    def _stt_changed(self, combo):
        new = combo.get_active()
        if new < 0 or new == self._stt_idx:
            return
        self._stt_commit(); self._stt_load(new); self._refresh_status()

    def _stt_add(self, _b):
        self._stt_commit()
        e = STTEngine("New STT", "openai", "http://localhost:8010/v1", "whisper-1")
        self.cfg.stt_engines.append(e); self.stt_combo.append_text(e.name)
        self.stt_combo.set_active(len(self.cfg.stt_engines) - 1)
        self._stt_load(len(self.cfg.stt_engines) - 1)

    def _stt_delete(self, _b):
        if len(self.cfg.stt_engines) <= 1:
            return
        del self.cfg.stt_engines[self._stt_idx]
        self.stt_combo.remove(self._stt_idx); self._stt_idx = -1
        self.stt_combo.set_active(0); self._stt_load(0)

    def _stt_test(self, _b):
        self._stt_commit()
        e = self.cfg.stt_engines[self._stt_idx]
        self.stt_result.set_markup("<i>Recording 4s — speak now…</i>")
        threading.Thread(target=self._run_stt_test, args=(e,), daemon=True).start()

    def _run_stt_test(self, engine):
        from .recorder import Recording, detect_recorder
        try:
            rec = Recording(detect_recorder(self.cfg.recorder), self.cfg.mic)
            time.sleep(4.0)
            wav = rec.stop()
            tr = self.daemon.transcriber if (self.daemon and engine.is_local) else None
            res = stt.benchmark(engine, wav, language=self.cfg.language, local_transcriber=tr)
            wav.unlink(missing_ok=True)
            if res.ok:
                msg = f"<b>{res.seconds:.2f}s</b> · {GLib.markup_escape_text(res.text or '(empty)')}"
            else:
                msg = f'<span foreground="{RED}">{GLib.markup_escape_text(res.error)}</span>'
        except Exception as exc:  # noqa: BLE001
            msg = f'<span foreground="{RED}">{GLib.markup_escape_text(str(exc))}</span>'
        GLib.idle_add(self.stt_result.set_markup, msg)

    # -- LLM engine editor ---
    def _llm_load(self, idx: int) -> None:
        if not (0 <= idx < len(self.cfg.llm_engines)):
            return
        e = self.cfg.llm_engines[idx]
        self.llm_url.set_text(e.url); self.llm_model.set_text(e.model)
        self.llm_key.set_text(e.api_key_env); self.llm_temp.set_text(str(e.temperature))
        self._llm_idx = idx

    def _llm_commit(self) -> None:
        idx = self._llm_idx
        if not (0 <= idx < len(self.cfg.llm_engines)):
            return
        e = self.cfg.llm_engines[idx]
        e.url = self.llm_url.get_text().strip().rstrip("/")
        e.model = self.llm_model.get_text().strip()
        e.api_key_env = self.llm_key.get_text().strip()
        if _isfloat(self.llm_temp.get_text().strip()):
            e.temperature = float(self.llm_temp.get_text().strip())

    def _llm_changed(self, combo):
        new = combo.get_active()
        if new < 0 or new == self._llm_idx:
            return
        self._llm_commit(); self._llm_load(new); self._refresh_status()

    def _llm_add(self, _b):
        self._llm_commit()
        e = LLMEngine("New LLM", "http://localhost:28080/v1", "model", "")
        self.cfg.llm_engines.append(e); self.llm_combo.append_text(e.name)
        self.llm_combo.set_active(len(self.cfg.llm_engines) - 1)
        self._llm_load(len(self.cfg.llm_engines) - 1)

    def _llm_delete(self, _b):
        if len(self.cfg.llm_engines) <= 1:
            return
        del self.cfg.llm_engines[self._llm_idx]
        self.llm_combo.remove(self._llm_idx); self._llm_idx = -1
        self.llm_combo.set_active(0); self._llm_load(0)

    # -- status dots (threaded) ---
    def _refresh_status(self) -> None:
        s = self.cfg.stt_engines[self._stt_idx] if 0 <= self._stt_idx < len(self.cfg.stt_engines) else None
        self._stt_commit()
        l = self.cfg.llm_engines[self._llm_idx] if 0 <= self._llm_idx < len(self.cfg.llm_engines) else None
        self._llm_commit()

        def check():
            sc = GREEN if (s and stt.status(s)) else RED if s else GREY
            lc = GREEN if (l and llm.status(l)) else RED if l else GREY
            GLib.idle_add(self.stt_dot.set_markup, _dot(sc))
            GLib.idle_add(self.llm_dot.set_markup, _dot(lc))
        threading.Thread(target=check, daemon=True).start()

    # ===== Input ============================================================
    def _build_input(self, page: Gtk.Box) -> None:
        self.in_mode = _labeled(page, "Input mode", _combo(["modifiers", "hotkeys"], self.cfg.input_mode))
        self.in_ptt = Gtk.Switch(); self.in_ptt.set_active(self.cfg.push_to_talk); self.in_ptt.set_halign(Gtk.Align.START)
        _labeled(page, "Push-to-talk", self.in_ptt)
        self.in_start = _labeled(page, "Start", _entry(self.cfg.key_start))
        self.in_stop = _labeled(page, "Stop + paste", _entry(self.cfg.key_stop))
        self.in_send = _labeled(page, "Stop + paste + Enter", _entry(self.cfg.key_send))
        self.in_cancel = _labeled(page, "Cancel", _entry(self.cfg.key_cancel))
        page.pack_start(Gtk.Separator(), False, False, 8)
        page.pack_start(Gtk.Label(label="Quality gate", xalign=0.0), False, False, 2)
        self.q_min = _labeled(page, "Min seconds", _entry(self.cfg.min_speech_seconds))
        self.q_rms = _labeled(page, "Silence RMS", _entry(self.cfg.silence_rms))
        self.q_halluc = Gtk.Switch(); self.q_halluc.set_active(self.cfg.reject_hallucinations); self.q_halluc.set_halign(Gtk.Align.START)
        _labeled(page, "Reject hallucinations", self.q_halluc)
        self.q_strip = Gtk.Switch(); self.q_strip.set_active(self.cfg.strip_trailing_punctuation); self.q_strip.set_halign(Gtk.Align.START)
        _labeled(page, "Strip trailing punctuation", self.q_strip)

    # ===== General ==========================================================
    def _build_general(self, page: Gtk.Box) -> None:
        self._mics = audio.list_mics()
        names = [label for _, label in self._mics]
        cur = next((lbl for nm, lbl in self._mics if nm == self.cfg.mic), names[0])
        self.gen_mic = _labeled(page, "Microphone", _combo(names, cur))

        self.mic_level = Gtk.LevelBar(); self.mic_level.set_min_value(0); self.mic_level.set_max_value(1)
        _labeled(page, "Input level", self.mic_level)
        self.gen_mic.connect("changed", lambda _c: self._restart_meter())

        self.gen_output = _labeled(page, "Output", _combo(["type", "paste"], self.cfg.output))
        self.gen_lang = _labeled(page, "Language hint", _entry(self.cfg.language, placeholder="de, en, …   (blank = autodetect)"))
        self.gen_notify = Gtk.Switch(); self.gen_notify.set_active(self.cfg.notify); self.gen_notify.set_halign(Gtk.Align.START)
        _labeled(page, "Notifications", self.gen_notify)
        self.gen_boot = Gtk.Switch(); self.gen_boot.set_active(autostart.is_enabled()); self.gen_boot.set_halign(Gtk.Align.START)
        _labeled(page, "Launch on login", self.gen_boot)

        page.pack_start(Gtk.Separator(), False, False, 8)
        page.pack_start(Gtk.Label(label="Local Whisper (for the local STT engine)", xalign=0.0), False, False, 2)
        self.gen_model = _labeled(page, "Model", _entry(self.cfg.model))
        self.gen_device = _labeled(page, "Device", _combo(["auto", "cpu", "cuda"], self.cfg.device))
        self.gen_compute = _labeled(page, "Compute type", _combo(["auto", "int8", "float16", "int8_float16"], self.cfg.compute_type))
        self._start_meter()

    def _selected_mic_name(self) -> str:
        i = self.gen_mic.get_active()
        return self._mics[i][0] if 0 <= i < len(self._mics) else ""

    def _start_meter(self) -> None:
        self._stop_meter()
        self._meter = audio.LevelMeter(self._selected_mic_name(), on_level=lambda v: GLib.idle_add(self.mic_level.set_value, v))
        self._meter.start()

    def _restart_meter(self) -> None:
        self._start_meter()

    def _stop_meter(self) -> None:
        if self._meter is not None:
            self._meter.stop(); self._meter = None

    # ===== save / collect ====================================================
    def _collect(self) -> bool:
        try:
            self._wf_commit(); self._stt_commit(); self._llm_commit()
            c = self.cfg
            c.stt_active = self.stt_combo.get_active_text() or c.stt_active
            c.llm_active = self.llm_combo.get_active_text() or c.llm_active
            c.input_mode = self.in_mode.get_active_text() or "modifiers"
            c.push_to_talk = self.in_ptt.get_active()
            c.key_start = self.in_start.get_text().strip()
            c.key_stop = self.in_stop.get_text().strip()
            c.key_send = self.in_send.get_text().strip()
            c.key_cancel = self.in_cancel.get_text().strip()
            c.min_speech_seconds = float(self.q_min.get_text())
            c.silence_rms = float(self.q_rms.get_text())
            c.reject_hallucinations = self.q_halluc.get_active()
            c.strip_trailing_punctuation = self.q_strip.get_active()
            c.mic = self._selected_mic_name()
            c.output = self.gen_output.get_active_text() or "type"
            c.language = self.gen_lang.get_text().strip()
            c.notify = self.gen_notify.get_active()
            c.model = self.gen_model.get_text().strip()
            c.device = self.gen_device.get_active_text() or "auto"
            c.compute_type = self.gen_compute.get_active_text() or "auto"
            autostart.set_enabled(self.gen_boot.get_active())
        except ValueError as exc:
            self._error(f"Check numeric fields: {exc}")
            return False
        return True

    def _error(self, msg: str) -> None:
        d = Gtk.MessageDialog(transient_for=self.dlg, modal=True, message_type=Gtk.MessageType.ERROR,
                              buttons=Gtk.ButtonsType.OK, text=msg)
        d.run(); d.destroy()

    def _info(self, msg: str) -> None:
        d = Gtk.MessageDialog(transient_for=self.dlg, modal=True, message_type=Gtk.MessageType.INFO,
                              buttons=Gtk.ButtonsType.OK, text=msg)
        d.run(); d.destroy()

    def _on_response(self, dlg, resp):
        if resp == RESP_SAVE:
            if self._collect():
                save(self.cfg)
                self._info("Saved. Restart Blitztext to apply engine/hotkey changes.")
            return
        if resp == RESP_SAVE_RESTART:
            if self._collect():
                save(self.cfg)
                self._stop_meter()
                os.execv(sys.executable, [sys.executable, "-m", "blitztext", "tray"])
            return
        self._stop_meter()
        dlg.destroy()

    @staticmethod
    def _index_of(engines, name):
        for i, e in enumerate(engines):
            if e.name == name:
                return i
        return 0

    def run_dialog(self) -> None:
        self.dlg.show_all()


def _isfloat(s: str) -> bool:
    try:
        float(s)
        return True
    except (TypeError, ValueError):
        return False

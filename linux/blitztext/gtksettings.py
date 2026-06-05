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
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

from . import audio, autostart, benchmark, llm, logbuffer, stt  # noqa: E402
from .config import Config, save  # noqa: E402
from .llm import LLMEngine  # noqa: E402
from .stt import STTEngine  # noqa: E402
from .config import Workflow  # noqa: E402

RESP_SAVE = 1
RESP_SAVE_RESTART = 2
GREEN, RED, GREY = "#34c759", "#ff3b30", "#b8b8be"


def _dot(color: str) -> str:
    return f'<span foreground="{color}">●</span>'


# --- key capture (for the "Set" bind buttons) -------------------------------
_MOD_ORDER = ["ctrl", "alt", "shift", "cmd"]


def _keyval_token(keyval: int) -> str | None:
    name = Gdk.keyval_name(keyval) or ""
    table = {
        "Control_L": "ctrl", "Control_R": "ctrl",
        "Alt_L": "alt", "Alt_R": "alt", "ISO_Level3_Shift": "alt",
        "Super_L": "cmd", "Super_R": "cmd", "Meta_L": "cmd", "Meta_R": "cmd",
        "Shift_L": "shift", "Shift_R": "shift",
        "Escape": "esc", "space": "space", "Return": "enter", "Tab": "tab",
        "BackSpace": "backspace", "Delete": "delete",
    }
    if name in table:
        return table[name]
    if len(name) == 1 and name.isprintable():
        return name.lower()
    if len(name) >= 2 and name[0] in "Ff" and name[1:].isdigit():
        return name.lower()  # F1..F12
    return None


def _format_combo(tokens: list[str]) -> str:
    mods = [t for t in _MOD_ORDER if t in tokens]
    rest = [t for t in tokens if t not in _MOD_ORDER]
    parts = [(t if len(t) == 1 else f"<{t}>") for t in mods + rest]
    return "+".join(parts)


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


class ModelPicker(Gtk.Box):
    """An editable model field + a ▾ button opening a popover with a search bar
    on top and a scrollable, filtered list of models."""

    def __init__(self, placeholder: str = ""):
        super().__init__(spacing=4)
        self.entry = Gtk.Entry(); self.entry.set_hexpand(True)
        if placeholder:
            self.entry.set_placeholder_text(placeholder)
        self.pack_start(self.entry, True, True, 0)
        self.btn = Gtk.Button.new_from_icon_name("pan-down-symbolic", Gtk.IconSize.BUTTON)
        self.btn.set_tooltip_text("Browse models")
        self.pack_start(self.btn, False, False, 0)

        self.pop = Gtk.Popover(); self.pop.set_relative_to(self.btn)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for m in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{m}")(6)
        self.search = Gtk.SearchEntry(); self.search.set_placeholder_text("Search models…")
        box.pack_start(self.search, False, False, 0)
        sw = Gtk.ScrolledWindow()
        sw.set_min_content_height(300); sw.set_min_content_width(380)
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.listbox = Gtk.ListBox()
        self.listbox.set_filter_func(self._filter)
        sw.add(self.listbox); box.pack_start(sw, True, True, 0)
        self.pop.add(box)

        self.btn.connect("clicked", self._open)
        self.search.connect("search-changed", lambda _s: self.listbox.invalidate_filter())
        self.listbox.connect("row-activated", self._activated)

    def _filter(self, row) -> bool:
        return self.search.get_text().lower() in row.get_child().get_text().lower()

    def _open(self, _b) -> None:
        self.pop.show_all(); self.search.set_text(""); self.search.grab_focus()

    def _activated(self, _lb, row) -> None:
        self.entry.set_text(row.get_child().get_text())
        self.pop.popdown()

    def set_models(self, models) -> None:
        for child in self.listbox.get_children():
            self.listbox.remove(child)
        for m in models:
            row = Gtk.ListBoxRow()
            lbl = Gtk.Label(label=m, xalign=0.0)
            lbl.set_margin_top(4); lbl.set_margin_bottom(4); lbl.set_margin_start(8); lbl.set_margin_end(8)
            row.add(lbl); self.listbox.add(row)
        self.listbox.show_all()

    def get_text(self) -> str:
        return self.entry.get_text().strip()

    def set_text(self, value: str) -> None:
        self.entry.set_text(value or "")


def _model_combo(placeholder="") -> ModelPicker:
    return ModelPicker(placeholder)


def _combo_text(c: ModelPicker) -> str:
    return c.get_text()


def _fill_combo(combo: ModelPicker, options, current: str) -> None:
    combo.set_models(list(options))
    combo.set_text(current or "")


def _url_field(parent: Gtk.Box, label: str, placeholder: str, on_reload) -> Gtk.Entry:
    row = Gtk.Box(spacing=10); row.set_margin_top(3); row.set_margin_bottom(3)
    lbl = Gtk.Label(label=label, xalign=0.0); lbl.set_size_request(130, -1)
    row.pack_start(lbl, False, False, 0)
    e = Gtk.Entry(); e.set_hexpand(True)
    if placeholder:
        e.set_placeholder_text(placeholder)
    row.pack_start(e, True, True, 0)
    btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
    btn.set_tooltip_text("Load models from this URL")
    btn.connect("clicked", lambda _b: on_reload())
    row.pack_start(btn, False, False, 0)
    parent.pack_start(row, False, False, 0)
    return e


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
        self._tr_cache: dict = {}
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
        self._build_benchmark(_page(nb, "Benchmark"))
        self._build_log(_page(nb, "Log"))

        self._bind_entry = None
        self._bind_pressed: list[str] = []
        self.dlg.connect("key-press-event", self._on_bind_press)
        self.dlg.connect("key-release-event", self._on_bind_release)
        self.dlg.connect("response", self._on_response)
        self.dlg.connect("destroy", lambda *_: self._cleanup())

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
        self.wf_hotkey = self._key_field(form, "Hotkey (optional)", "", placeholder="click Set, or e.g. <ctrl>+<alt>+e", width=130)
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
        self.stt_name = _labeled(form, "Name", _entry(placeholder="e.g. faster-whisper GPU"))
        self.stt_type = _labeled(form, "Type", _combo(["local", "openai"]))
        self.stt_url = _url_field(form, "URL", "http://localhost:8010/v1   (blank for local)",
                                  lambda: self._populate_models(self.stt_model, self.stt_url.get_text().strip(), self.stt_key.get_text().strip()))
        self.stt_model = _labeled(form, "Model", _model_combo("pick after entering URL  ·  tiny/base/small… for local"))
        self.stt_key = _labeled(form, "API key env", _entry(placeholder="env var name, e.g. GROQ_API_KEY   (optional)"))
        self.stt_url.connect("changed", lambda _e: self._schedule_models("stt"))
        self.stt_key.connect("changed", lambda _e: self._schedule_models("stt"))
        self.stt_type.connect("changed", self._stt_type_changed)

        sep = Gtk.Separator(); sep.set_margin_top(4); form.pack_start(sep, False, False, 4)
        form.pack_start(Gtk.Label(label="Local engine (faster-whisper) — device & precision", xalign=0.0), False, False, 0)
        self.stt_device = _labeled(form, "Device", _combo(["auto", "cpu", "cuda"], self.cfg.device))
        self.stt_compute = _labeled(form, "Compute type", _combo(["auto", "int8", "float16", "int8_float16"], self.cfg.compute_type))

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
        self.llm_name = _labeled(form, "Name", _entry(placeholder="e.g. Local Qwen"))
        self.llm_type = _labeled(form, "Type", _combo(["local", "cloud"]))
        self.llm_url = _url_field(form, "Base URL", "http://localhost:28080/v1  ·  https://api.openai.com/v1",
                                  lambda: self._populate_models(self.llm_model, self.llm_url.get_text().strip(), self.llm_key.get_text().strip()))
        self.llm_model = _labeled(form, "Model", _model_combo("pick after entering URL"))
        self.llm_key = _labeled(form, "API key env", _entry(placeholder="env var name, e.g. OPENAI_API_KEY   (blank for local)"))
        self.llm_temp = _labeled(form, "Temperature", _entry(placeholder="0.3"))
        self.llm_url.connect("changed", lambda _e: self._schedule_models("llm"))
        self.llm_key.connect("changed", lambda _e: self._schedule_models("llm"))
        self._llm_load(self.llm_combo.get_active())
        return box

    # -- STT engine editor ---
    def _stt_load(self, idx: int) -> None:
        if not (0 <= idx < len(self.cfg.stt_engines)):
            return
        e = self.cfg.stt_engines[idx]
        self.stt_name.set_text(e.name)
        self.stt_type.set_active(["local", "openai"].index(e.type) if e.type in ("local", "openai") else 0)
        self.stt_url.set_text(e.url); self.stt_key.set_text(e.api_key_env)
        if e.type == "local":
            _fill_combo(self.stt_model, ["tiny", "base", "small", "medium", "large-v3"], e.model or self.cfg.model)
        else:
            _fill_combo(self.stt_model, [], e.model)
            self._populate_models(self.stt_model, e.url, e.api_key_env)
        self._stt_idx = idx

    def _stt_commit(self) -> None:
        idx = self._stt_idx
        if not (0 <= idx < len(self.cfg.stt_engines)):
            return
        e = self.cfg.stt_engines[idx]
        new_name = self.stt_name.get_text().strip() or e.name
        e.name = new_name
        e.type = self.stt_type.get_active_text() or "local"
        e.url = self.stt_url.get_text().strip().rstrip("/")
        e.model = _combo_text(self.stt_model)
        e.api_key_env = self.stt_key.get_text().strip()
        if self.stt_combo.get_active_text() != new_name:
            self.stt_combo.remove(idx); self.stt_combo.insert_text(idx, new_name); self.stt_combo.set_active(idx)

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

    def _transcriber_for(self, engine):
        """A local Transcriber for the engine, loading on demand (cached)."""
        if not engine.is_local:
            return None
        model = engine.model or self.cfg.model
        active = self.cfg.active_stt
        if (self.daemon and self.daemon.transcriber and active.is_local
                and (active.model or self.cfg.model) == model):
            return self.daemon.transcriber
        key = (model, self.cfg.device, self.cfg.compute_type)
        if key not in self._tr_cache:
            from .transcribe import Transcriber
            logbuffer.log(f"Loading local model '{model}' ({self.cfg.device}) for test/benchmark…")
            self._tr_cache[key] = Transcriber(model, self.cfg.device, self.cfg.compute_type, self.cfg.beam_size)
        return self._tr_cache[key]

    def _run_stt_test(self, engine):
        from .recorder import Recording, detect_recorder
        try:
            rec = Recording(detect_recorder(self.cfg.recorder), self.cfg.mic)
            time.sleep(4.0)
            wav = rec.stop()
            GLib.idle_add(self.stt_result.set_markup, "<i>Transcribing…</i>")
            tr = self._transcriber_for(engine)
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
        self.llm_name.set_text(e.name)
        self.llm_type.set_active(["local", "cloud"].index(e.type) if e.type in ("local", "cloud") else 1)
        self.llm_url.set_text(e.url)
        self.llm_key.set_text(e.api_key_env); self.llm_temp.set_text(str(e.temperature))
        _fill_combo(self.llm_model, [], e.model)
        self._populate_models(self.llm_model, e.url, e.api_key_env)
        self._llm_idx = idx

    def _llm_commit(self) -> None:
        idx = self._llm_idx
        if not (0 <= idx < len(self.cfg.llm_engines)):
            return
        e = self.cfg.llm_engines[idx]
        new_name = self.llm_name.get_text().strip() or e.name
        e.name = new_name
        e.type = self.llm_type.get_active_text() or "cloud"
        e.url = self.llm_url.get_text().strip().rstrip("/")
        e.model = _combo_text(self.llm_model)
        e.api_key_env = self.llm_key.get_text().strip()
        if self.llm_combo.get_active_text() != new_name:
            self.llm_combo.remove(idx); self.llm_combo.insert_text(idx, new_name); self.llm_combo.set_active(idx)
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

    def _stt_type_changed(self, _c) -> None:
        if self.stt_type.get_active_text() == "local":
            _fill_combo(self.stt_model, ["tiny", "base", "small", "medium", "large-v3"], _combo_text(self.stt_model))
        else:
            self._schedule_models("stt")

    # -- model dropdowns (fetched from {url}/models) ---
    def _populate_models(self, combo, url: str, key_env: str) -> None:
        def work():
            models = stt.list_models(url, key_env) if url else []

            def apply():
                cur = _combo_text(combo)
                _fill_combo(combo, models, cur)
                return False
            GLib.idle_add(apply)
        threading.Thread(target=work, daemon=True).start()

    def _schedule_models(self, which: str) -> None:
        attr = f"_mt_{which}"
        old = getattr(self, attr, 0)
        if old:
            GLib.source_remove(old)

        def fire():
            setattr(self, attr, 0)
            if which == "stt" and self.stt_type.get_active_text() != "local":
                self._populate_models(self.stt_model, self.stt_url.get_text().strip(),
                                      self.stt_key.get_text().strip())
            elif which == "llm":
                self._populate_models(self.llm_model, self.llm_url.get_text().strip(),
                                      self.llm_key.get_text().strip())
            return False
        setattr(self, attr, GLib.timeout_add(700, fire))

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

    # -- key binding ("Set" button captures the next keypress) ---
    def _key_field(self, page: Gtk.Box, label: str, value: str, placeholder: str = "", width: int = 150) -> Gtk.Entry:
        row = Gtk.Box(spacing=10); row.set_margin_top(3); row.set_margin_bottom(3)
        lbl = Gtk.Label(label=label, xalign=0.0); lbl.set_size_request(width, -1)
        row.pack_start(lbl, False, False, 0)
        entry = Gtk.Entry(); entry.set_text(value); entry.set_hexpand(True)
        if placeholder:
            entry.set_placeholder_text(placeholder)
        row.pack_start(entry, True, True, 0)
        btn = Gtk.Button(label="Set")
        btn.connect("clicked", lambda _b, e=entry: self._bind_key(e))
        row.pack_start(btn, False, False, 0)
        page.pack_start(row, False, False, 0)
        return entry

    def _bind_key(self, entry: Gtk.Entry) -> None:
        self._bind_entry = entry
        self._bind_pressed = []
        entry.set_text("")
        entry.set_placeholder_text("press the key to bind…")

    def _on_bind_press(self, _w, event) -> bool:
        if self._bind_entry is None:
            return False
        tok = _keyval_token(event.keyval)
        if tok and tok not in self._bind_pressed:
            self._bind_pressed.append(tok)
        return True  # swallow while binding

    def _on_bind_release(self, _w, event) -> bool:
        if self._bind_entry is None:
            return False
        combo = _format_combo(self._bind_pressed)
        if combo:
            self._bind_entry.set_text(combo)
        self._bind_entry = None
        return True

    # ===== Input ============================================================
    def _build_input(self, page: Gtk.Box) -> None:
        self.in_mode = _labeled(page, "Input mode", _combo(["modifiers", "hotkeys"], self.cfg.input_mode))
        self.in_ptt = Gtk.Switch(); self.in_ptt.set_active(self.cfg.push_to_talk); self.in_ptt.set_halign(Gtk.Align.START)
        _labeled(page, "Push-to-talk", self.in_ptt)
        self.in_start = self._key_field(page, "Start", self.cfg.key_start)
        self.in_stop = self._key_field(page, "Stop + paste", self.cfg.key_stop)
        self.in_send = self._key_field(page, "Stop + paste + Enter", self.cfg.key_send)
        self.in_cancel = self._key_field(page, "Cancel", self.cfg.key_cancel)
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

    # ===== Benchmark ========================================================
    def _build_benchmark(self, page: Gtk.Box) -> None:
        page.pack_start(Gtk.Label(
            label="Benchmark all your STT engines against a reference clip "
                  "(add presets for each model you want compared).",
            xalign=0.0, wrap=True), False, False, 0)

        wavf = Gtk.FileChooserButton(title="WAV file", action=Gtk.FileChooserAction.OPEN)
        fa = Gtk.FileFilter(); fa.set_name("Audio (.wav)"); fa.add_pattern("*.wav"); wavf.add_filter(fa)
        self.bench_wav = _labeled(page, "Audio (.wav)", wavf)
        reff = Gtk.FileChooserButton(title="Reference transcript", action=Gtk.FileChooserAction.OPEN)
        ft = Gtk.FileFilter(); ft.set_name("Text (.txt)"); ft.add_pattern("*.txt"); reff.add_filter(ft)
        self.bench_ref = _labeled(page, "Reference (.txt)", reff)

        run = Gtk.Button(label="Run benchmark"); run.connect("clicked", self._run_bench)
        run.set_halign(Gtk.Align.START)
        page.pack_start(run, False, False, 6)

        self.bench_store = Gtk.ListStore(str, str, str, str, str)
        tree = Gtk.TreeView(model=self.bench_store)
        for title, i, expand in [("Engine", 0, False), ("Model", 1, False),
                                 ("Time (s)", 2, False), ("Accuracy", 3, False), ("Output", 4, True)]:
            r = Gtk.CellRendererText()
            if i == 4:
                r.set_property("ellipsize", Pango.EllipsizeMode.END)
            col = Gtk.TreeViewColumn(title, r, text=i); col.set_resizable(True)
            col.set_expand(expand)
            tree.append_column(col)
        sw = Gtk.ScrolledWindow(); sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.add(tree); page.pack_start(sw, True, True, 4)

        self.bench_summary = Gtk.Label(xalign=0.0); self.bench_summary.set_line_wrap(True)
        page.pack_start(self.bench_summary, False, False, 4)

    def _run_bench(self, _b) -> None:
        wav = self.bench_wav.get_filename()
        refp = self.bench_ref.get_filename()
        if not wav or not refp:
            self._error("Pick a .wav file and a matching reference .txt file.")
            return
        reference = Path(refp).read_text(errors="replace")
        self.bench_store.clear()
        self.bench_summary.set_markup("<i>Running… (local models load on first use)</i>")
        self._stt_commit()
        engines = list(self.cfg.stt_engines)

        def work():
            def prog(row):
                GLib.idle_add(self._bench_add_row, row)
            rows = benchmark.run(engines, Path(wav), reference, language=self.cfg.language,
                                 get_local_transcriber=self._transcriber_for, progress=prog)
            GLib.idle_add(self._bench_done, rows)
        threading.Thread(target=work, daemon=True).start()

    def _bench_add_row(self, row) -> bool:
        acc = f"{row.accuracy:.1f}%" if row.ok else "—"
        out = row.text if row.ok else f"⚠ {row.error}"
        self.bench_store.append([row.engine, row.model, f"{row.seconds:.2f}", acc, out])
        return False

    def _bench_done(self, rows) -> bool:
        fastest, acc = benchmark.best(rows)
        if not fastest:
            self.bench_summary.set_markup('<span foreground="#ff3b30">All engines failed — check the Log tab.</span>')
            return False
        self.bench_summary.set_markup(
            f"<b>Fastest:</b> {GLib.markup_escape_text(fastest.engine)} ({fastest.seconds:.2f}s)"
            f"     ·     <b>Most accurate:</b> {GLib.markup_escape_text(acc.engine)} ({acc.accuracy:.1f}%)")
        return False

    # ===== Log ==============================================================
    def _build_log(self, page: Gtk.Box) -> None:
        sw = Gtk.ScrolledWindow(); sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.log_view = Gtk.TextView()
        self.log_view.set_editable(False); self.log_view.set_cursor_visible(False)
        self.log_view.set_monospace(True); self.log_view.set_left_margin(6); self.log_view.set_top_margin(6)
        sw.add(self.log_view)
        page.pack_start(sw, True, True, 0)

        bar = Gtk.Box(spacing=8); bar.set_margin_top(6)
        self.log_autoscroll = Gtk.CheckButton(label="Auto-scroll"); self.log_autoscroll.set_active(True)
        bar.pack_start(self.log_autoscroll, False, False, 0)
        clear = Gtk.Button(label="Clear"); clear.connect("clicked", lambda _b: (logbuffer.clear(), self._log_refresh()))
        copy = Gtk.Button(label="Copy"); copy.connect("clicked", lambda _b: self._log_copy())
        bar.pack_end(clear, False, False, 0); bar.pack_end(copy, False, False, 0)
        page.pack_start(bar, False, False, 0)

        self._log_last = None
        self._log_refresh()
        self._log_timer = GLib.timeout_add(1000, self._log_tick)

    def _log_tick(self) -> bool:
        self._log_refresh()
        return True

    def _log_refresh(self) -> None:
        text = "\n".join(logbuffer.lines())
        if text == getattr(self, "_log_last", None):
            return
        self._log_last = text
        buf = self.log_view.get_buffer()
        buf.set_text(text)
        if self.log_autoscroll.get_active():
            self.log_view.scroll_to_iter(buf.get_end_iter(), 0.0, False, 0, 0)

    def _log_copy(self) -> None:
        cb = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        cb.set_text("\n".join(logbuffer.lines()), -1)

    def _cleanup(self) -> None:
        self._stop_meter()
        t = getattr(self, "_log_timer", 0)
        if t:
            GLib.source_remove(t)
            self._log_timer = 0

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
            c.device = self.stt_device.get_active_text() or "auto"
            c.compute_type = self.stt_compute.get_active_text() or "auto"
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
                self._cleanup()
                os.execv(sys.executable, [sys.executable, "-m", "blitztext", "tray"])
            return
        self._cleanup()
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

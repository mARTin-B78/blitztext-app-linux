"""GTK settings: dropdown + editor managers for prompt presets and engines.

Tabs:
  Presets  - prompt presets (select from a dropdown, edit, add, delete)
  Engines  - STT and LLM engine presets with online/offline status + STT test
  Input    - input scheme, keys, quality gate
  General  - mic (with live level meter), output, language, notifications, autostart
  Benchmark- compare STT engines against a reference clip
  Log      - runtime log output
  About    - version, source, changelog, and license
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

from . import __version__, audio, autostart, benchmark, llm, logbuffer, stt, wakeword_bench  # noqa: E402
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


def _labeled(parent: Gtk.Box, label: str, widget: Gtk.Widget, width: int = 130, tooltip: str = "") -> Gtk.Widget:
    row = Gtk.Box(spacing=10)
    row.set_margin_top(3); row.set_margin_bottom(3)
    lbl = Gtk.Label(label=label, xalign=0.0); lbl.set_size_request(width, -1)
    
    # ATK Accessibility linking
    if hasattr(lbl, "set_mnemonic_widget"):
        lbl.set_mnemonic_widget(widget)
    atk = widget.get_accessible()
    if atk and label:
        atk.set_name(label.replace("_", ""))
    if tooltip:
        widget.set_tooltip_text(tooltip)
        lbl.set_tooltip_text(tooltip)
        if atk:
            atk.set_description(tooltip)
            
    row.pack_start(lbl, False, False, 0)
    row.pack_start(widget, True, True, 0)
    parent.pack_start(row, False, False, 0)
    return widget


def _switch_row(parent: Gtk.Box, label: str, switch: Gtk.Switch, description: str = "",
                width: int = 130) -> Gtk.Switch:
    """A settings row: [label] [grey description ……………] [switch, far right].

    The description tells the user what the switch does without hovering.
    """
    row = Gtk.Box(spacing=10)
    row.set_margin_top(3); row.set_margin_bottom(3)

    lbl = Gtk.Label(label=label, xalign=0.0); lbl.set_size_request(width, -1)
    row.pack_start(lbl, False, False, 0)

    desc = Gtk.Label(label=description, xalign=0.0)
    desc.set_line_wrap(True)
    desc.get_style_context().add_class("dim-label")
    row.pack_start(desc, True, True, 0)

    switch.set_halign(Gtk.Align.END)
    switch.set_valign(Gtk.Align.CENTER)
    row.pack_end(switch, False, False, 0)

    # ATK accessibility + tooltips
    if hasattr(lbl, "set_mnemonic_widget"):
        lbl.set_mnemonic_widget(switch)
    atk = switch.get_accessible()
    if atk and label:
        atk.set_name(label.replace("_", ""))
        if description:
            atk.set_description(description)
    if description:
        switch.set_tooltip_text(description)
        lbl.set_tooltip_text(description)
        desc.set_tooltip_text(description)

    parent.pack_start(row, False, False, 0)
    return switch


def _infobox(parent: Gtk.Box, text: str) -> Gtk.Box:
    """A plain-language help box at the top of a tab (read by screen readers)."""
    box = Gtk.Box(spacing=8)
    box.set_margin_top(2); box.set_margin_bottom(10)
    icon = Gtk.Image.new_from_icon_name("dialog-information-symbolic", Gtk.IconSize.BUTTON)
    icon.set_valign(Gtk.Align.START)
    box.pack_start(icon, False, False, 0)
    lbl = Gtk.Label(label=text, xalign=0.0)
    lbl.set_line_wrap(True); lbl.set_xalign(0.0); lbl.set_max_width_chars(72)
    box.pack_start(lbl, True, True, 0)
    acc = box.get_accessible()
    if acc:
        acc.set_name("Information")
        acc.set_description(text)
    parent.pack_start(box, False, False, 0)
    return box


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


class MultiPicker(ModelPicker):
    """Like ModelPicker, but picking a row APPENDS to a comma-separated list —
    for fields that hold several values (e.g. the benchmark's voices)."""

    def _activated(self, _lb, row) -> None:
        val = row.get_child().get_text()
        cur = [v.strip() for v in self.entry.get_text().split(",") if v.strip()]
        if val and val not in cur:
            cur.append(val)
        self.entry.set_text(", ".join(cur))
        self.pop.popdown()


def _model_combo(placeholder="") -> ModelPicker:
    return ModelPicker(placeholder)


def _combo_text(c: ModelPicker) -> str:
    return c.get_text()


def _fill_combo(combo: ModelPicker, options, current: str) -> None:
    combo.set_models(list(options))
    combo.set_text(current or "")


def _url_field(parent: Gtk.Box, label: str, placeholder: str, on_reload,
               dot: Gtk.Label | None = None, width: int = 130) -> Gtk.Entry:
    row = Gtk.Box(spacing=10); row.set_margin_top(3); row.set_margin_bottom(3)
    lbl = Gtk.Label(label=label, xalign=0.0); lbl.set_size_request(width, -1)
    row.pack_start(lbl, False, False, 0)
    if dot is not None:
        row.pack_start(dot, False, False, 0)   # connection dot beside the field (left), like Engines
    e = Gtk.Entry(); e.set_hexpand(True)
    if placeholder:
        e.set_placeholder_text(placeholder)
        
    lbl.set_mnemonic_widget(e)
    atk = e.get_accessible()
    if atk and label:
        atk.set_name(label)
        
    row.pack_start(e, True, True, 0)
    btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
    btn.set_tooltip_text("Load models from this URL")
    if btn.get_accessible():
        btn.get_accessible().set_name("Refresh models")
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


def _read_first(paths: list[Path], fallback: str = "Not available in this install.") -> str:
    for path in paths:
        try:
            if path.exists():
                return path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
    return fallback


def _app_paths() -> dict[str, list[Path]]:
    pkg_dir = Path(__file__).resolve().parent
    linux_dir = pkg_dir.parent
    repo_dir = linux_dir.parent
    return {
        "changelog": [linux_dir / "CHANGELOG.md", Path("/opt/blitztext/CHANGELOG.md")],
        "license": [repo_dir / "LICENSE", Path("/usr/share/doc/blitztext/copyright")],
    }


def _text_panel(text: str, *, monospace: bool = True, height: int = 180) -> Gtk.ScrolledWindow:
    sw = Gtk.ScrolledWindow()
    sw.set_min_content_height(height)
    sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    view = Gtk.TextView()
    view.set_editable(False)
    view.set_cursor_visible(False)
    view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    view.set_left_margin(8)
    view.set_right_margin(8)
    view.set_top_margin(8)
    view.set_bottom_margin(8)
    view.set_monospace(monospace)
    view.get_buffer().set_text(text)
    sw.add(view)
    return sw


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
        # Build each tab lazily on first view so the dialog opens instantly. The
        # heavy bits are the Gtk.FileChooserButton pickers in Input/Benchmark
        # (~0.2s each to construct); deferring them until you visit that tab keeps
        # the initial open near-instant. _collect() force-builds any unvisited tab
        # before saving, so no field is ever missed.
        self._pending_tabs: dict = {}
        for title, builder in (("Presets", self._build_presets),
                               ("Engines", self._build_engines),
                               ("Input", self._build_input),
                               ("General", self._build_general),
                               ("Benchmark", self._build_benchmark),
                               ("Log", self._build_log),
                               ("About", self._build_about)):
            self._pending_tabs[_page(nb, title)] = builder
        self._build_tab(nb.get_nth_page(0))   # the visible tab, eagerly
        nb.connect("switch-page", lambda _nb, page, _n: self._build_tab(page))

        self._bind_entry = None
        self._bind_pressed: list[str] = []
        self.dlg.connect("key-press-event", self._on_bind_press)
        self.dlg.connect("key-release-event", self._on_bind_release)
        self.dlg.connect("response", self._on_response)
        self.dlg.connect("destroy", lambda *_: self._cleanup())

    def _build_tab(self, page: Gtk.Box) -> None:
        """Build a notebook tab's contents the first time it's shown (lazy)."""
        builder = self._pending_tabs.pop(page, None)
        if builder is not None:
            builder(page)
            page.show_all()   # the dialog may already be on-screen

    def _force_build_tabs(self) -> None:
        """Build any not-yet-visited tabs so _collect() sees every field."""
        for page in list(self._pending_tabs):
            self._build_tab(page)

    # ===== Presets ==========================================================
    def _build_presets(self, page: Gtk.Box) -> None:
        _infobox(page, "Presets are your dictation actions. Pick one to edit it, or add your "
                       "own. A preset can simply type what you say, or rewrite it first "
                       "(for example into a polished email). Trigger it by speaking its "
                       "keyword, or with an optional keyboard shortcut.")
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
        self.wf_name = _labeled(form, "Name", _entry(placeholder="Preset name"),
                                tooltip="A short name for this action, shown in the main panel.")
        self.wf_icon = _labeled(form, "Icon (emoji)", _entry(placeholder="⚡  (shown in the ‘matched preset’ notification)"),
                                tooltip="An emoji shown next to this preset when a voice command matches it — "
                                        "give each preset a distinct one so you can tell at a glance which fired.")
        self.wf_desc = _labeled(form, "Description", _entry(placeholder="Short description shown in the panel"),
                                tooltip="One line explaining what this preset does.")
        self.wf_keywords = _labeled(form, "Keywords (comma)", _entry(placeholder="nicer email, bessere email"),
                                    tooltip="Spoken trigger words. Say one at the start or end of your speech to use this preset.")
        self.wf_hotkey = self._key_field(form, "Hotkey (optional)", "", placeholder="click Set, or e.g. <ctrl>+<alt>+e", width=130)
        self.wf_mode = _labeled(form, "Mode", _combo(["transcribe", "rewrite", "stream"]),
                                tooltip="‘transcribe’ types your words as-is. ‘rewrite’ sends them to the language model first. ‘stream’ shows live text from a realtime engine.")
        self.wf_model = _labeled(form, "LLM model (opt.)", _entry(placeholder="blank = use the active LLM engine's model"),
                                 tooltip="Override the language model just for this preset. Leave blank to use the active LLM engine.")
        self.wf_temp = _labeled(form, "Temperature (opt.)", _entry(placeholder="blank = engine default (e.g. 0.3)"),
                                tooltip="Creativity of the rewrite, 0–1. Lower is more predictable. Blank uses the engine default.")

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
        self.wf_icon.set_text(wf.icon or "")
        self.wf_desc.set_text(wf.description)
        self.wf_keywords.set_text(", ".join(wf.keywords))
        self.wf_hotkey.set_text(wf.hotkey)
        self.wf_mode.set_active(["transcribe", "rewrite", "stream"].index(wf.mode) if wf.mode in ("transcribe", "rewrite", "stream") else 0)
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
        wf.icon = self.wf_icon.get_text().strip() or "⚡"
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
        _infobox(page, "Engines do the work. The speech-to-text engine turns your voice into "
                       "text; the language model rewrites it. Each can run locally on this "
                       "computer or on a server you enter. A green dot means it is reachable, "
                       "red means offline. Use Test to try the speech engine.")
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
        for label, cb in (("+ Add", self._stt_add), ("+ Stream", self._stt_add_stream),
                          ("Delete", self._stt_delete), ("Test", self._stt_test),
                          ("Refresh", lambda _b: self._refresh_status())):
            b = Gtk.Button(label=label); b.connect("clicked", cb); bar.pack_start(b, False, False, 0)
        box.pack_start(bar, False, False, 2)

        form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL); box.pack_start(form, False, False, 2)
        self.stt_name = _labeled(form, "Name", _entry(placeholder="e.g. faster-whisper GPU"))
        self.stt_type = _labeled(form, "Type", _combo(["local", "openai", "riva_realtime"]))
        self.stt_url = _url_field(form, "URL", "http://localhost:8010/v1  ·  realtime: http://localhost:8006/v1",
                                  lambda: self._populate_models(self.stt_model, self.stt_url.get_text().strip(), self.stt_key.get_text().strip()))
        self.stt_model = _labeled(form, "Model", _model_combo("blank = server default  ·  tiny/base/small… for local"))
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
        self.stt_type.set_active(["local", "openai", "riva_realtime"].index(e.type) if e.type in ("local", "openai", "riva_realtime") else 0)
        self.stt_url.set_text(e.url); self.stt_key.set_text(e.api_key_env)
        if e.type == "local":
            _fill_combo(self.stt_model, ["tiny", "base", "small", "medium", "large-v3"], e.model or self.cfg.model)
        elif e.type == "openai":
            _fill_combo(self.stt_model, [], e.model)
            self._populate_models(self.stt_model, e.url, e.api_key_env)
        else:
            _fill_combo(self.stt_model, [], e.model)
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

    def _stt_add_stream(self, _b):
        self._stt_commit()
        e = STTEngine("Nemotron ASR Streaming", "riva_realtime", "http://127.0.0.1:8006/v1", "")
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
        if e.is_streaming:
            self.stt_result.set_markup("<i>Streaming engines are live-only. Use a preset with mode = stream.</i>")
            return
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
        typ = self.stt_type.get_active_text()
        if typ == "local":
            _fill_combo(self.stt_model, ["tiny", "base", "small", "medium", "large-v3"], _combo_text(self.stt_model))
        elif typ == "openai":
            self._schedule_models("stt")
        else:
            _fill_combo(self.stt_model, [], _combo_text(self.stt_model))

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
            if which == "stt" and self.stt_type.get_active_text() == "openai":
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

    def _probe_dot(self, dot: Gtk.Label, uri: str, fallback_port: int) -> None:
        """Colour a connection dot by TCP reachability of a host:port URL (threaded).

        Green = something is listening at the address, red = configured but
        unreachable, grey = empty. Deliberately lightweight — the per-tab Test /
        Connect buttons do the deeper, protocol-aware checks.
        """
        uri = (uri or "").strip()
        if not uri:
            dot.set_markup(_dot(GREY))
            return
        from urllib.parse import urlparse
        p = urlparse(uri if "://" in uri else "//" + uri)
        host = p.hostname or "127.0.0.1"
        port = p.port or (443 if p.scheme == "https" else fallback_port)

        def work():
            import socket
            try:
                with socket.create_connection((host, port), timeout=2.0):
                    ok = True
            except OSError:
                ok = False
            GLib.idle_add(dot.set_markup, _dot(GREEN if ok else RED))
        threading.Thread(target=work, daemon=True).start()

    def _on_ww_uri_leave(self, *_a) -> bool:
        self._probe_dot(self.ww_dot, self.ww_uri.get_text(), 10400)
        return False

    def _on_tts_url_leave(self, *_a) -> bool:
        self._probe_dot(self.tts_dot, self.wwb_url.get_text(), 80)
        return False

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
        _infobox(page, "Choose how you start and stop dictating. With the default "
                       "‘modifiers’ mode: hold Ctrl and the Windows key to talk, then press "
                       "Ctrl to stop and paste. Below you can tune the noise filter, set up "
                       "hands-free wakeword, and pick sounds that confirm start and stop.")
        LW = 175  # uniform label width for all rows in this tab
        self.in_mode = _labeled(page, "Input mode", _combo(["modifiers", "hotkeys"], self.cfg.input_mode),
                                width=LW,
                                tooltip="’modifiers’: hold/press the keys below. ‘hotkeys’: each preset has its own shortcut combo.")
        self.in_ptt = Gtk.Switch(); self.in_ptt.set_active(self.cfg.push_to_talk); self.in_ptt.set_halign(Gtk.Align.START)
        _labeled(page, "Push-to-talk", self.in_ptt, width=LW)
        self.in_start = self._key_field(page, "Start", self.cfg.key_start, width=LW)
        self.in_stop = self._key_field(page, "Stop + paste", self.cfg.key_stop, width=LW)
        self.in_send = self._key_field(page, "Stop + paste + Enter", self.cfg.key_send, width=LW)
        self.in_cancel = self._key_field(page, "Cancel", self.cfg.key_cancel, width=LW)
        page.pack_start(Gtk.Separator(), False, False, 8)
        page.pack_start(Gtk.Label(label="Quality gate", xalign=0.0), False, False, 2)
        self.q_min = _labeled(page, "Min seconds", _entry(self.cfg.min_speech_seconds), width=LW,
                              tooltip="Minimum audio length. Shorter clips are ignored.")
        self.q_rms = _labeled(page, "Silence RMS", _entry(self.cfg.silence_rms), width=LW,
                              tooltip="Microphone volume threshold to ignore background noise.")
        self.q_halluc = Gtk.Switch(); self.q_halluc.set_active(self.cfg.reject_hallucinations); self.q_halluc.set_halign(Gtk.Align.START)
        _labeled(page, "Reject hallucinations", self.q_halluc, width=LW,
                 tooltip="Automatically drop STT ghost outputs like ‘Thank you.’ or ‘Bye.’")
        self.q_strip = Gtk.Switch(); self.q_strip.set_active(self.cfg.strip_trailing_punctuation); self.q_strip.set_halign(Gtk.Align.START)
        _labeled(page, "Strip trailing punctuation", self.q_strip, width=LW,
                 tooltip="Remove ending periods from pasted text, useful for code inserts.")
        page.pack_start(Gtk.Separator(), False, False, 8)
        page.pack_start(Gtk.Label(label="Hands-free (Wakeword)", xalign=0.0), False, False, 2)
        self.ww_enabled = Gtk.Switch(); self.ww_enabled.set_active(self.cfg.wakeword_enabled); self.ww_enabled.set_halign(Gtk.Align.START)
        _labeled(page, "Enable wakeword", self.ww_enabled, width=LW)
        self.ww_dot = Gtk.Label(); self.ww_dot.set_markup(_dot(GREY))
        self.ww_dot.set_tooltip_text("Wakeword (Wyoming / openWakeWord) server: "
                                     "green = reachable, red = unreachable")
        self.ww_uri = _url_field(page, "Wakeword engine", "tcp://127.0.0.1:10400",
                                 self._ww_load, dot=self.ww_dot, width=LW)
        self.ww_uri.set_text(self.cfg.wakeword_uri)
        self.ww_uri.connect("focus-out-event", self._on_ww_uri_leave)
        self._probe_dot(self.ww_dot, self.cfg.wakeword_uri, 10400)
        self.ww_model = _labeled(page, "Model name", _model_combo("Search models…"), width=LW)
        _fill_combo(self.ww_model, [], self.cfg.wakeword_model)

        self.ww_mic_level = Gtk.LevelBar(); self.ww_mic_level.set_min_value(0); self.ww_mic_level.set_max_value(1)
        _labeled(page, "Input level", self.ww_mic_level, width=LW)

        self.ww_test_btn = Gtk.Button(label="Test Wakeword"); self.ww_test_btn.set_halign(Gtk.Align.START)
        self.ww_test_btn.connect("clicked", self._ww_test)
        self.ww_test_lbl = Gtk.Label(label=""); self.ww_test_lbl.set_xalign(0.0)
        box = Gtk.Box(spacing=10); box.pack_start(self.ww_test_btn, False, False, 0); box.pack_start(self.ww_test_lbl, False, False, 0)
        _labeled(page, "", box, width=LW)

        self.ww_silence = _labeled(page, "Silence to stop (s)", _entry(self.cfg.wakeword_silence_seconds), width=LW,
                                   tooltip="After the wakeword starts recording, end it this many seconds "
                                           "after you stop speaking. Hands-free auto-stop — the wakeword "
                                           "can’t be released like a key. Default 2.0.")

        self.cancel_keywords = _labeled(
            page, "Cancel words (comma)",
            _entry(", ".join(self.cfg.cancel_keywords), placeholder="abbrechen, cancel"),
            width=LW,
            tooltip="Say one of these at the start or end of a clip to DISCARD it — "
                    "nothing is transcribed onward, routed, rewritten, or typed. "
                    "Rescues an accidentally triggered dictation. Empty = off.")

        self.send_keywords = _labeled(
            page, "Send words (comma)",
            _entry(", ".join(self.cfg.send_keywords), placeholder="computer send, computer abschicken"),
            width=LW,
            tooltip="Say one of these at the start or end of a clip to SEND it: the word is "
                    "stripped and the rest is typed AND submitted with Enter (spoken "
                    "’stop+paste+Enter’). Because it presses Enter, use a distinctive "
                    "multi-word phrase (e.g. your wakeword + ‘send’). Empty = off.")

        self.ww_snd_detected = self._sound_field(
            page, "Sound: detected", self.cfg.wakeword_sound_detected,
            "HANDS-FREE ONLY. Plays the instant the wake word is recognised and recording starts "
            "— your ‘speak now’ cue. (Keyboard/hotkey dictation ignores this and uses ‘Play before’.)",
            empty_note="Leave empty for no sound. These wakeword cues are independent of the "
                       "’Play audio cues’ switch below.",
            clear_tip="Clear — no sound", width=LW)
        self.ww_snd_done = self._sound_field(
            page, "Sound: captured", self.cfg.wakeword_sound_done,
            "HANDS-FREE ONLY. Plays when your spoken command is captured and recording stops "
            "(on silence or stop). (Keyboard/hotkey dictation ignores this and uses ‘Play after’.)",
            empty_note="Leave empty for no sound.",
            clear_tip="Clear — no sound", width=LW)

        page.pack_start(Gtk.Separator(), False, False, 8)
        page.pack_start(Gtk.Label(label="Audio cues (manual dictation)", xalign=0.0), False, False, 2)
        self.snd_enabled = Gtk.Switch(); self.snd_enabled.set_active(self.cfg.sounds_enabled); self.snd_enabled.set_halign(Gtk.Align.START)
        _labeled(page, "Play audio cues", self.snd_enabled, width=LW,
                 tooltip="On/off for the MANUAL start/stop chimes below (keyboard/hotkey dictation). "
                         "The hands-free wakeword sounds above are separate and always play when set.")
        self.snd_before = self._sound_field(
            page, "Play before", self.cfg.sound_before,
            "MANUAL (keyboard/hotkey) dictation only. Plays when recording starts. "
            "(Hands-free sessions use ‘Sound: detected’ instead.)", width=LW)
        self.snd_after = self._sound_field(
            page, "Play after", self.cfg.sound_after,
            "MANUAL (keyboard/hotkey) dictation only. Plays when recording stops "
            "(paste, paste+Enter, or auto-stop on silence). (Hands-free uses ‘Sound: captured’ instead.)",
            width=LW)

    def _sound_field(self, page: Gtk.Box, label: str, value: str, tooltip: str = "",
                     empty_note: str = "Leave empty to use the built-in system sound.",
                     clear_tip: str = "Clear — use the built-in system sound",
                     width: int = 150) -> Gtk.FileChooserButton:
        row = Gtk.Box(spacing=10); row.set_margin_top(3); row.set_margin_bottom(3)
        lbl = Gtk.Label(label=label, xalign=0.0); lbl.set_size_request(width, -1)
        if tooltip:
            lbl.set_tooltip_text(tooltip)
        row.pack_start(lbl, False, False, 0)
        chooser = Gtk.FileChooserButton(title=label, action=Gtk.FileChooserAction.OPEN)
        af = Gtk.FileFilter(); af.set_name("Audio")
        for pat in ("*.wav", "*.oga", "*.ogg", "*.flac"):
            af.add_pattern(pat)
        chooser.add_filter(af)
        if value:
            chooser.set_filename(value)
        chooser.set_hexpand(True)
        if tooltip:
            chooser.set_tooltip_text(f"{tooltip} {empty_note}")
        row.pack_start(chooser, True, True, 0)
        play = Gtk.Button.new_from_icon_name("media-playback-start-symbolic", Gtk.IconSize.BUTTON)
        play.set_tooltip_text("Play this sound now")
        play.connect("clicked", lambda _b, c=chooser: self._play_sound_file(c.get_filename()))
        row.pack_start(play, False, False, 0)
        clr = Gtk.Button.new_from_icon_name("edit-clear-symbolic", Gtk.IconSize.BUTTON)
        clr.set_tooltip_text(clear_tip)
        clr.connect("clicked", lambda _b, c=chooser: c.unselect_all())
        row.pack_start(clr, False, False, 0)
        page.pack_start(row, False, False, 0)
        return chooser

    def _play_sound_file(self, path) -> None:
        from . import sound
        if path:
            sound.play(path)

    # ===== General ==========================================================
    def _build_general(self, page: Gtk.Box) -> None:
        _infobox(page, "General options: choose your microphone and watch its level bar move "
                       "when you speak, set how the text is delivered, the spoken language, "
                       "desktop notifications, and whether Blitztext starts automatically "
                       "when you log in.")
        self._mics = audio.list_mics()
        names = [label for _, label in self._mics]
        cur = next((lbl for nm, lbl in self._mics if nm == self.cfg.mic), names[0])
        self.gen_mic = _labeled(page, "Microphone", _combo(names, cur),
                                tooltip="Which microphone Blitztext records from.")

        self.mic_level = Gtk.LevelBar(); self.mic_level.set_min_value(0); self.mic_level.set_max_value(1)
        _labeled(page, "Input level", self.mic_level,
                 tooltip="Live microphone level. The bar should move when you speak.")
        self.gen_mic.connect("changed", lambda _c: self._restart_meter())

        self.gen_output = _labeled(page, "Output", _combo(["type", "paste"], self.cfg.output),
                                   tooltip="‘type’ types the text key by key. ‘paste’ copies it and presses Ctrl+V (faster for long text).")
        self.gen_lang = _labeled(page, "Language hint", _entry(self.cfg.language, placeholder="de, en, …   (blank = autodetect)"),
                                 tooltip="Spoken language code (de, en, …). Leave blank to auto-detect.")
        self.gen_notify = Gtk.Switch(); self.gen_notify.set_active(self.cfg.notify)
        _switch_row(page, "Notifications", self.gen_notify,
                    "Desktop pop-ups for recording, transcription, and errors (manual dictation).")
        self.gen_notify_routing = Gtk.Switch(); self.gen_notify_routing.set_active(self.cfg.notify_routing)
        _switch_row(page, "Announce matched preset", self.gen_notify_routing,
                    "After a voice command, show which preset and keyword matched — even hands-free.")
        self.gen_overlay = Gtk.Switch(); self.gen_overlay.set_active(self.cfg.overlay_enabled)
        _switch_row(page, "Visual overlay", self.gen_overlay,
                    "Show a microphone, a live waveform, and the recognised text in a bubble "
                    "at the cursor while you dictate (also gives hands-free sessions feedback).")
        self.gen_boot = Gtk.Switch(); self.gen_boot.set_active(autostart.is_enabled())
        _switch_row(page, "Launch on login", self.gen_boot,
                    "Start Blitztext automatically when you log in.")
        self._start_meter()

    def _selected_mic_name(self) -> str:
        i = self.gen_mic.get_active()
        return self._mics[i][0] if 0 <= i < len(self._mics) else ""

    def _start_meter(self) -> None:
        self._stop_meter()
        def on_level(v):
            GLib.idle_add(self.mic_level.set_value, v)
            if hasattr(self, "ww_mic_level"):
                GLib.idle_add(self.ww_mic_level.set_value, v)
        self._meter = audio.LevelMeter(self._selected_mic_name(), on_level=on_level)
        self._meter.start()

    def _restart_meter(self) -> None:
        self._start_meter()

    def _stop_meter(self) -> None:
        if self._meter is not None:
            self._meter.stop(); self._meter = None

    def _ww_load(self) -> None:
        self._probe_dot(self.ww_dot, self.ww_uri.get_text(), 10400)

        def work():
            import socket, json
            from urllib.parse import urlparse
            uri = self.ww_uri.get_text().strip()
            parsed = urlparse(uri)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or 10400
            try:
                with socket.create_connection((host, port), timeout=2.0) as s:
                    s.sendall(json.dumps({"type": "describe"}).encode() + b"\n")
                    line = b""
                    while not line.endswith(b"\n"):
                        b = s.recv(1)
                        if not b: break
                        line += b
                    info = json.loads(line.decode("utf-8"))
                    payload_len = info.get("data_length", info.get("payload_length", 0))
                    payload = b""
                    while len(payload) < payload_len:
                        chunk = s.recv(payload_len - len(payload))
                        if not chunk: break
                        payload += chunk
                    data = json.loads(payload.decode("utf-8"))
                    models = []
                    for w in data.get("wake", []):
                        for m in w.get("models", []):
                            models.append(m.get("name"))
                    def apply():
                        _fill_combo(self.ww_model, models, models[0] if models else "")
                        self._info("Loaded models successfully.")
                    GLib.idle_add(apply)
            except Exception as e:
                GLib.idle_add(lambda: self._error(f"Failed to load models:\n{e}"))
        threading.Thread(target=work, daemon=True).start()

    def _ww_test(self, _b) -> None:
        self.ww_test_btn.set_sensitive(False)
        self.ww_test_lbl.set_text("Listening for 10s...")
        
        def work():
            from .wakeword import WakewordListener
            import time
            detected = False
            def on_detect():
                nonlocal detected
                detected = True
            
            listener = WakewordListener(
                uri=self.ww_uri.get_text().strip(),
                model=_combo_text(self.ww_model),
                mic=self._selected_mic_name(),
                on_detect=on_detect
            )
            listener.start()
            
            start_t = time.time()
            while time.time() - start_t < 10 and not detected:
                time.sleep(0.1)
                
            listener.stop()
            
            def finish():
                self.ww_test_btn.set_sensitive(True)
                if detected:
                    self.ww_test_lbl.set_markup("<span foreground='green'><b>Detected!</b></span>")
                else:
                    self.ww_test_lbl.set_markup("<span foreground='red'>Timed out.</span>")
            GLib.idle_add(finish)
            
        threading.Thread(target=work, daemon=True).start()

    # ===== Benchmark ========================================================
    def _build_benchmark(self, page: Gtk.Box) -> None:
        _infobox(page, "Compare your speech-to-text engines. Pick a recording (.wav) and a "
                       "text file (.txt) containing exactly what is said, then press Run "
                       "benchmark. The table shows how fast each engine is and how accurate, "
                       "and names the fastest and most accurate. Add an engine preset for "
                       "each model you want in the comparison.")

        wavf = Gtk.FileChooserButton(title="WAV file", action=Gtk.FileChooserAction.OPEN)
        fa = Gtk.FileFilter(); fa.set_name("Audio (.wav)"); fa.add_pattern("*.wav"); wavf.add_filter(fa)
        self.bench_wav = _labeled(page, "Audio (.wav)", wavf)
        reff = Gtk.FileChooserButton(title="Reference transcript", action=Gtk.FileChooserAction.OPEN)
        ft = Gtk.FileFilter(); ft.set_name("Text (.txt)"); ft.add_pattern("*.txt"); reff.add_filter(ft)
        self.bench_ref = _labeled(page, "Reference (.txt)", reff)

        def _on_wav_set(_b):
            fn = wavf.get_filename()
            if not fn: return
            p = Path(fn)
            for ext in (".reference.txt", ".txt"):
                cand = p.with_name(p.stem + ext)
                if cand.exists():
                    reff.set_filename(str(cand))
                    break
        wavf.connect("file-set", _on_wav_set)

        run = Gtk.Button(label="Run benchmark"); run.connect("clicked", self._run_bench)
        run.set_halign(Gtk.Align.START)
        page.pack_start(run, False, False, 6)

        self.bench_store = Gtk.ListStore(str, str, str, str, str, str)
        tree = Gtk.TreeView(model=self.bench_store)
        for title, i, expand in [("Engine", 0, False), ("Model", 1, False), ("Device", 2, False),
                                 ("Time (s)", 3, False), ("Accuracy", 4, False), ("Output", 5, True)]:
            r = Gtk.CellRendererText()
            if i == 5:
                r.set_property("ellipsize", Pango.EllipsizeMode.END)
            col = Gtk.TreeViewColumn(title, r, text=i); col.set_resizable(True)
            col.set_expand(expand)
            tree.append_column(col)
        sw = Gtk.ScrolledWindow(); sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.add(tree); page.pack_start(sw, True, True, 4)

        self.bench_summary = Gtk.Label(xalign=0.0); self.bench_summary.set_line_wrap(True)
        page.pack_start(self.bench_summary, False, False, 4)

        # --- Wakeword benchmark ---------------------------------------------
        page.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 10)
        _infobox(page, "Stress-test the wakeword. It synthesizes short sentences with your "
                       "wakeword spoken in random voices (plus filler with none), streams them to "
                       "your wyoming-openwakeword server, and reports how reliably it fires "
                       "(recall) and whether it false-fires. Speech comes from any OpenAI-compatible "
                       "TTS server (Kokoro, XTTS, OpenAI …) — set its URL, model and voices, then "
                       "Connect to test it.")

        # URL with a ⟳ reload that loads models + voices from the server (like the
        # Engines tab). Set the saved URL after building the field.
        self.tts_dot = Gtk.Label(); self.tts_dot.set_markup(_dot(GREY))
        self.tts_dot.set_tooltip_text("TTS server: green = reachable, red = unreachable")
        self.wwb_url = _url_field(page, "TTS URL", "http://localhost:8880/v1",
                                  self._tts_reload, dot=self.tts_dot)
        self.wwb_url.set_text(self.cfg.tts_url)
        self.wwb_url.connect("focus-out-event", self._on_tts_url_leave)
        self._probe_dot(self.tts_dot, self.cfg.tts_url, 80)
        self.wwb_key = _labeled(
            page, "API key env", _entry(self.cfg.tts_api_key_env, placeholder="(optional, e.g. OPENAI_API_KEY)"),
            tooltip="Name of an environment variable holding a bearer token. Leave empty for "
                    "no-auth local servers. The key itself is never stored in the config.")
        self.wwb_model = _model_combo("press ⟳ to load, or type a model id")
        self.wwb_model.set_text(self.cfg.tts_model)
        _labeled(page, "TTS model", self.wwb_model,
                 tooltip="The TTS model id your endpoint serves (from {url}/models). Required.")
        self.wwb_voices = MultiPicker("press ⟳ to load voices, or type names")
        self.wwb_voices.set_text(", ".join(self.cfg.tts_voices))
        _labeled(page, "Voices (comma)", self.wwb_voices,
                 tooltip="Voices to cycle through at random so the test covers different timbres. "
                         "⟳ fills these from the server; the ▾ dropdown appends one at a time.")

        self.wwb_test_btn = Gtk.Button(label="Connect")
        self.wwb_test_btn.set_tooltip_text("Synthesize a test phrase with the selected model + voice.")
        self.wwb_test_btn.connect("clicked", self._connect_tts)
        self.wwb_test_lbl = Gtk.Label(xalign=0.0); self.wwb_test_lbl.set_line_wrap(True)
        connect_box = Gtk.Box(spacing=10)
        connect_box.pack_start(self.wwb_test_btn, False, False, 0)
        connect_box.pack_start(self.wwb_test_lbl, False, False, 0)
        _labeled(page, "", connect_box)

        adj = Gtk.Adjustment(value=12, lower=1, upper=200, step_increment=1, page_increment=10)
        self.wwb_count = Gtk.SpinButton(adjustment=adj, climb_rate=1, digits=0)
        self.wwb_count.set_halign(Gtk.Align.START); self.wwb_count.set_size_request(90, -1)
        _labeled(page, "Wakeword samples", self.wwb_count,
                 tooltip="How many wakeword utterances to synthesize and test (filler-only "
                         "utterances for false-fire checking are added on top).")

        wrun = Gtk.Button(label="Run wakeword benchmark"); wrun.connect("clicked", self._run_wakeword_bench)
        wrun.set_halign(Gtk.Align.START)
        page.pack_start(wrun, False, False, 6)
        self.wwb_summary = Gtk.Label(xalign=0.0); self.wwb_summary.set_line_wrap(True)
        self.wwb_summary.set_selectable(True)
        page.pack_start(self.wwb_summary, False, False, 4)

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
        self.bench_store.append([row.engine, row.model, row.device, f"{row.seconds:.2f}", acc, out])
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

    # ----- wakeword benchmark ----------------------------------------------
    def _read_tts_fields(self):
        """(url, api_key_env, model, voices) from the Benchmark tab, persisted to cfg."""
        url = self.wwb_url.get_text().strip().rstrip("/")
        key = self.wwb_key.get_text().strip()
        model = self.wwb_model.get_text().strip()
        voices = [v.strip() for v in self.wwb_voices.get_text().split(",") if v.strip()]
        self.cfg.tts_url, self.cfg.tts_api_key_env = url, key
        self.cfg.tts_model, self.cfg.tts_voices = model, voices
        return url, key, model, voices

    def _tts_reload(self) -> None:
        """⟳ — load the model list ({url}/models) and voice list into the dropdowns."""
        url = self.wwb_url.get_text().strip().rstrip("/")
        key = self.wwb_key.get_text().strip()
        if not url:
            self._error("Enter the TTS server URL first (e.g. http://localhost:8880/v1).")
            return
        self._probe_dot(self.tts_dot, url, 80)
        self.wwb_test_lbl.set_markup("<i>Loading models &amp; voices…</i>")

        def work():
            models = stt.list_models(url, key)
            voices = wakeword_bench.list_voices(url, api_key_env=key)

            def apply():
                _fill_combo(self.wwb_model, models, self.wwb_model.get_text())
                self.wwb_voices.set_models(voices)
                if voices and not self.wwb_voices.get_text().strip():
                    self.wwb_voices.set_text(", ".join(voices))   # default: test them all
                colour = "#34c759" if (models or voices) else "#ff9f0a"
                self.wwb_test_lbl.set_markup(
                    f"<span foreground='{colour}'>Loaded {len(models)} models, "
                    f"{len(voices)} voices.</span>")
                return False
            GLib.idle_add(apply)
        threading.Thread(target=work, daemon=True).start()

    def _connect_tts(self, _b) -> None:
        url, key, model, voices = self._read_tts_fields()
        if not url or not model:
            self._error("Enter the TTS URL and model (press ⟳ to load them).")
            return
        self.wwb_test_btn.set_sensitive(False)
        self.wwb_test_lbl.set_markup("<i>Testing synthesis…</i>")
        voice = voices[0] if voices else "alloy"

        def work():
            ok, msg = wakeword_bench.probe(url, model=model, voice=voice, api_key_env=key)
            GLib.idle_add(self._connect_tts_done, ok, msg)
        threading.Thread(target=work, daemon=True).start()

    def _connect_tts_done(self, ok, msg) -> bool:
        self.wwb_test_btn.set_sensitive(True)
        colour = "#34c759" if ok else "#ff3b30"
        self.wwb_test_lbl.set_markup(f"<span foreground='{colour}'>{GLib.markup_escape_text(msg)}</span>")
        return False

    def _run_wakeword_bench(self, _b) -> None:
        url, key, model, voices = self._read_tts_fields()
        count = int(self.wwb_count.get_value())
        if not url:
            self._error("Enter the TTS server URL (e.g. http://localhost:8880/v1).")
            return
        if not model:
            self._error("Set a TTS model id (your endpoint's /audio/speech model).")
            return
        if not voices:
            self._error("Add at least one voice (or press Connect to fetch them).")
            return
        self.wwb_summary.set_markup("<i>Synthesizing and streaming… this talks to your TTS "
                                    "and wyoming-openwakeword servers.</i>")

        def work():
            def prog(done, total, u):
                GLib.idle_add(self._wwbench_progress, done, total, u)
            try:
                res = wakeword_bench.run(
                    tts_url=url, tts_api_key_env=key, tts_model=model, voices=voices,
                    wakeword_model=self.cfg.wakeword_model, wakeword_uri=self.cfg.wakeword_uri,
                    language=self.cfg.language, count=count, progress=prog)
            except Exception as exc:  # noqa: BLE001 - surface setup errors
                GLib.idle_add(self._wwbench_error, str(exc))
                return
            GLib.idle_add(self._wwbench_done, res)
        threading.Thread(target=work, daemon=True).start()

    def _wwbench_progress(self, done, total, u) -> bool:
        tag = "✓" if (u.ok and (u.detections > 0) == u.has_wakeword) else ("•" if u.ok else "⚠")
        kind = "wake" if u.has_wakeword else "filler"
        self.wwb_summary.set_markup(
            f"<i>{done}/{total}</i>  {tag} {kind} · {GLib.markup_escape_text(u.voice)}"
            + (f" · <span foreground='#ff3b30'>{GLib.markup_escape_text(u.error)}</span>" if u.error else ""))
        return False

    def _wwbench_error(self, msg: str) -> bool:
        self.wwb_summary.set_markup(f"<span foreground='#ff3b30'>{GLib.markup_escape_text(msg)}</span>")
        return False

    def _wwbench_done(self, res) -> bool:
        if res.expected == 0:
            errs = {u.error for u in res.utterances if u.error}
            hint = ("  " + GLib.markup_escape_text(next(iter(errs)))) if errs else ""
            self.wwb_summary.set_markup(
                f"<span foreground='#ff3b30'>No utterances synthesized — check the TTS model/endpoint.</span>{hint}")
            return False
        by_voice = res.recall_by_voice()
        voice_bits = "  ".join(
            f"{GLib.markup_escape_text(v)} {d}/{t}" for v, (d, t) in sorted(by_voice.items()))
        colour = "#34c759" if res.recall >= 0.9 and res.false_fires == 0 else (
            "#ff9f0a" if res.recall >= 0.6 else "#ff3b30")
        self.wwb_summary.set_markup(
            f"<b><span foreground='{colour}'>Recall {res.recall * 100:.0f}%</span></b> "
            f"({res.detected}/{res.expected} fired)   ·   "
            f"<b>False fires:</b> {res.false_fires} in {len(res.filler)} filler   ·   "
            f"{res.seconds:.0f}s\n<small>per voice: {voice_bits}</small>")
        return False

    # ===== About ============================================================
    def _build_about(self, page: Gtk.Box) -> None:
        _infobox(page, "About Blitztext: version, source code, recent changes, and licence.")
        paths = _app_paths()
        changelog = _read_first(paths["changelog"])
        license_text = _read_first(paths["license"])

        title = Gtk.Label(label="Blitztext App Linux", xalign=0.0)
        title.set_markup("<b>Blitztext App Linux</b>")
        page.pack_start(title, False, False, 0)

        version = Gtk.Label(label=f"Version {__version__}", xalign=0.0)
        version.set_selectable(True)
        page.pack_start(version, False, False, 2)

        source = Gtk.LinkButton.new_with_label(
            "https://github.com/mARTin-B78/blitztext-app-linux",
            "Source: github.com/mARTin-B78/blitztext-app-linux",
        )
        source.set_halign(Gtk.Align.START)
        page.pack_start(source, False, False, 4)

        license_label = Gtk.Label(label="License: MIT", xalign=0.0)
        license_label.set_selectable(True)
        page.pack_start(license_label, False, False, 2)

        copyright_label = Gtk.Label(label="Copyright: 2026 mARTin Bierschenk - Design", xalign=0.0)
        copyright_label.set_selectable(True)
        page.pack_start(copyright_label, False, False, 2)

        nb = Gtk.Notebook()
        nb.set_margin_top(8)
        page.pack_start(nb, True, True, 0)

        changelog_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        changelog_box.pack_start(_text_panel(changelog, height=300), True, True, 0)
        nb.append_page(changelog_box, Gtk.Label(label="Changelog"))

        license_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        license_box.pack_start(_text_panel(license_text, height=300), True, True, 0)
        nb.append_page(license_box, Gtk.Label(label="License"))


    # ===== Log ==============================================================
    def _build_log(self, page: Gtk.Box) -> None:
        _infobox(page, "A live activity log — useful to see what Blitztext is doing, for "
                       "example while a speech model loads or downloads. Press Copy to put it "
                       "on the clipboard when you want to report a problem.")
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
            c.sounds_enabled = self.snd_enabled.get_active()
            c.sound_before = self.snd_before.get_filename() or ""
            c.sound_after = self.snd_after.get_filename() or ""
            c.wakeword_enabled = self.ww_enabled.get_active()
            c.wakeword_uri = self.ww_uri.get_text().strip()
            c.wakeword_model = _combo_text(self.ww_model)
            c.wakeword_sound_detected = self.ww_snd_detected.get_filename() or ""
            c.wakeword_sound_done = self.ww_snd_done.get_filename() or ""
            c.wakeword_silence_seconds = float(self.ww_silence.get_text())
            c.cancel_keywords = [k.strip() for k in self.cancel_keywords.get_text().split(",") if k.strip()]
            c.send_keywords = [k.strip() for k in self.send_keywords.get_text().split(",") if k.strip()]
            c.tts_url = self.wwb_url.get_text().strip().rstrip("/")
            c.tts_api_key_env = self.wwb_key.get_text().strip()
            c.tts_model = self.wwb_model.get_text().strip()
            c.tts_voices = [v.strip() for v in self.wwb_voices.get_text().split(",") if v.strip()]
            c.mic = self._selected_mic_name()
            c.output = self.gen_output.get_active_text() or "type"
            c.language = self.gen_lang.get_text().strip()
            c.notify = self.gen_notify.get_active()
            c.notify_routing = self.gen_notify_routing.get_active()
            c.overlay_enabled = self.gen_overlay.get_active()
            c.device = self.stt_device.get_active_text() or "auto"
            c.compute_type = self.stt_compute.get_active_text() or "auto"
            autostart.set_enabled(self.gen_boot.get_active())
            
            if c.wakeword_enabled:
                import socket
                from urllib.parse import urlparse
                parsed = urlparse(c.wakeword_uri)
                host = parsed.hostname or "127.0.0.1"
                port = parsed.port or 10400
                try:
                    with socket.create_connection((host, port), timeout=1.5):
                        pass
                except OSError as e:
                    self._error(f"Cannot connect to Wakeword server at {c.wakeword_uri}:\n{e}\n\nPlease check your server or disable wakeword.")
                    return False
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
        if resp in (RESP_SAVE, RESP_SAVE_RESTART):
            self._force_build_tabs()   # ensure every tab's fields exist
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

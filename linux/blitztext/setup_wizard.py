"""First-run setup wizard — guides new users through the essential settings.

Shows automatically when no config file exists yet (fresh install).
Can also be reopened from Settings → "Setup Wizard…".

Flow:
  Welcome → Trigger method → [Keyboard] → [Wakeword] → STT → LLM → Done

Pages in brackets are shown conditionally depending on the trigger choice.
"""

from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402


# ---------------------------------------------------------------------------
# Tiny style helpers
# ---------------------------------------------------------------------------

def _h1(text: str) -> Gtk.Label:
    lbl = Gtk.Label(label=text, xalign=0.0)
    lbl.set_line_wrap(True)
    attrs = Pango.AttrList()
    attrs.insert(Pango.attr_weight_new(Pango.Weight.BOLD))
    attrs.insert(Pango.attr_scale_new(1.45))
    lbl.set_attributes(attrs)
    return lbl


def _sub(text: str) -> Gtk.Label:
    lbl = Gtk.Label(label=text, xalign=0.0)
    lbl.set_line_wrap(True)
    lbl.set_max_width_chars(64)
    lbl.get_style_context().add_class("dim-label")
    return lbl


def _section(text: str) -> Gtk.Label:
    lbl = Gtk.Label(xalign=0.0)
    lbl.set_markup(f"<b><small>{GLib.markup_escape_text(text.upper())}</small></b>")
    lbl.set_margin_top(12)
    lbl.get_style_context().add_class("dim-label")
    return lbl


def _page_box() -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    box.set_margin_top(28); box.set_margin_bottom(8)
    box.set_margin_start(32); box.set_margin_end(32)
    return box


def _option_card(icon: str, title: str, desc: str) -> tuple[Gtk.RadioButton, Gtk.Box]:
    """A large selectable card with an icon, bold title, and grey description."""
    card = Gtk.Box(spacing=14)
    card.set_margin_top(4); card.set_margin_bottom(4)
    card.get_style_context().add_class("card")

    icon_lbl = Gtk.Label(label=icon)
    attrs = Pango.AttrList()
    attrs.insert(Pango.attr_scale_new(2.0))
    icon_lbl.set_attributes(attrs)
    icon_lbl.set_margin_start(14)
    card.pack_start(icon_lbl, False, False, 0)

    text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    text_box.set_margin_top(12); text_box.set_margin_bottom(12)
    title_lbl = Gtk.Label(label=title, xalign=0.0)
    attrs2 = Pango.AttrList()
    attrs2.insert(Pango.attr_weight_new(Pango.Weight.BOLD))
    title_lbl.set_attributes(attrs2)
    text_box.pack_start(title_lbl, False, False, 0)
    desc_lbl = Gtk.Label(label=desc, xalign=0.0)
    desc_lbl.get_style_context().add_class("dim-label")
    desc_lbl.set_line_wrap(True)
    desc_lbl.set_max_width_chars(55)
    text_box.pack_start(desc_lbl, False, False, 0)
    card.pack_start(text_box, True, True, 0)

    # Invisible RadioButton — the whole card is the clickable area.
    rb = Gtk.RadioButton()
    rb.set_margin_end(14)
    card.pack_start(rb, False, False, 0)
    return rb, card


def _keyval_token(keyval: int) -> str | None:
    from gi.repository import Gdk as _Gdk
    name = _Gdk.keyval_name(keyval) or ""
    low = name.lower()
    for mod in ("control", "ctrl"):
        if low.startswith(mod):
            return "ctrl"
    for mod in ("alt", "meta"):
        if low.startswith(mod):
            return "alt"
    if low.startswith("super") or low.startswith("hyper") or low.startswith("win"):
        return "cmd"
    if low.startswith("shift"):
        return "shift"
    if low in ("escape", "esc"):
        return "esc"
    if low in ("return", "enter"):
        return "enter"
    if low == "space":
        return "space"
    if len(name) == 1 and name.isalpha():
        return name.lower()
    return None


def _format_combo(tokens: list[str]) -> str:
    if not tokens:
        return ""
    order = ["ctrl", "alt", "shift", "cmd"]
    mods = [t for t in order if t in tokens]
    rest = [t for t in tokens if t not in order]
    parts = mods + rest
    return "+".join(f"<{p}>" for p in parts)


# ---------------------------------------------------------------------------
# Wizard
# ---------------------------------------------------------------------------

class SetupWizard:
    """Paged first-run setup dialog."""

    # Page names in fixed order; "keyboard" and "wakeword" are conditional.
    _ALL_PAGES = ("welcome", "trigger", "keyboard", "wakeword", "stt", "llm", "done")

    def __init__(self, cfg, parent: Gtk.Window | None = None):
        self.cfg = cfg
        self._parent = parent

        # Wizard state collected as user moves through pages.
        self._trigger = "keyboard"        # "keyboard" | "wakeword" | "both"
        self._kb_start  = cfg.key_start
        self._kb_stop   = cfg.key_stop
        self._kb_send   = cfg.key_send
        self._kb_cancel = cfg.key_cancel
        self._ww_uri    = cfg.wakeword_uri
        self._ww_model  = cfg.wakeword_model
        self._stt_local = True            # True = faster-whisper, False = remote API
        self._stt_size  = "small"
        self._stt_url   = ""
        self._stt_key   = ""
        self._llm_enabled = bool(cfg.base_url and cfg.base_url != "https://api.openai.com/v1")
        self._llm_url   = cfg.base_url
        self._llm_model = cfg.rewrite_model
        self._llm_key   = cfg.api_key_env

        # Key-binding capture state
        self._bind_entry: Gtk.Entry | None = None
        self._bind_pressed: list[str] = []

        self._build()

    # ------------------------------------------------------------------
    # Dialog shell
    # ------------------------------------------------------------------

    def _build(self) -> None:
        self.dlg = Gtk.Dialog(title="Blitztext Setup")
        if self._parent:
            self.dlg.set_transient_for(self._parent)
        self.dlg.set_modal(True)
        self.dlg.set_default_size(580, 520)
        self.dlg.set_resizable(False)
        self.dlg.get_action_area().hide()

        # Key capture
        self.dlg.add_events(Gdk.EventMask.KEY_PRESS_MASK | Gdk.EventMask.KEY_RELEASE_MASK)
        self.dlg.connect("key-press-event",   self._on_key_press)
        self.dlg.connect("key-release-event", self._on_key_release)

        content = self.dlg.get_content_area()
        content.set_spacing(0)

        # Stack
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(180)
        content.pack_start(self.stack, True, True, 0)

        self._pg: dict[str, Gtk.Widget] = {}
        builders = {
            "welcome":  self._build_welcome,
            "trigger":  self._build_trigger,
            "keyboard": self._build_keyboard,
            "wakeword": self._build_wakeword,
            "stt":      self._build_stt,
            "llm":      self._build_llm,
            "done":     self._build_done,
        }
        for name in self._ALL_PAGES:
            w = builders[name]()
            self.stack.add_named(w, name)
            self._pg[name] = w

        # Nav bar
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        content.pack_start(sep, False, False, 0)

        nav = Gtk.Box(spacing=8)
        nav.set_margin_top(10); nav.set_margin_bottom(10)
        nav.set_margin_start(20); nav.set_margin_end(20)

        self._btn_back = Gtk.Button(label="← Back")
        self._btn_back.connect("clicked", lambda _b: self._go(-1))
        nav.pack_start(self._btn_back, False, False, 0)

        self._step_lbl = Gtk.Label()
        self._step_lbl.get_style_context().add_class("dim-label")
        nav.pack_start(self._step_lbl, True, True, 0)

        self._btn_skip = Gtk.Button(label="Skip")
        self._btn_skip.get_style_context().add_class("flat")
        self._btn_skip.connect("clicked", lambda _b: self._go(+1, skip=True))
        nav.pack_start(self._btn_skip, False, False, 0)

        self._btn_next = Gtk.Button(label="Next →")
        self._btn_next.get_style_context().add_class("suggested-action")
        self._btn_next.connect("clicked", lambda _b: self._go(+1))
        nav.pack_start(self._btn_next, False, False, 0)

        content.pack_start(nav, False, False, 0)

        self._page_order: list[str] = []
        self._idx = 0
        self._refresh_page_order()
        self._show(0)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _refresh_page_order(self) -> None:
        pages = ["welcome", "trigger"]
        if self._trigger in ("keyboard", "both"):
            pages.append("keyboard")
        if self._trigger in ("wakeword", "both"):
            pages.append("wakeword")
        pages += ["stt", "llm", "done"]
        self._page_order = pages

    def _show(self, idx: int) -> None:
        self._idx = max(0, min(idx, len(self._page_order) - 1))
        name = self._page_order[self._idx]
        self.stack.set_visible_child_name(name)

        is_first = self._idx == 0
        is_last  = self._idx == len(self._page_order) - 1
        is_welcome = name == "welcome"
        is_done    = name == "done"

        self._btn_back.set_sensitive(not is_first)
        self._btn_skip.set_visible(not is_welcome and not is_done)
        self._btn_next.set_label("Start dictating →" if is_last else "Next →")

        # Step counter (exclude welcome and done from the count)
        core_pages = [p for p in self._page_order if p not in ("welcome", "done")]
        if name in core_pages:
            step = core_pages.index(name) + 1
            self._step_lbl.set_text(f"Step {step} of {len(core_pages)}")
        else:
            self._step_lbl.set_text("")

        # When leaving "trigger", re-evaluate page order.
        if name == "trigger":
            self._read_trigger()
            self._refresh_page_order()

    def _go(self, direction: int, skip: bool = False) -> None:
        name = self._page_order[self._idx]
        if not skip:
            self._commit_page(name)
        if direction > 0 and self._idx >= len(self._page_order) - 1:
            self._finish()
            return
        self._show(self._idx + direction)

    def _finish(self) -> None:
        self._apply_to_cfg()
        self.dlg.response(Gtk.ResponseType.OK)

    # ------------------------------------------------------------------
    # Page builders
    # ------------------------------------------------------------------

    def _build_welcome(self) -> Gtk.Widget:
        box = _page_box()
        box.set_valign(Gtk.Align.CENTER)

        logo = Gtk.Label(label="🎙")
        attrs = Pango.AttrList()
        attrs.insert(Pango.attr_scale_new(4.0))
        logo.set_attributes(attrs)
        logo.set_margin_bottom(12)
        box.pack_start(logo, False, False, 0)

        box.pack_start(_h1("Welcome to Blitztext"), False, False, 0)
        box.pack_start(_sub(
            "Blitztext lets you speak and have your words typed anywhere on screen — "
            "with optional AI polishing.\n\n"
            "This short wizard sets up the basics. "
            "You can change everything later in Settings."
        ), False, False, 0)
        return box

    def _build_trigger(self) -> Gtk.Widget:
        box = _page_box()
        box.pack_start(_h1("How do you want to trigger recording?"), False, False, 0)
        box.pack_start(_sub("You can change this later in Settings → Input."), False, False, 0)

        self._rb_kb,  card_kb  = _option_card("⌨",  "Keyboard shortcut",
            "Press a key combination to start and stop recording. "
            "Great for desktop use.")
        self._rb_ww,  card_ww  = _option_card("🎙", "Voice wakeword",
            "Say a wake phrase like \"okay computer\" to start hands-free. "
            "Needs a wakeword server.")
        self._rb_both, card_both = _option_card("✨", "Both",
            "Use a keyboard shortcut AND a voice wakeword — whichever is handy.")

        # Group the radio buttons
        self._rb_ww.join_group(self._rb_kb)
        self._rb_both.join_group(self._rb_kb)
        self._rb_kb.set_active(True)

        for rb, card in ((self._rb_kb, card_kb), (self._rb_ww, card_ww),
                         (self._rb_both, card_both)):
            # Make the card clickable by forwarding clicks to the radio button
            ebox = Gtk.EventBox()
            ebox.add(card)
            ebox.connect("button-press-event",
                         lambda _e, _ev, r=rb: r.set_active(True))
            box.pack_start(ebox, False, False, 0)

        return box

    def _build_keyboard(self) -> Gtk.Widget:
        box = _page_box()
        box.pack_start(_h1("Set up your keyboard shortcuts"), False, False, 0)
        box.pack_start(_sub(
            'Click "Set" and press a key combination to capture it. '
            "The defaults shown here work well for most users."
        ), False, False, 0)

        grid = Gtk.Grid(column_spacing=8, row_spacing=8)
        grid.set_margin_top(16)

        rows = [
            ("Start recording",     self._kb_start,  "_kb_start"),
            ("Stop and paste",      self._kb_stop,   "_kb_stop"),
            ("Stop, paste + Enter", self._kb_send,   "_kb_send"),
            ("Cancel",              self._kb_cancel, "_kb_cancel"),
        ]
        self._kb_entries: dict[str, Gtk.Entry] = {}

        for i, (label, value, attr) in enumerate(rows):
            lbl = Gtk.Label(label=label, xalign=0.0)
            lbl.set_size_request(180, -1)
            grid.attach(lbl, 0, i, 1, 1)

            entry = Gtk.Entry()
            entry.set_text(value)
            entry.set_size_request(140, -1)
            entry.set_editable(False)
            self._kb_entries[attr] = entry
            grid.attach(entry, 1, i, 1, 1)

            btn = Gtk.Button(label="Set")
            btn.connect("clicked", lambda _b, e=entry: self._bind_key(e))
            grid.attach(btn, 2, i, 1, 1)

        box.pack_start(grid, False, False, 0)

        note = Gtk.Label(xalign=0.0)
        note.set_markup(
            '<span size="small" alpha="75%">'
            "Tip: use modifier keys (Ctrl, Alt, Win/Cmd) rather than letters "
            "so shortcuts don't interfere with typing."
            "</span>")
        note.set_line_wrap(True)
        note.set_margin_top(8)
        box.pack_start(note, False, False, 0)
        return box

    def _build_wakeword(self) -> Gtk.Widget:
        box = _page_box()
        box.pack_start(_h1("Set up voice activation"), False, False, 0)
        box.pack_start(_sub(
            "Blitztext listens for your wake phrase through a local wakeword server. "
            "The server runs on your machine — nothing is sent to the cloud."
        ), False, False, 0)

        grid = Gtk.Grid(column_spacing=8, row_spacing=10)
        grid.set_margin_top(16)

        # Server URL
        lbl_uri = Gtk.Label(label="Server URL", xalign=0.0)
        lbl_uri.set_size_request(120, -1)
        self._wiz_ww_uri = Gtk.Entry()
        self._wiz_ww_uri.set_text(self._ww_uri)
        self._wiz_ww_uri.set_hexpand(True)
        self._wiz_ww_uri.set_placeholder_text("tcp://127.0.0.1:10400")
        grid.attach(lbl_uri, 0, 0, 1, 1)
        grid.attach(self._wiz_ww_uri, 1, 0, 1, 1)

        # Model
        lbl_model = Gtk.Label(label="Wake phrase", xalign=0.0)
        self._wiz_ww_model = Gtk.Entry()
        self._wiz_ww_model.set_text(self._ww_model)
        self._wiz_ww_model.set_placeholder_text("okay_computer")
        grid.attach(lbl_model, 0, 1, 1, 1)
        grid.attach(self._wiz_ww_model, 1, 1, 1, 1)

        box.pack_start(grid, False, False, 0)

        # Test row
        test_row = Gtk.Box(spacing=10)
        test_row.set_margin_top(8)
        self._wiz_ww_test_btn = Gtk.Button(label="Test connection")
        self._wiz_ww_test_btn.connect("clicked", self._ww_test)
        self._wiz_ww_test_lbl = Gtk.Label(label="", xalign=0.0)
        test_row.pack_start(self._wiz_ww_test_btn, False, False, 0)
        test_row.pack_start(self._wiz_ww_test_lbl, False, False, 0)
        box.pack_start(test_row, False, False, 0)

        # Setup hint (collapsible-ish — just always visible for simplicity)
        hint = Gtk.Label(xalign=0.0)
        hint.set_markup(
            '<span size="small" alpha="75%">'
            "Don't have a wakeword server yet? Run one with Docker:\n"
            "<tt>docker run -it -p 10400:10400 homeassistant/wyoming-openwakeword</tt>"
            "</span>")
        hint.set_line_wrap(True)
        hint.set_selectable(True)
        hint.set_margin_top(12)
        box.pack_start(hint, False, False, 0)
        return box

    def _build_stt(self) -> Gtk.Widget:
        box = _page_box()
        box.pack_start(_h1("Choose your speech-to-text engine"), False, False, 0)
        box.pack_start(_sub(
            "Blitztext transcribes your speech locally using Whisper, "
            "or you can connect to a remote OpenAI-compatible API."
        ), False, False, 0)

        # Local vs remote toggle
        self._rb_local, card_local = _option_card(
            "💻", "Local (faster-whisper)",
            "Runs on your machine — private, no API key needed. "
            "Choose the model size below.")
        self._rb_remote, card_remote = _option_card(
            "☁",  "Remote API",
            "Send audio to an OpenAI-compatible endpoint "
            "(OpenAI, local Whisper server, etc.).")
        self._rb_remote.join_group(self._rb_local)
        self._rb_local.set_active(True)

        for rb, card in ((self._rb_local, card_local), (self._rb_remote, card_remote)):
            ebox = Gtk.EventBox()
            ebox.add(card)
            ebox.connect("button-press-event",
                         lambda _e, _ev, r=rb: (r.set_active(True),
                                                 self._stt_toggle()))
            box.pack_start(ebox, False, False, 0)
            rb.connect("toggled", lambda _r: self._stt_toggle())

        # Local options
        self._stt_local_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._stt_local_box.set_margin_top(8)
        size_lbl = Gtk.Label(label="Model size", xalign=0.0)
        size_lbl.get_style_context().add_class("dim-label")

        self._stt_size_rb: dict[str, Gtk.RadioButton] = {}
        sizes = [
            ("tiny",     "Tiny — fastest, basic accuracy"),
            ("base",     "Base — fast, decent accuracy"),
            ("small",    "Small — balanced  ✓ recommended"),
            ("medium",   "Medium — better accuracy, slower"),
            ("large-v3", "Large — best accuracy, most memory"),
        ]
        size_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        prev = None
        for key, desc in sizes:
            rb = Gtk.RadioButton(label=desc)
            if prev:
                rb.join_group(prev)
            rb.set_active(key == self._stt_size)
            rb.connect("toggled", lambda r, k=key: r.get_active() and
                       setattr(self, "_stt_size", k))
            self._stt_size_rb[key] = rb
            size_box.pack_start(rb, False, False, 0)
            prev = rb
        self._stt_local_box.pack_start(size_lbl, False, False, 0)
        self._stt_local_box.pack_start(size_box, False, False, 0)
        box.pack_start(self._stt_local_box, False, False, 0)

        # Remote options
        self._stt_remote_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._stt_remote_box.set_margin_top(8)
        rgrid = Gtk.Grid(column_spacing=8, row_spacing=6)
        rlbl_url = Gtk.Label(label="API URL", xalign=0.0); rlbl_url.set_size_request(100, -1)
        self._stt_url_entry = Gtk.Entry(); self._stt_url_entry.set_hexpand(True)
        self._stt_url_entry.set_text(self._stt_url or "http://localhost:8010/v1")
        self._stt_url_entry.set_placeholder_text("http://localhost:8010/v1")
        rlbl_key = Gtk.Label(label="API key env", xalign=0.0)
        self._stt_key_entry = Gtk.Entry(); self._stt_key_entry.set_hexpand(True)
        self._stt_key_entry.set_text(self._stt_key)
        self._stt_key_entry.set_placeholder_text("OPENAI_API_KEY  (leave empty if not needed)")
        rgrid.attach(rlbl_url, 0, 0, 1, 1); rgrid.attach(self._stt_url_entry, 1, 0, 1, 1)
        rgrid.attach(rlbl_key, 0, 1, 1, 1); rgrid.attach(self._stt_key_entry, 1, 1, 1, 1)
        self._stt_remote_box.pack_start(rgrid, False, False, 0)
        self._stt_remote_box.set_no_show_all(True)
        box.pack_start(self._stt_remote_box, False, False, 0)

        first_run_note = Gtk.Label(xalign=0.0)
        first_run_note.set_markup(
            '<span size="small" alpha="65%">'
            "The local model is downloaded the first time you use it (~500 MB for Small). "
            "Subsequent starts are instant."
            "</span>")
        first_run_note.set_line_wrap(True)
        first_run_note.set_margin_top(6)
        box.pack_start(first_run_note, False, False, 0)
        return box

    def _build_llm(self) -> Gtk.Widget:
        box = _page_box()
        box.pack_start(_h1("AI text processing  (optional)"), False, False, 0)
        box.pack_start(_sub(
            "Blitztext can send your transcript to an AI model that rewrites it — "
            "cleaning up speech artifacts, adjusting tone, or reformatting it."
        ), False, False, 0)

        enable_row = Gtk.Box(spacing=10)
        enable_row.set_margin_top(12)
        self._llm_switch = Gtk.Switch()
        self._llm_switch.set_active(self._llm_enabled)
        self._llm_switch.set_valign(Gtk.Align.CENTER)
        enable_lbl = Gtk.Label(label="Enable AI rewriting", xalign=0.0)
        enable_row.pack_start(self._llm_switch, False, False, 0)
        enable_row.pack_start(enable_lbl, False, False, 0)
        box.pack_start(enable_row, False, False, 0)

        self._llm_detail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._llm_detail.set_margin_top(10)

        lgrid = Gtk.Grid(column_spacing=8, row_spacing=8)
        llbl_url = Gtk.Label(label="API URL", xalign=0.0); llbl_url.set_size_request(120, -1)
        self._llm_url_entry = Gtk.Entry(); self._llm_url_entry.set_hexpand(True)
        self._llm_url_entry.set_text(self._llm_url)
        self._llm_url_entry.set_placeholder_text("https://api.openai.com/v1")

        llbl_model = Gtk.Label(label="Model", xalign=0.0)
        self._llm_model_entry = Gtk.Entry(); self._llm_model_entry.set_hexpand(True)
        self._llm_model_entry.set_text(self._llm_model)
        self._llm_model_entry.set_placeholder_text("gpt-4o-mini")

        llbl_key = Gtk.Label(label="API key env", xalign=0.0)
        self._llm_key_entry = Gtk.Entry(); self._llm_key_entry.set_hexpand(True)
        self._llm_key_entry.set_text(self._llm_key)
        self._llm_key_entry.set_placeholder_text("OPENAI_API_KEY")

        lgrid.attach(llbl_url,   0, 0, 1, 1); lgrid.attach(self._llm_url_entry,   1, 0, 1, 1)
        lgrid.attach(llbl_model, 0, 1, 1, 1); lgrid.attach(self._llm_model_entry, 1, 1, 1, 1)
        lgrid.attach(llbl_key,   0, 2, 1, 1); lgrid.attach(self._llm_key_entry,   1, 2, 1, 1)
        self._llm_detail.pack_start(lgrid, False, False, 0)

        llm_note = Gtk.Label(xalign=0.0)
        llm_note.set_markup(
            '<span size="small" alpha="65%">'
            "Works with OpenAI, or a local model via Ollama / LM Studio / vLLM. "
            "You can fine-tune prompts per workflow in Settings → Workflows."
            "</span>")
        llm_note.set_line_wrap(True)
        self._llm_detail.pack_start(llm_note, False, False, 0)

        box.pack_start(self._llm_detail, False, False, 0)

        self._llm_switch.connect("notify::active", lambda s, _p: self._llm_toggle())
        self._llm_toggle()
        return box

    def _build_done(self) -> Gtk.Widget:
        box = _page_box()
        box.set_valign(Gtk.Align.CENTER)

        lbl_done = Gtk.Label(label="✅")
        attrs = Pango.AttrList()
        attrs.insert(Pango.attr_scale_new(3.5))
        lbl_done.set_attributes(attrs)
        lbl_done.set_margin_bottom(12)
        box.pack_start(lbl_done, False, False, 0)

        box.pack_start(_h1("You're all set!"), False, False, 0)
        self._done_summary = Gtk.Label(xalign=0.0)
        self._done_summary.set_line_wrap(True)
        self._done_summary.set_max_width_chars(60)
        self._done_summary.get_style_context().add_class("dim-label")
        box.pack_start(self._done_summary, False, False, 0)

        tip = Gtk.Label(xalign=0.0)
        tip.set_markup(
            '\n<span size="small" alpha="70%">'
            "You can always open <b>Settings</b> from the system tray to add workflows, "
            "tune STT quality, or configure more shortcuts."
            "</span>")
        tip.set_line_wrap(True)
        box.pack_start(tip, False, False, 0)
        return box

    # ------------------------------------------------------------------
    # Page commit helpers
    # ------------------------------------------------------------------

    def _read_trigger(self) -> None:
        if self._rb_ww.get_active():
            self._trigger = "wakeword"
        elif self._rb_both.get_active():
            self._trigger = "both"
        else:
            self._trigger = "keyboard"

    def _commit_page(self, name: str) -> None:
        if name == "trigger":
            self._read_trigger()
            self._refresh_page_order()
        elif name == "keyboard":
            for attr, entry in self._kb_entries.items():
                setattr(self, attr, entry.get_text().strip())
        elif name == "wakeword":
            self._ww_uri   = self._wiz_ww_uri.get_text().strip()
            self._ww_model = self._wiz_ww_model.get_text().strip()
        elif name == "stt":
            self._stt_local = self._rb_local.get_active()
            if not self._stt_local:
                self._stt_url = self._stt_url_entry.get_text().strip()
                self._stt_key = self._stt_key_entry.get_text().strip()
        elif name == "llm":
            self._llm_enabled = self._llm_switch.get_active()
            self._llm_url   = self._llm_url_entry.get_text().strip()
            self._llm_model = self._llm_model_entry.get_text().strip()
            self._llm_key   = self._llm_key_entry.get_text().strip()
            self._update_done_summary()

    def _update_done_summary(self) -> None:
        lines: list[str] = []
        if self._trigger in ("keyboard", "both"):
            lines.append(f"⌨  Keyboard — start: {self._kb_start}, cancel: {self._kb_cancel}")
        if self._trigger in ("wakeword", "both"):
            lines.append(f"🎙  Wakeword — {self._ww_model!r} @ {self._ww_uri}")
        if self._stt_local:
            lines.append(f"🤖  Local Whisper ({self._stt_size})")
        else:
            lines.append(f"☁  Remote STT — {self._stt_url}")
        if self._llm_enabled:
            lines.append(f"✨  AI rewriting — {self._llm_model} @ {self._llm_url}")
        else:
            lines.append("✨  AI rewriting — disabled")
        if hasattr(self, "_done_summary"):
            self._done_summary.set_text("\n".join(lines))

    # ------------------------------------------------------------------
    # Apply to config
    # ------------------------------------------------------------------

    def _apply_to_cfg(self) -> None:
        from .config import save
        from .stt import STTEngine
        cfg = self.cfg

        # Trigger / keyboard mode
        if self._trigger in ("keyboard", "both"):
            cfg.input_mode = "modifiers"
            cfg.key_start  = self._kb_start
            cfg.key_stop   = self._kb_stop
            cfg.key_send   = self._kb_send
            cfg.key_cancel = self._kb_cancel

        # Wakeword
        cfg.wakeword_enabled = self._trigger in ("wakeword", "both")
        if cfg.wakeword_enabled:
            cfg.wakeword_uri   = self._ww_uri
            cfg.wakeword_model = self._ww_model
            from .config import WakewordEngine
            # Update or create the first engine preset.
            if cfg.wakeword_engines:
                cfg.wakeword_engines[0].uri   = self._ww_uri
                cfg.wakeword_engines[0].model = self._ww_model
            else:
                cfg.wakeword_engines = [WakewordEngine(
                    name="Default", uri=self._ww_uri, model=self._ww_model)]
            cfg.wakeword_active = cfg.wakeword_engines[0].name

        # STT
        if self._stt_local:
            local_eng = STTEngine(name="Local Whisper", type="local",
                                  model=self._stt_size)
            # Replace or add.
            locals_ = [e for e in cfg.stt_engines if e.is_local]
            if locals_:
                idx = cfg.stt_engines.index(locals_[0])
                cfg.stt_engines[idx] = local_eng
            else:
                cfg.stt_engines.insert(0, local_eng)
            cfg.stt_active = local_eng.name
            cfg.model = self._stt_size
        else:
            remote_eng = STTEngine(name="Remote STT", type="openai",
                                   url=self._stt_url, api_key_env=self._stt_key)
            remotes = [e for e in cfg.stt_engines if not e.is_local]
            if remotes:
                idx = cfg.stt_engines.index(remotes[0])
                cfg.stt_engines[idx] = remote_eng
            else:
                cfg.stt_engines.append(remote_eng)
            cfg.stt_active = remote_eng.name

        # LLM
        if self._llm_enabled:
            cfg.base_url      = self._llm_url
            cfg.rewrite_model = self._llm_model
            cfg.api_key_env   = self._llm_key
            from .llm import LLMEngine
            llm_eng = LLMEngine("Default", self._llm_url,
                                self._llm_model, self._llm_key)
            if cfg.llm_engines:
                cfg.llm_engines[0] = llm_eng
            else:
                cfg.llm_engines = [llm_eng]
            cfg.llm_active = llm_eng.name

        # Mark setup as complete so the wizard doesn't auto-show again.
        cfg.setup_complete = True
        save(cfg)

    # ------------------------------------------------------------------
    # UI toggle helpers
    # ------------------------------------------------------------------

    def _stt_toggle(self) -> None:
        local = self._rb_local.get_active()
        self._stt_local_box.set_visible(local)
        self._stt_remote_box.set_visible(not local)

    def _llm_toggle(self) -> None:
        on = self._llm_switch.get_active()
        self._llm_detail.set_sensitive(on)

    # ------------------------------------------------------------------
    # Wakeword connection test
    # ------------------------------------------------------------------

    def _ww_test(self, _btn) -> None:
        uri = self._wiz_ww_uri.get_text().strip()
        self._wiz_ww_test_lbl.set_text("Testing…")
        self._wiz_ww_test_btn.set_sensitive(False)

        def _probe():
            import socket as _socket
            from urllib.parse import urlparse
            p = urlparse(uri)
            host = p.hostname or "127.0.0.1"
            port = p.port or 10400
            try:
                with _socket.create_connection((host, port), timeout=3.0):
                    ok = True
            except OSError:
                ok = False

            def _update():
                self._wiz_ww_test_btn.set_sensitive(True)
                if ok:
                    self._wiz_ww_test_lbl.set_markup(
                        '<span foreground="#2a7d2a">✓ Connected</span>')
                else:
                    self._wiz_ww_test_lbl.set_markup(
                        '<span foreground="#cc3333">✗ Could not connect — is the server running?</span>')
            GLib.idle_add(_update)

        threading.Thread(target=_probe, daemon=True).start()

    # ------------------------------------------------------------------
    # Key-binding capture
    # ------------------------------------------------------------------

    def _bind_key(self, entry: Gtk.Entry) -> None:
        self._bind_entry = entry
        self._bind_pressed = []
        entry.set_text("")
        entry.set_placeholder_text("press the key combination…")

    def _on_key_press(self, _w, event) -> bool:
        if self._bind_entry is None:
            return False
        tok = _keyval_token(event.keyval)
        if tok and tok not in self._bind_pressed:
            self._bind_pressed.append(tok)
        return True

    def _on_key_release(self, _w, event) -> bool:
        if self._bind_entry is None:
            return False
        combo = _format_combo(self._bind_pressed)
        if combo:
            self._bind_entry.set_text(combo)
            self._bind_entry.set_placeholder_text("")
        self._bind_entry = None
        self._bind_pressed = []
        return True

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        self.dlg.show_all()
        # Hide remote STT box initially (local is default)
        self._stt_remote_box.hide()
        self.dlg.run()
        self.dlg.destroy()


# ---------------------------------------------------------------------------
# Convenience: show if this is a fresh install
# ---------------------------------------------------------------------------

def maybe_show(cfg, parent: Gtk.Window | None = None) -> None:
    """Show the wizard if setup has never been completed."""
    if not getattr(cfg, "setup_complete", False):
        wiz = SetupWizard(cfg, parent=parent)
        wiz.run()

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
import unicodedata
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402  # type: ignore[import-untyped]

from . import __version__, audio, autostart, benchmark, llm, logbuffer, stt, wakeword_bench  # noqa: E402
from .config import Config, save  # noqa: E402
from .llm import LLMEngine  # noqa: E402
from .stt import STTEngine  # noqa: E402
from .config import Workflow  # noqa: E402

RESP_SAVE = 1
RESP_SAVE_RESTART = 2
GREEN, RED, GREY = "#34c759", "#ff3b30", "#b8b8be"

# (stored_value, display_label) pairs used by _type_combo / _type_key
_STT_TYPES: list[tuple[str, str]] = [
    ("local",         "Internal  —  faster-whisper, runs inside the app"),
    ("openai",        "Server  —  OpenAI-compatible API (LAN or cloud)"),
    ("riva_realtime", "Realtime  —  NVIDIA Riva / NIM streaming"),
]
_LLM_TYPES: list[tuple[str, str]] = [
    ("local", "LAN server  —  runs on your machine or local network"),
    ("cloud", "Cloud service  —  OpenAI, Groq, OpenRouter, …"),
]
_DEVICE_OPTIONS: list[tuple[str, str]] = [
    ("auto", "Auto  (try GPU / CUDA first, fall back to CPU)"),
    ("cpu",  "CPU"),
    ("cuda", "GPU  (CUDA)"),
]
_COMPUTE_OPTIONS: list[tuple[str, str]] = [
    ("auto",         "Auto"),
    ("int8",         "int8  —  fast, less memory"),
    ("float16",      "float16  —  accurate, needs more VRAM"),
    ("int8_float16", "int8_float16  —  balanced"),
]

# (name, url, api_key_env, type_key, default_model) — quickstart templates
_LLM_TEMPLATES: list[tuple[str, str, str, str, str]] = [
    ("OpenAI",       "https://api.openai.com/v1",          "OPENAI_API_KEY",     "cloud", "gpt-4o-mini"),
    ("Groq",         "https://api.groq.com/openai/v1",     "GROQ_API_KEY",       "cloud", "llama3-8b-8192"),
    ("OpenRouter",   "https://openrouter.ai/api/v1",       "OPENROUTER_API_KEY", "cloud", "openai/gpt-4o-mini"),
    ("Ollama",       "http://localhost:11434/v1",           "",                   "local", ""),
    ("LM Studio",    "http://localhost:1234/v1",            "",                   "local", ""),
    ("vLLM",         "http://localhost:8000/v1",            "",                   "local", ""),
    ("llama-swap",   "http://localhost:28080/v1",           "",                   "local", ""),
]
_STT_TEMPLATES: list[tuple[str, str, str, str, str]] = [
    # ── Cloud / API services ──────────────────────────────────────────────────
    ("OpenAI Whisper",          "https://api.openai.com/v1",      "OPENAI_API_KEY", "openai",        "whisper-1"),
    ("Groq Whisper (free tier)","https://api.groq.com/openai/v1", "GROQ_API_KEY",   "openai",        "whisper-large-v3-turbo"),
    # ── Local servers ─────────────────────────────────────────────────────────
    ("faster-whisper-server",   "http://localhost:8010/v1",        "",               "openai",        ""),
    ("Speaches (docker)",       "http://localhost:8080/v1",        "",               "openai",        ""),
    ("whisper.cpp server",      "http://localhost:8081/v1",        "",               "openai",        ""),
    ("NVIDIA NIM / Parakeet",   "http://localhost:8007/v1",        "",               "openai",        ""),
    ("Realtime (Riva / NIM)",   "http://localhost:8006/v1",        "",               "riva_realtime", ""),
    # ── Built-in local models (no server needed) ──────────────────────────────
    ("Local tiny  — fastest, ~39 MB",   "", "", "local", "tiny"),
    ("Local base  — fast,    ~74 MB",   "", "", "local", "base"),
    ("Local small — balanced, ~244 MB", "", "", "local", "small"),
    ("Local medium — accurate, ~769 MB","", "", "local", "medium"),
    ("Local large-v3 — best,  ~1.5 GB", "", "", "local", "large-v3"),
]

# (cat_emoji, label, [emojis]) — standard Unicode categories, WhatsApp-style
_EMOJI_CATEGORIES: list[tuple[str, str, list[str]]] = [
    ("😀", "Smileys", [
        "😀","😃","😄","😁","😆","😅","🤣","😂","🙂","🙃","😉","😊","😇",
        "🥰","😍","🤩","😘","😗","😚","😙","🥲","😋","😛","😜","🤪","😝",
        "🤑","🤗","🤭","🤫","🤔","🤐","🤨","😐","😑","😶","😏","😒","🙄",
        "😬","🤥","😌","😔","😪","🤤","😴","😷","🤒","🤕","🤢","🤮","🤧",
        "🥵","🥶","🥴","😵","🤯","🤠","🥳","🥸","😎","🤓","🧐","😕","😟",
        "🙁","😮","😯","😲","😳","🥺","😦","😧","😨","😰","😥","😢","😭",
        "😱","😖","😣","😞","😓","😩","😫","🥱","😤","😡","😠","🤬","😈",
        "👿","💀","☠️","💩","🤡","👹","👺","👻","👽","👾","🤖",
    ]),
    ("👋", "People", [
        "👋","🤚","🖐️","✋","🖖","👌","🤌","🤏","✌️","🤞","🤟","🤘","🤙",
        "👈","👉","👆","🖕","👇","☝️","👍","👎","✊","👊","🤛","🤜","👏",
        "🙌","👐","🤲","🤝","🙏","✍️","💅","💪","🦾","👂","👃","👀","👅",
        "👄","💋","👶","🧒","👦","👧","🧑","👱","👨","🧔","👩","🧓","👴",
        "👵","🙍","🙎","🙅","🙆","💁","🙋","🧏","🙇","🤦","🤷","💆","💇",
        "🚶","🏃","💃","🕺","🧖","🧗","🤸","⛹️","🏋️","🤼","🧘","🛀","🛌",
        "👮","🕵️","💂","🥷","👷","🫅","🤴","👸","🧙","🧝","🧛","🧟","🧞",
        "🧜","🧚","👼","🤶","🎅","🦸","🦹","🧑‍🍳","🧑‍🎓","🧑‍🏫","🧑‍⚕️","🧑‍💼","🧑‍🔧","🧑‍💻",
    ]),
    ("🐶", "Animals", [
        "🐶","🐱","🐭","🐹","🐰","🦊","🐻","🐼","🐨","🐯","🦁","🐮","🐷",
        "🐸","🐵","🙈","🙉","🙊","🐒","🐔","🐧","🐦","🐤","🦆","🦅","🦉",
        "🦇","🐺","🐗","🐴","🦄","🐝","🐛","🦋","🐌","🐞","🐜","🦟","🦗",
        "🕷️","🦂","🐢","🐍","🦎","🐙","🦑","🦐","🦀","🐡","🐠","🐟","🐬",
        "🐳","🐋","🦈","🐊","🐅","🐆","🦓","🦍","🐘","🦏","🐪","🦒","🦘",
        "🐃","🐄","🐎","🐖","🐏","🐑","🦙","🐐","🦌","🐕","🐩","🦮","🐈",
        "🐓","🦃","🦚","🦜","🦢","🦩","🕊️","🐇","🦝","🦨","🦡","🦦","🦥",
        "🐁","🐀","🐿️","🦔","🐉","🐲","🌵","🌲","🌳","🌴","🌿","☘️","🍀",
        "🎋","🎍","🍃","🍂","🍁","🌾","🌺","🌸","🌼","🌻","🌹","🥀","🌷",
    ]),
    ("🍎", "Food", [
        "🍏","🍎","🍐","🍊","🍋","🍌","🍉","🍇","🍓","🫐","🍒","🍑","🥭",
        "🍍","🥥","🥝","🍅","🍆","🥑","🥦","🥬","🥒","🌶️","🧄","🧅","🥔",
        "🌽","🥕","🍞","🥐","🥖","🥨","🧀","🥚","🍳","🧈","🥞","🥓","🥩",
        "🍗","🍖","🌭","🍔","🍟","🍕","🌮","🌯","🥙","🥚","🍲","🥗","🍿",
        "🧂","🍱","🍣","🍛","🍜","🍝","🍢","🥟","🥠","🥡","🍦","🍧","🍨",
        "🍩","🍪","🎂","🍰","🧁","🍫","🍬","🍭","🍮","🍯","🥛","☕","🍵",
        "🧃","🥤","🧋","🍺","🍻","🥂","🍷","🥃","🍸","🍹","🍾","🧊","🍴",
    ]),
    ("🏠", "Travel", [
        "🚗","🚕","🚙","🚌","🏎️","🚓","🚑","🚒","🚐","🛻","🚚","🚛","🚜",
        "🏍️","🛵","🚲","🛴","🛹","⚓","⛵","🚤","🛥️","🚢","✈️","🛩️","🚁",
        "🚀","🛸","🪐","🌍","🌎","🌏","🗺️","🧭","🏔️","⛰️","🌋","🏕️","🏖️",
        "🏜️","🏝️","🏟️","🏛️","🏗️","🏘️","🏠","🏡","🏢","🏣","🏤","🏥","🏦",
        "🏨","🏪","🏫","🏬","🏭","🏯","🏰","💒","🗼","🗽","⛪","🕌","⛩️",
        "🕋","⛲","⛺","🌁","🌃","🏙️","🌄","🌅","🌆","🌇","🌉","🌌","🌠",
        "🎇","🎆","🎑","🗾",
    ]),
    ("⚽", "Activities", [
        "⚽","🏀","🏈","⚾","🥎","🎾","🏐","🏉","🥏","🎱","🏓","🏸","🏒",
        "🥍","🏑","🏏","⛳","🎣","🤿","🎽","🎿","🛷","🥌","🎯","🎮","🎰",
        "🎲","♟️","🧩","🪄","🎭","🎨","🎪","🎤","🎧","🎼","🎹","🥁","🎷",
        "🎺","🎸","🎻","🎬","🎥","📽️","🎞️","🎠","🎡","🎢","🎟️","🎫","🏆",
        "🥇","🥈","🥉","🏅","🎖️","🎗️","🎀","🎁","🎊","🎉",
    ]),
    ("💡", "Objects", [
        "📱","📲","💻","⌨️","🖥️","🖨️","🖱️","💾","💿","📀","🧮","🎥","📷",
        "📹","📼","🔍","🔎","💡","🔦","🏮","🪔","📔","📒","📓","📕","📗",
        "📘","📙","📚","📖","🔖","🏷️","💰","💳","🪙","📈","📉","📊","📋",
        "📌","📍","✂️","🔒","🔓","🔏","🔐","🔑","🗝️","🔨","⛏️","⚒️","🛠️",
        "🔧","🪛","🔩","⚙️","⚖️","🔗","🧲","🪜","🧪","🔭","🔬","💊","💉",
        "🩹","🩺","🧴","🧷","🧹","🧺","🧻","🪣","🧼","🪒","🛒","🚪","🪞",
        "🛏️","🛋️","🪑","🚽","🚿","🛁","🧸","🪆","👓","🕶️","🥽","👒","🎩",
        "🧢","⛑️","📿","💍","💎","🌂","🧵","🧶","🪢","🎒","👜","👝","👛",
        "💼","🧳","🌂","☂️","🛡️","🗡️","⚔️","🪃","🏹","🪤","🪬","🧿","🔮",
    ]),
    ("🔣", "Symbols", [
        "❤️","🧡","💛","💚","💙","💜","🖤","🤍","🤎","💔","❣️","💕","💞",
        "💓","💗","💖","💘","💝","☮️","✝️","☪️","🕉️","☸️","✡️","☯️","☦️","🛐",
        "♈","♉","♊","♋","♌","♍","♎","♏","♐","♑","♒","♓","⛎",
        "🔀","🔁","🔂","▶️","⏩","⏭️","⏯️","◀️","⏪","⏮️","🔼","⏫","🔽",
        "⏬","⏸️","⏹️","⏺️","🎦","🔅","🔆","📶","🔇","🔈","🔉","🔊","📢",
        "📣","🔔","🔕","⚠️","🚸","⛔","🚫","🚳","🚭","🚯","🚱","🚷","📵",
        "🔞","💯","♻️","✅","❌","❎","➕","➖","➗","✖️","💲","™️","©️","®️",
        "〰️","➰","➿","🔚","🔙","🔛","🔜","🔝","🔴","🟠","🟡","🟢","🔵",
        "🟣","⚫","⚪","🟤","🔶","🔷","🔸","🔹","🔺","🔻","💠","🔘","⭕",
        "⭐","🌟","💫","✨","🔥","💧","🌊","🌀","⚡","❄️","🌈","🎵","🎶",
        "💬","💭","💤","❓","❗","⁉️","🔑","🎯","🏁","🚩","🎌","🏴","🏳️",
    ]),
]


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


def _labeled(parent, label: str, widget: Gtk.Widget, width: int = 130, tooltip: str = "") -> Gtk.Widget:
    is_lb = isinstance(parent, Gtk.ListBox)
    row_box = Gtk.Box(spacing=10)
    mt, mb, ms, me = (6, 6, 12, 8) if is_lb else (3, 3, 0, 0)
    row_box.set_margin_top(mt); row_box.set_margin_bottom(mb)
    if is_lb:
        row_box.set_margin_start(ms); row_box.set_margin_end(me)

    lbl = Gtk.Label(label=label, xalign=0.0); lbl.set_size_request(width, -1)
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

    row_box.pack_start(lbl, False, False, 0)
    row_box.pack_start(widget, True, True, 0)
    if tooltip:
        row_box.pack_start(_info_btn(tooltip), False, False, 0)

    if is_lb:
        _lb_add(parent, row_box)
    else:
        parent.pack_start(row_box, False, False, 0)
    return widget


def _switch_row(parent, label: str, switch: Gtk.Switch, description: str = "",
                width: int = 130) -> Gtk.Switch:
    """A settings row: [label] [grey description ……………] [ⓘ] [switch]."""
    is_lb = isinstance(parent, Gtk.ListBox)
    row = Gtk.Box(spacing=10)
    mt, mb = (6, 6) if is_lb else (3, 3)
    row.set_margin_top(mt); row.set_margin_bottom(mb)
    if is_lb:
        row.set_margin_start(12); row.set_margin_end(8)

    lbl = Gtk.Label(label=label, xalign=0.0); lbl.set_size_request(width, -1)
    row.pack_start(lbl, False, False, 0)

    desc = Gtk.Label(label=description, xalign=0.0)
    desc.set_line_wrap(True)
    desc.get_style_context().add_class("dim-label")
    row.pack_start(desc, True, True, 0)

    switch.set_halign(Gtk.Align.END); switch.set_valign(Gtk.Align.CENTER)
    row.pack_end(switch, False, False, 0)
    if description:
        row.pack_end(_info_btn(description), False, False, 0)

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

    if is_lb:
        _lb_add(parent, row)
    else:
        parent.pack_start(row, False, False, 0)
    return switch


def _infobox(parent: Gtk.Box, text: str) -> Gtk.Box:
    """A styled banner at the top of each settings tab."""
    box = Gtk.Box(spacing=10)
    box.set_margin_top(0); box.set_margin_bottom(12)
    box.set_margin_start(4); box.set_margin_end(4)
    box.get_style_context().add_class("bt-infobox")
    icon = Gtk.Image.new_from_icon_name("dialog-information-symbolic", Gtk.IconSize.BUTTON)
    icon.set_valign(Gtk.Align.CENTER)
    icon.set_margin_start(6); icon.set_margin_end(2)
    box.pack_start(icon, False, False, 0)
    lbl = Gtk.Label(label=text, xalign=0.0)
    lbl.set_line_wrap(True); lbl.set_xalign(0.0); lbl.set_max_width_chars(72)
    lbl.set_margin_top(8); lbl.set_margin_bottom(8); lbl.set_margin_end(8)
    box.pack_start(lbl, True, True, 0)
    acc = box.get_accessible()
    if acc:
        acc.set_name("Information")
        acc.set_description(text)
    parent.pack_start(box, False, False, 0)
    return box


def _section_title(parent: Gtk.Box, text: str, margin_top: int = 16) -> None:
    """A small bold uppercase section header above a group of settings."""
    lbl = Gtk.Label(xalign=0.0)
    lbl.set_markup(f"<b><small>{GLib.markup_escape_text(text.upper())}</small></b>")
    lbl.set_margin_top(margin_top); lbl.set_margin_bottom(3)
    lbl.get_style_context().add_class("bt-section")
    parent.pack_start(lbl, False, False, 0)


def _card_section(parent: Gtk.Box, title: str = "", margin_top: int = 16) -> Gtk.ListBox:
    """A titled card group. Returns a ListBox styled as a card for packing rows into."""
    if title:
        _section_title(parent, title, margin_top)
    lb = Gtk.ListBox()
    lb.set_selection_mode(Gtk.SelectionMode.NONE)
    lb.get_style_context().add_class("boxed-list")
    lb.get_style_context().add_class("bt-card")
    parent.pack_start(lb, False, False, 0)
    return lb


def _lb_add(lb: Gtk.ListBox, widget: Gtk.Widget) -> None:
    """Add any widget as a non-interactive row inside a card ListBox."""
    row = Gtk.ListBoxRow()
    row.set_activatable(False); row.set_selectable(False)
    row.add(widget)
    lb.add(row)


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


def _info_btn(text: str) -> Gtk.Button:
    """Small ⓘ button that shows a help popover when clicked."""
    btn = Gtk.Button()
    icon = Gtk.Image.new_from_icon_name("dialog-information-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
    btn.add(icon)
    btn.set_relief(Gtk.ReliefStyle.NONE)
    btn.set_tooltip_text(text)
    def _show(_b):
        pop = Gtk.Popover(relative_to=btn)
        lbl = Gtk.Label(label=text, xalign=0.0)
        lbl.set_line_wrap(True)
        lbl.set_max_width_chars(46)
        lbl.set_margin_top(10); lbl.set_margin_bottom(10)
        lbl.set_margin_start(12); lbl.set_margin_end(12)
        pop.add(lbl)
        pop.show_all()
    btn.connect("clicked", _show)
    return btn


def _type_combo(types: list[tuple[str, str]], stored: str = "") -> Gtk.ComboBoxText:
    """Combo that shows human-readable labels but maps to/from internal key values via index."""
    c = Gtk.ComboBoxText()
    for _, label in types:
        c.append_text(label)
    idx = next((i for i, (k, _) in enumerate(types) if k == stored), 0)
    c.set_active(idx)
    return c


def _type_key(combo: Gtk.ComboBoxText, types: list[tuple[str, str]], fallback: str = "") -> str:
    """Read the stored key for a combo built with _type_combo."""
    i = combo.get_active()
    return types[i][0] if 0 <= i < len(types) else fallback


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


def _url_field_lb(lb: Gtk.ListBox, label: str, placeholder: str, on_reload,
                  dot: Gtk.Label | None = None, width: int = 130) -> Gtk.Entry:
    """_url_field variant that adds the row as a ListBox card row."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    _url_field(box, label, placeholder, on_reload, dot=dot, width=width)
    row_box = box.get_children()[0]  # the row box built by _url_field
    box.remove(row_box)
    row_box.set_margin_top(6); row_box.set_margin_bottom(6)
    row_box.set_margin_start(12); row_box.set_margin_end(8)
    _lb_add(lb, row_box)
    # return the Entry widget (second child of row_box after label [and optional dot])
    for child in row_box.get_children():
        if isinstance(child, Gtk.Entry):
            return child
    return row_box.get_children()[-2]  # fallback: second-to-last (before refresh btn)


def _page(nb: Gtk.Notebook, title: str) -> Gtk.Box:
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    nb.append_page(outer, Gtk.Label(label=title))
    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.ALWAYS)
    sw.set_overlay_scrolling(False)  # always-visible scrollbar, not the overlay kind
    outer.pack_start(sw, True, True, 0)
    inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    for m in ("top", "bottom", "start", "end"):
        getattr(inner, f"set_margin_{m}")(15)
    sw.add(inner)
    outer._bt_inner = inner
    return outer


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
        "manual": [pkg_dir / "MANUAL.md", repo_dir / "MANUAL.md", Path("/opt/blitztext/MANUAL.md")],
    }


def _md_panel(text: str, height: int = 420) -> Gtk.ScrolledWindow:
    """Render a Markdown string into a read-only styled Gtk.TextView.

    Handles: # h1/h2/h3, **bold**, *italic*, `inline code`,
    > blockquotes, --- rules, bullet/numbered lists, and | tables |.
    """
    import re

    sw = Gtk.ScrolledWindow()
    sw.set_min_content_height(height)
    sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    view = Gtk.TextView()
    view.set_editable(False)
    view.set_cursor_visible(False)
    view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    view.set_left_margin(14)
    view.set_right_margin(14)
    view.set_top_margin(10)
    view.set_bottom_margin(10)

    buf = view.get_buffer()

    t_h1    = buf.create_tag("h1",    weight=Pango.Weight.BOLD, size_points=17.0,
                             pixels_above_lines=14, pixels_below_lines=4)
    t_h2    = buf.create_tag("h2",    weight=Pango.Weight.BOLD, size_points=13.0,
                             pixels_above_lines=10, pixels_below_lines=3)
    t_h3    = buf.create_tag("h3",    weight=Pango.Weight.BOLD, size_points=11.0,
                             pixels_above_lines=8,  pixels_below_lines=2)
    t_bold  = buf.create_tag("bold",  weight=Pango.Weight.BOLD)
    t_ital  = buf.create_tag("ital",  style=Pango.Style.ITALIC)
    t_code  = buf.create_tag("code",  family="Monospace", size_points=10.0,
                             background="#f0f0f4", foreground="#c7254e")
    t_quote = buf.create_tag("quote", left_margin=20, foreground="#666",
                             style=Pango.Style.ITALIC,
                             pixels_above_lines=2, pixels_below_lines=2)
    t_hr    = buf.create_tag("hr",    foreground="#aaa",
                             pixels_above_lines=6, pixels_below_lines=6)
    t_tbl   = buf.create_tag("tbl",   family="Monospace", size_points=10.0,
                             pixels_above_lines=1, pixels_below_lines=1)
    t_thdr  = buf.create_tag("thdr",  family="Monospace", size_points=10.0,
                             weight=Pango.Weight.BOLD,
                             pixels_above_lines=2, pixels_below_lines=1)

    _inline_re = re.compile(r'(\*\*.*?\*\*|\*.*?\*|`.*?`)')

    def _insert_inline(line: str, end_iter, *extra_tags) -> None:
        for part in _inline_re.split(line):
            if part.startswith("**") and part.endswith("**") and len(part) > 4:
                buf.insert_with_tags(end_iter, part[2:-2], t_bold, *extra_tags)
            elif part.startswith("*") and part.endswith("*") and len(part) > 2:
                buf.insert_with_tags(end_iter, part[1:-1], t_ital, *extra_tags)
            elif part.startswith("`") and part.endswith("`") and len(part) > 2:
                buf.insert_with_tags(end_iter, part[1:-1], t_code, *extra_tags)
            elif extra_tags:
                buf.insert_with_tags(end_iter, part, *extra_tags)
            else:
                buf.insert(end_iter, part)

    # Collect lines, detect table blocks so we can measure column widths
    lines = text.splitlines()
    # Pre-scan: mark which lines are table rows vs separators
    _tbl_sep = re.compile(r'^\|[-| :]+\|$')

    def _is_table_row(s: str) -> bool:
        return s.strip().startswith("|") and s.strip().endswith("|")

    first_line = True
    i = 0
    while i < len(lines):
        raw = lines[i].rstrip()
        end = buf.get_end_iter()

        if not first_line:
            buf.insert(end, "\n")
            end = buf.get_end_iter()
        first_line = False

        # --- Table block: gather all consecutive table rows ---
        if _is_table_row(raw):
            tbl_rows: list[list[str]] = []
            while i < len(lines) and (_is_table_row(lines[i].rstrip()) or _tbl_sep.match(lines[i].rstrip())):
                row_line = lines[i].rstrip()
                if not _tbl_sep.match(row_line):
                    cells = [c.strip() for c in row_line.strip("|").split("|")]
                    tbl_rows.append(cells)
                i += 1

            if tbl_rows:
                # Column widths: max of each column (plain text length, stripped of markup)
                n_cols = max(len(r) for r in tbl_rows)
                widths = [0] * n_cols
                for row in tbl_rows:
                    for ci, cell in enumerate(row):
                        plain = re.sub(r'\*\*|`|\*', '', cell)
                        widths[ci] = max(widths[ci], len(plain))

                for ri, row in enumerate(tbl_rows):
                    end = buf.get_end_iter()
                    tag = t_thdr if ri == 0 else t_tbl
                    line_text = ""
                    for ci in range(n_cols):
                        cell = row[ci] if ci < len(row) else ""
                        plain = re.sub(r'\*\*|`|\*', '', cell)
                        line_text += plain.ljust(widths[ci] + 2)
                    buf.insert_with_tags(end, line_text.rstrip(), tag)
                    if ri < len(tbl_rows) - 1:
                        end = buf.get_end_iter()
                        buf.insert(end, "\n")
            continue  # i already advanced

        # --- Normal lines ---
        if raw.startswith("### "):
            buf.insert_with_tags(end, raw[4:], t_h3)
        elif raw.startswith("## "):
            buf.insert_with_tags(end, raw[3:], t_h2)
        elif raw.startswith("# "):
            buf.insert_with_tags(end, raw[2:], t_h1)
        elif raw.startswith("> "):
            _insert_inline(raw[2:], end, t_quote)
        elif re.match(r'^-{3,}$', raw):
            buf.insert_with_tags(end, "─" * 64, t_hr)
        elif raw.startswith("- ") or raw.startswith("* "):
            buf.insert(end, "  • ")
            end = buf.get_end_iter()
            _insert_inline(raw[2:], end)
        elif re.match(r'^\d+\. ', raw):
            m = re.match(r'^(\d+\. )(.*)', raw)
            if m:
                buf.insert(end, "  " + m.group(1))
                end = buf.get_end_iter()
                _insert_inline(m.group(2), end)
        else:
            _insert_inline(raw, end)

        i += 1

    sw.add(view)
    return sw


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
        self.dlg.set_default_size(740, 700)
        self.dlg.add_button("Close", Gtk.ResponseType.CLOSE)
        self.dlg.add_button("Save", RESP_SAVE)
        self.dlg.add_button("Save & Restart", RESP_SAVE_RESTART)

        _prov = Gtk.CssProvider()
        _prov.load_from_data(b"""
.bt-section {
    font-weight: bold;
    font-size: small;
    letter-spacing: 1px;
    color: mix(@theme_fg_color, @theme_bg_color, 0.45);
    margin-top: 14px;
    margin-bottom: 2px;
}
.bt-card {
    border-radius: 8px;
    border: 1px solid mix(@theme_fg_color, @theme_bg_color, 0.8);
    padding: 2px 0px;
    margin-bottom: 4px;
}
.bt-card row {
    padding: 0px;
}
.bt-infobox {
    border-radius: 6px;
    border: 1px solid rgba(66, 133, 244, 0.50);
    background-color: rgba(66, 133, 244, 0.09);
    padding: 4px;
    margin-bottom: 10px;
}
.bt-infobox label {
    color: @theme_fg_color;
}
notebook.bt-nb tab {
    padding: 8px 18px;
    border-radius: 4px 4px 0 0;
}
notebook.bt-nb tab label {
    font-size: 14px;
    color: mix(@theme_fg_color, @theme_bg_color, 0.35);
}
notebook.bt-nb tab:checked label {
    font-size: 14px;
    font-weight: bold;
    color: #1a73e8;
}
.bt-emoji-btn {
    font-size: 20px;
    min-width: 38px;
    min-height: 38px;
    padding: 2px;
}
.bt-emoji-cat-btn {
    font-size: 18px;
    min-width: 34px;
    min-height: 34px;
    padding: 2px;
}
""")
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), _prov,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        nb = Gtk.Notebook()
        nb.get_style_context().add_class("bt-nb")
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
                               ("Manual", self._build_manual),
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
            content = getattr(page, "_bt_inner", page)
            builder(content)
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

        # ── Selector bar ──────────────────────────────────────────────────────
        bar = Gtk.Box(spacing=8)
        bar.set_margin_bottom(6)
        self.wf_combo = Gtk.ComboBoxText()
        for wf in self.cfg.workflows:
            self.wf_combo.append_text(wf.name)
        self.wf_combo.set_active(0)
        self.wf_combo.connect("changed", self._wf_changed)
        bar.pack_start(self.wf_combo, True, True, 0)
        add = Gtk.Button(label="+ Add"); add.connect("clicked", self._wf_add)
        rm  = Gtk.Button(label="Delete"); rm.connect("clicked", self._wf_delete)
        bar.pack_start(add, False, False, 0); bar.pack_start(rm, False, False, 0)
        page.pack_start(bar, False, False, 0)

        # ── Identity card ─────────────────────────────────────────────────────
        id_card = _card_section(page, "Identity", margin_top=4)
        self.wf_name = _labeled(id_card, "Name", _entry(placeholder="Preset name"),
                                tooltip="A short name for this action, shown in the main panel.")
        self.wf_icon = self._icon_field_lb(id_card, "Icon (emoji)")
        self.wf_desc = _labeled(id_card, "Description", _entry(placeholder="Short description shown in the panel"),
                                tooltip="One line explaining what this preset does.")

        # ── Trigger card ──────────────────────────────────────────────────────
        trig_card = _card_section(page, "Trigger")
        self.wf_keywords = _labeled(trig_card, "Keywords", _entry(placeholder="nicer email, bessere email"),
                                    tooltip="Spoken trigger words, comma-separated. Say one at the start or end of your speech to activate this preset.")
        self.wf_hotkey = self._key_field_lb(trig_card, "Hotkey (optional)", "", placeholder="click Set, or e.g. <ctrl>+<alt>+e")

        # ── Behaviour card ────────────────────────────────────────────────────
        beh_card = _card_section(page, "Behaviour")
        self.wf_mode = _labeled(beh_card, "Mode", _combo(["transcribe", "rewrite", "stream"]),
                                tooltip="’transcribe’ types your words as-is. ‘rewrite’ sends them to the language model first. ‘stream’ shows live text from a realtime engine.")
        # Engine dropdown — "(active engine)" + one entry per configured LLM engine.
        llm_names = [e.name for e in self.cfg.llm_engines]
        self.wf_llm_engine = _labeled(
            beh_card, "LLM engine",
            _combo(["(active engine)"] + llm_names),
            tooltip="Which LLM engine to use for the rewrite step. ‘(active engine)’ follows whatever is selected in the Engines tab.",
        )
        self.wf_temp  = _labeled(beh_card, "Temperature (opt.)", _entry(placeholder="blank = engine default (e.g. 0.3)"),
                                 tooltip="Creativity of the rewrite, 0–1. Lower is more predictable. Blank uses the engine default.")

        # ── Prompt ────────────────────────────────────────────────────────────
        _section_title(page, "Prompt sent to the LLM (rewrite mode)", margin_top=14)
        frame = Gtk.Frame(); frame.set_shadow_type(Gtk.ShadowType.IN)
        sw = Gtk.ScrolledWindow(); sw.set_min_content_height(140)
        self.wf_prompt = Gtk.TextView(); self.wf_prompt.set_wrap_mode(Gtk.WrapMode.WORD)
        self.wf_prompt.set_left_margin(8); self.wf_prompt.set_top_margin(6)
        self.wf_prompt.set_right_margin(8); self.wf_prompt.set_bottom_margin(6)
        sw.add(self.wf_prompt); frame.add(sw)
        page.pack_start(frame, True, True, 0)
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
        llm_names = [e.name for e in self.cfg.llm_engines]
        engine = getattr(wf, "llm_engine", "") or ""
        idx_e = (llm_names.index(engine) + 1) if engine in llm_names else 0
        self.wf_llm_engine.set_active(idx_e)
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
        engine_text = self.wf_llm_engine.get_active_text() or ""
        wf.llm_engine = "" if engine_text == "(active engine)" else engine_text
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

    def _icon_field(self, page: Gtk.Box, label: str, width: int = 130) -> Gtk.Entry:
        TOOLTIP = ("An emoji shown next to this preset when a voice command matches it — "
                   "give each preset a distinct one so you can tell at a glance which fired.")
        row = Gtk.Box(spacing=10); row.set_margin_top(3); row.set_margin_bottom(3)
        lbl = Gtk.Label(label=label, xalign=0.0); lbl.set_size_request(width, -1)
        lbl.set_tooltip_text(TOOLTIP)
        row.pack_start(lbl, False, False, 0)
        entry = Gtk.Entry(); entry.set_hexpand(True)
        entry.set_placeholder_text("⚡")
        entry.set_tooltip_text(TOOLTIP)
        atk = entry.get_accessible()
        if atk:
            atk.set_name(label.replace("_", ""))
            atk.set_description(TOOLTIP)
        row.pack_start(entry, True, True, 0)
        btn = Gtk.Button(label="😀")
        btn.set_tooltip_text("Pick an emoji")
        btn.connect("clicked", lambda _b: self._show_emoji_picker(btn, entry))
        row.pack_start(btn, False, False, 0)
        page.pack_start(row, False, False, 0)
        return entry

    def _icon_field_lb(self, lb: Gtk.ListBox, label: str, width: int = 130) -> Gtk.Entry:
        """_icon_field variant for use inside a card ListBox."""
        TOOLTIP = ("An emoji shown next to this preset when a voice command matches it — "
                   "give each preset a distinct one so you can tell at a glance which fired.")
        box = Gtk.Box(spacing=10)
        box.set_margin_top(6); box.set_margin_bottom(6)
        box.set_margin_start(12); box.set_margin_end(8)
        lbl = Gtk.Label(label=label, xalign=0.0); lbl.set_size_request(width, -1)
        lbl.set_tooltip_text(TOOLTIP)
        box.pack_start(lbl, False, False, 0)
        entry = Gtk.Entry(); entry.set_hexpand(True)
        entry.set_placeholder_text("⚡"); entry.set_tooltip_text(TOOLTIP)
        box.pack_start(entry, True, True, 0)
        btn = Gtk.Button(label="😀"); btn.set_tooltip_text("Pick an emoji")
        btn.connect("clicked", lambda _b: self._show_emoji_picker(btn, entry))
        box.pack_start(btn, False, False, 0)
        box.pack_start(_info_btn(TOOLTIP), False, False, 0)
        _lb_add(lb, box)
        return entry

    def _key_field_lb(self, lb: Gtk.ListBox, label: str, value: str,
                      placeholder: str = "", width: int = 130) -> Gtk.Entry:
        """_key_field variant for use inside a card ListBox."""
        box = Gtk.Box(spacing=10)
        box.set_margin_top(6); box.set_margin_bottom(6)
        box.set_margin_start(12); box.set_margin_end(8)
        lbl = Gtk.Label(label=label, xalign=0.0); lbl.set_size_request(width, -1)
        box.pack_start(lbl, False, False, 0)
        entry = Gtk.Entry(); entry.set_text(value); entry.set_hexpand(True)
        if placeholder:
            entry.set_placeholder_text(placeholder)
        box.pack_start(entry, True, True, 0)
        btn = Gtk.Button(label="Set")
        btn.connect("clicked", lambda _b, e=entry: self._bind_key(e))
        box.pack_start(btn, False, False, 0)
        _lb_add(lb, box)
        return entry

    def _show_emoji_picker(self, anchor: Gtk.Widget, entry: Gtk.Entry) -> None:
        pop = Gtk.Popover(relative_to=anchor)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # -- Search bar -------------------------------------------------------
        search = Gtk.SearchEntry()
        search.set_placeholder_text("Search emoji…")
        search.set_margin_top(6); search.set_margin_bottom(4)
        search.set_margin_start(6); search.set_margin_end(6)
        vbox.pack_start(search, False, False, 0)
        vbox.pack_start(Gtk.Separator(), False, False, 0)

        # Flat emoji list (all categories) used by search
        all_emojis: list[str] = [e for _, _, es in _EMOJI_CATEGORIES for e in es]

        def _keywords(e: str) -> str:
            try:
                return unicodedata.name(e[0], "").lower()
            except Exception:
                return ""

        # -- Category view ----------------------------------------------------
        cat_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        stack = Gtk.Stack()
        stack.set_transition_type(Gtk.StackTransitionType.NONE)
        stack.set_size_request(420, 230)

        cat_bar = Gtk.Box(spacing=0)
        cat_bar.set_margin_top(4); cat_bar.set_margin_bottom(4)
        cat_bar.set_margin_start(4); cat_bar.set_margin_end(4)

        first_name: str | None = None
        active_btn: list[Gtk.Button] = [None]

        def _select(name: str, btn: Gtk.Button) -> None:
            stack.set_visible_child_name(name)
            if active_btn[0]:
                active_btn[0].get_style_context().remove_class("suggested-action")
            btn.get_style_context().add_class("suggested-action")
            active_btn[0] = btn

        for cat_emoji, cat_name, emojis in _EMOJI_CATEGORIES:
            flow = Gtk.FlowBox()
            flow.set_max_children_per_line(10)
            flow.set_selection_mode(Gtk.SelectionMode.NONE)
            flow.set_margin_top(4); flow.set_margin_bottom(4)
            flow.set_margin_start(4); flow.set_margin_end(4)
            for emoji in emojis:
                eb = Gtk.Button(label=emoji)
                eb.set_relief(Gtk.ReliefStyle.NONE)
                eb.get_style_context().add_class("bt-emoji-btn")
                eb.connect("clicked", lambda _b, e=emoji: (entry.set_text(e), pop.popdown()))
                flow.add(eb)
            sw = Gtk.ScrolledWindow()
            sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            sw.add(flow)
            stack.add_named(sw, cat_name)

            cb = Gtk.Button(label=cat_emoji)
            cb.set_relief(Gtk.ReliefStyle.NONE)
            cb.get_style_context().add_class("bt-emoji-cat-btn")
            cb.set_tooltip_text(cat_name)
            cb.connect("clicked", lambda _b, n=cat_name, b=cb: _select(n, b))
            cat_bar.pack_start(cb, True, True, 0)

            if first_name is None:
                first_name = cat_name
                active_btn[0] = cb
                cb.get_style_context().add_class("suggested-action")

        if first_name:
            stack.set_visible_child_name(first_name)

        cat_scroll = Gtk.ScrolledWindow()
        cat_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        cat_scroll.set_min_content_height(44)
        cat_scroll.add(cat_bar)
        cat_container.pack_start(cat_scroll, False, False, 0)
        cat_container.pack_start(Gtk.Separator(), False, False, 0)
        cat_container.pack_start(stack, True, True, 0)

        # -- Search results view ----------------------------------------------
        search_sw = Gtk.ScrolledWindow()
        search_sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        search_sw.set_size_request(420, 274)
        search_flow = Gtk.FlowBox()
        search_flow.set_max_children_per_line(10)
        search_flow.set_selection_mode(Gtk.SelectionMode.NONE)
        search_flow.set_margin_top(4); search_flow.set_margin_bottom(4)
        search_flow.set_margin_start(4); search_flow.set_margin_end(4)
        search_sw.add(search_flow)

        def _on_search(_e: Gtk.SearchEntry) -> None:
            query = search.get_text().strip().lower()
            for child in search_flow.get_children():
                search_flow.remove(child)
            if query:
                cat_container.set_visible(False)
                search_sw.set_visible(True)
                for emoji in all_emojis:
                    if query in _keywords(emoji) or query in emoji:
                        btn = Gtk.Button(label=emoji)
                        btn.set_relief(Gtk.ReliefStyle.NONE)
                        btn.get_style_context().add_class("bt-emoji-btn")
                        btn.connect("clicked", lambda _b, e=emoji: (entry.set_text(e), pop.popdown()))
                        search_flow.add(btn)
                search_flow.show_all()
            else:
                search_sw.set_visible(False)
                cat_container.set_visible(True)

        search.connect("search-changed", _on_search)

        vbox.pack_start(cat_container, True, True, 0)
        vbox.pack_start(search_sw, True, True, 0)
        pop.add(vbox)
        pop.show_all()
        search_sw.set_visible(False)  # hide search results until user types

    # ===== Engines ==========================================================
    def _build_engines(self, page: Gtk.Box) -> None:
        _infobox(page, "Engines do the work. The speech-to-text engine turns your voice into "
                       "text; the language model rewrites it. Each can run locally or on "
                       "a server you enter. A green dot means it is reachable, red means offline.")
        _section_title(page, "Speech-to-text engine", margin_top=4)
        page.pack_start(self._stt_section(), False, False, 0)
        _section_title(page, "Language model (rewrite)")
        page.pack_start(self._llm_section(), False, False, 0)
        self._refresh_status()

    def _stt_section(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._stt_idx = 0

        # ── Selector bar ──────────────────────────────────────────────────────
        bar = Gtk.Box(spacing=6)
        self.stt_combo = Gtk.ComboBoxText()
        for e in self.cfg.stt_engines:
            self.stt_combo.append_text(e.name)
        self.stt_combo.set_active(self._index_of(self.cfg.stt_engines, self.cfg.stt_active))
        self.stt_combo.connect("changed", self._stt_changed)
        self.stt_dot = Gtk.Label(); self.stt_dot.set_markup(_dot(GREY))
        bar.pack_start(self.stt_dot, False, False, 0)
        bar.pack_start(self.stt_combo, True, True, 0)
        # Left: creation
        for label, cb in (("+ Add", self._stt_add), ("+ Stream", self._stt_add_stream)):
            b = Gtk.Button(label=label); b.connect("clicked", cb)
            bar.pack_start(b, False, False, 0)
        qs = Gtk.Button(label="Quickstart ▾")
        qs.set_tooltip_text("Fill the form from a common service template")
        qs.connect("clicked", self._show_stt_templates)
        bar.pack_start(qs, False, False, 0)
        # Right: actions (Test moved to its own row below the config)
        for label, cb, tip in (
            ("Delete",  self._stt_delete,                "Remove this engine preset"),
            ("⟳",       lambda _b: self._refresh_status(), "Re-check connection status"),
        ):
            b = Gtk.Button(label=label); b.set_tooltip_text(tip); b.connect("clicked", cb)
            bar.pack_end(b, False, False, 0)
        box.pack_start(bar, False, False, 2)

        # ── Engine config card ────────────────────────────────────────────────
        cfg_card = _card_section(box, "", margin_top=6)
        self.stt_name = _labeled(cfg_card, "Name", _entry(placeholder="e.g. faster-whisper GPU"),
                                 tooltip="A label for this engine, shown in the dropdown.")
        self.stt_type = _labeled(cfg_card, "Type", _type_combo(_STT_TYPES, "local"),
                                 tooltip="Internal: faster-whisper runs inside Blitztext, no server needed. "
                                         "Server: any OpenAI-compatible /v1 endpoint on your LAN or a cloud API. "
                                         "Realtime: live streaming via NVIDIA Riva or NIM.")
        self.stt_url  = _url_field_lb(cfg_card, "URL",
                                      "http://localhost:8010/v1  ·  realtime: http://localhost:8006/v1",
                                      lambda: self._populate_models(self.stt_model, self.stt_url.get_text().strip(), self.stt_key.get_text().strip()))
        self.stt_model = _labeled(cfg_card, "Model", _model_combo("tiny/base/small… or server model"),
                                  tooltip="Which Whisper model to load. For Internal: tiny (fastest) → large-v3 (most accurate). "
                                          "For a server, press ⟳ to fetch available models from its URL.")
        self.stt_key  = _labeled(cfg_card, "API key env", _entry(placeholder="e.g. GROQ_API_KEY   (optional)"),
                                 tooltip="Name of the environment variable that holds your API key. Leave blank for local servers.")
        self.stt_url.connect("changed", lambda _e: self._schedule_models("stt"))
        self.stt_key.connect("changed", lambda _e: self._schedule_models("stt"))
        self.stt_type.connect("changed", self._stt_type_changed)

        # ── Device & precision card ───────────────────────────────────────────
        dev_card = _card_section(box, "Internal engine — device & precision")
        self.stt_device  = _labeled(dev_card, "Device", _type_combo(_DEVICE_OPTIONS, self.cfg.device),
                                    tooltip="Which processor runs the speech model. "
                                            "Auto tries your GPU first. GPU (CUDA) requires NVIDIA — much faster than CPU.")
        self.stt_compute = _labeled(dev_card, "Compute type", _type_combo(_COMPUTE_OPTIONS, self.cfg.compute_type),
                                    tooltip="Precision of the model. int8 is fastest and uses least memory. "
                                            "float16 is most accurate. Auto lets Blitztext decide.")

        test_row = Gtk.Box(spacing=10)
        test_row.set_margin_top(6)
        stt_test_btn = Gtk.Button(label="Test")
        stt_test_btn.set_tooltip_text("Record 4 s and transcribe to test this engine")
        stt_test_btn.connect("clicked", self._stt_test)
        stt_test_btn.set_valign(Gtk.Align.START)
        test_row.pack_start(stt_test_btn, False, False, 0)
        self.stt_result = Gtk.Label(xalign=0.0)
        self.stt_result.set_line_wrap(True)
        self.stt_result.set_selectable(True)
        self.stt_result.set_valign(Gtk.Align.START)
        test_row.pack_start(self.stt_result, True, True, 0)
        box.pack_start(test_row, False, False, 2)

        self.stt_bench_info = Gtk.Label(xalign=0.0)
        self.stt_bench_info.set_use_markup(True)
        self.stt_bench_info.set_margin_top(2)
        box.pack_start(self.stt_bench_info, False, False, 0)

        self._stt_load(self.stt_combo.get_active())
        return box

    def _llm_section(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._llm_idx = 0

        # ── Selector bar ──────────────────────────────────────────────────────
        bar = Gtk.Box(spacing=6)
        self.llm_combo = Gtk.ComboBoxText()
        for e in self.cfg.llm_engines:
            self.llm_combo.append_text(e.name)
        self.llm_combo.set_active(self._index_of(self.cfg.llm_engines, self.cfg.llm_active))
        self.llm_combo.connect("changed", self._llm_changed)
        self.llm_dot = Gtk.Label(); self.llm_dot.set_markup(_dot(GREY))
        bar.pack_start(self.llm_dot, False, False, 0)
        bar.pack_start(self.llm_combo, True, True, 0)
        add = Gtk.Button(label="+ Add"); add.connect("clicked", self._llm_add)
        bar.pack_start(add, False, False, 0)
        qs = Gtk.Button(label="Quickstart ▾")
        qs.set_tooltip_text("Fill the form from a common service template")
        qs.connect("clicked", self._show_llm_templates)
        bar.pack_start(qs, False, False, 0)
        for label, cb, tip in (
            ("Delete", self._llm_delete,                "Remove this engine preset"),
            ("⟳",      lambda _b: self._refresh_status(), "Re-check connection status"),
        ):
            b = Gtk.Button(label=label); b.set_tooltip_text(tip); b.connect("clicked", cb)
            bar.pack_end(b, False, False, 0)
        box.pack_start(bar, False, False, 2)

        # ── Engine config card ────────────────────────────────────────────────
        cfg_card = _card_section(box, "", margin_top=6)
        self.llm_name = _labeled(cfg_card, "Name", _entry(placeholder="e.g. Local Qwen"),
                                 tooltip="A label for this language model engine, shown in the dropdown.")
        self.llm_type = _labeled(cfg_card, "Type", _type_combo(_LLM_TYPES, "cloud"),
                                 tooltip="LAN server: a model on your own machine or network (Ollama, vLLM, LM Studio, …). "
                                         "Cloud service: a remote paid API like OpenAI or Groq.")
        self.llm_url  = _url_field_lb(cfg_card, "Base URL",
                                      "http://localhost:28080/v1  ·  https://api.openai.com/v1",
                                      lambda: self._populate_models(self.llm_model, self.llm_url.get_text().strip(), self.llm_key.get_text().strip()))
        self.llm_model = _labeled(cfg_card, "Model", _model_combo("pick after entering URL"),
                                  tooltip="Which language model to use for rewriting. Press ⟳ on the URL field to fetch available models.")
        self.llm_key  = _labeled(cfg_card, "API key env", _entry(placeholder="e.g. OPENAI_API_KEY   (blank for local)"),
                                 tooltip="Name of the environment variable holding your API key. Leave blank for local servers.")
        self.llm_temp = _labeled(cfg_card, "Temperature", _entry(placeholder="0.3"),
                                 tooltip="How creative the rewrite is, 0.0–1.0. 0.3 is a good default.")
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
        self.stt_type.set_active(next((i for i, (k, _) in enumerate(_STT_TYPES) if k == e.type), 0))
        self.stt_url.set_text(e.url); self.stt_key.set_text(e.api_key_env)
        if e.type == "local":
            _fill_combo(self.stt_model, ["tiny", "base", "small", "medium", "large-v3"], e.model or self.cfg.model)
        elif e.type == "openai":
            _fill_combo(self.stt_model, [], e.model)
            self._populate_models(self.stt_model, e.url, e.api_key_env)
        else:
            _fill_combo(self.stt_model, [], e.model)
        self._stt_idx = idx
        self._stt_update_bench_info(e.name)

    def _stt_update_bench_info(self, engine_name: str) -> None:
        if not hasattr(self, "stt_bench_info"):
            return
        last = self.cfg.bench_last.get(engine_name)
        if not last:
            self.stt_bench_info.set_markup("")
            return
        if last.get("ok"):
            self.stt_bench_info.set_markup(
                f'<span foreground="#888" size="small">Last benchmark: '
                f'<b>{last["seconds"]:.2f}s</b> · <b>{last["accuracy"]:.1f}%</b> accuracy</span>')
        else:
            self.stt_bench_info.set_markup(
                '<span foreground="#888" size="small">Last benchmark: <b>failed</b></span>')

    def _stt_commit(self) -> None:
        idx = self._stt_idx
        if not (0 <= idx < len(self.cfg.stt_engines)):
            return
        e = self.cfg.stt_engines[idx]
        new_name = self.stt_name.get_text().strip() or e.name
        e.name = new_name
        e.type = _type_key(self.stt_type, _STT_TYPES, "local")
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
        self.llm_type.set_active(next((i for i, (k, _) in enumerate(_LLM_TYPES) if k == e.type), 0))
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
        e.type = _type_key(self.llm_type, _LLM_TYPES, "cloud")
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

    def _show_stt_templates(self, btn: Gtk.Button) -> None:
        menu = Gtk.Menu()
        for tpl in _STT_TEMPLATES:
            item = Gtk.MenuItem(label=tpl[0])
            item.connect("activate", lambda _i, t=tpl: self._stt_apply_template(t))
            menu.append(item)
        menu.show_all()
        menu.popup_at_widget(btn, Gdk.Gravity.SOUTH_WEST, Gdk.Gravity.NORTH_WEST, None)

    def _stt_apply_template(self, tpl: tuple) -> None:
        name, url, key, type_key, model = tpl
        self.stt_name.set_text(name)
        self.stt_url.set_text(url)
        self.stt_key.set_text(key)
        self.stt_type.set_active(next((i for i, (k, _) in enumerate(_STT_TYPES) if k == type_key), 0))
        if model:
            _fill_combo(self.stt_model, [model], model)
        elif url:
            self._populate_models(self.stt_model, url, key)

    def _show_llm_templates(self, btn: Gtk.Button) -> None:
        menu = Gtk.Menu()
        for tpl in _LLM_TEMPLATES:
            item = Gtk.MenuItem(label=tpl[0])
            item.connect("activate", lambda _i, t=tpl: self._llm_apply_template(t))
            menu.append(item)
        menu.show_all()
        menu.popup_at_widget(btn, Gdk.Gravity.SOUTH_WEST, Gdk.Gravity.NORTH_WEST, None)

    def _llm_apply_template(self, tpl: tuple) -> None:
        name, url, key, type_key, model = tpl
        self.llm_name.set_text(name)
        self.llm_url.set_text(url)
        self.llm_key.set_text(key)
        self.llm_type.set_active(next((i for i, (k, _) in enumerate(_LLM_TYPES) if k == type_key), 0))
        if model:
            _fill_combo(self.llm_model, [model], model)
        elif url:
            self._populate_models(self.llm_model, url, key)

    def _stt_type_changed(self, _c) -> None:
        typ = _type_key(self.stt_type, _STT_TYPES, "local")
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
                if not models and not cur:
                    combo.entry.set_placeholder_text("type model name manually")
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
            if which == "stt" and _type_key(self.stt_type, _STT_TYPES) == "openai":
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
                       "’modifiers’ mode: hold Ctrl and the Windows key to talk, then press "
                       "Ctrl to stop and paste. Below you can tune the noise filter, set up "
                       "hands-free wakeword, and pick sounds that confirm start and stop.")
        LW = 170

        # ── Input mode card ───────────────────────────────────────────────────
        mode_card = _card_section(page, "Input mode & keys", margin_top=4)
        self.in_mode = _labeled(mode_card, "Input mode", _combo(["modifiers", "hotkeys"], self.cfg.input_mode),
                                width=LW,
                                tooltip="’modifiers’: hold/press the keys below — easiest for most people. "
                                        "’hotkeys’: each preset has its own shortcut combo (set per preset).")
        self.in_ptt = Gtk.Switch(); self.in_ptt.set_active(self.cfg.push_to_talk)
        _switch_row(mode_card, "Push-to-talk", self.in_ptt, width=LW,
                    description="Hold the Start key to record; release to stop. "
                                "Off = the key toggles recording on/off.")
        self.in_start  = self._key_field_lb(mode_card, "Start",              self.cfg.key_start,  width=LW)
        self.in_stop   = self._key_field_lb(mode_card, "Stop + paste",       self.cfg.key_stop,   width=LW)
        self.in_send   = self._key_field_lb(mode_card, "Stop + paste + Enter", self.cfg.key_send, width=LW)
        self.in_cancel = self._key_field_lb(mode_card, "Cancel",             self.cfg.key_cancel, width=LW)

        # ── Quality gate card ─────────────────────────────────────────────────
        q_card = _card_section(page, "Quality gate")
        self.q_min = _labeled(q_card, "Min seconds", _entry(str(self.cfg.min_speech_seconds)), width=LW,
                              tooltip="Minimum audio length. Shorter clips are silently ignored (avoids pasting nothing).")
        self.q_rms = _labeled(q_card, "Silence RMS", _entry(str(self.cfg.silence_rms)), width=LW,
                              tooltip="Microphone volume threshold below which a clip is considered silent and dropped.")
        self.q_halluc = Gtk.Switch(); self.q_halluc.set_active(self.cfg.reject_hallucinations)
        _switch_row(q_card, "Reject hallucinations", self.q_halluc, width=LW,
                    description="Drop STT ghost outputs like ‘Thank you.’ or ‘Bye.’ that Whisper invents from silence.")
        self.q_strip = Gtk.Switch(); self.q_strip.set_active(self.cfg.strip_trailing_punctuation)
        _switch_row(q_card, "Strip trailing . / ,", self.q_strip, width=LW,
                    description="Remove ending punctuation from pasted text — handy for code insertion.")

        # ── Wakeword card ─────────────────────────────────────────────────────
        ww_card = _card_section(page, "Hands-free wakeword")
        self.ww_enabled = Gtk.Switch(); self.ww_enabled.set_active(self.cfg.wakeword_enabled)
        _switch_row(ww_card, "Enable wakeword", self.ww_enabled, width=LW,
                    description="Start dictation with a spoken keyword via an external openWakeWord server.")
        # ── Server preset dropdown ────────────────────────────────────────────
        self.ww_combo = Gtk.ComboBoxText()
        self.ww_combo.append_text("(custom)")
        for e in self.cfg.wakeword_engines:
            self.ww_combo.append_text(e.name)
        active_idx = next((i + 1 for i, e in enumerate(self.cfg.wakeword_engines)
                           if e.name == self.cfg.wakeword_active), 0)
        self.ww_combo.set_active(active_idx)
        self.ww_combo.set_tooltip_text("Pick a saved wakeword server preset, or use (custom) to enter a URI manually.")
        _labeled(ww_card, "Server preset", self.ww_combo, width=LW,
                 tooltip="Select from wakeword server presets defined in the benchmark list, or (custom) to type a URI directly.")

        self.ww_dot = Gtk.Label(); self.ww_dot.set_markup(_dot(GREY))
        self.ww_dot.set_tooltip_text("openWakeWord server: green = reachable, red = unreachable")
        self.ww_uri = _url_field_lb(ww_card, "Wakeword server", "tcp://127.0.0.1:10400",
                                    self._ww_load, dot=self.ww_dot, width=LW)
        self.ww_uri.set_text(self.cfg.wakeword_uri)
        self.ww_uri.connect("focus-out-event", self._on_ww_uri_leave)
        self._probe_dot(self.ww_dot, self.cfg.wakeword_uri, 10400)
        self.ww_model = _labeled(ww_card, "Model name", _model_combo("Search models…"), width=LW,
                                 tooltip="Which wake model to listen for (e.g. computer, okay_computer). Press ⟳ on the URI field to load models from the server.")
        _fill_combo(self.ww_model, [], self.cfg.wakeword_model)
        self.ww_combo.connect("changed", self._ww_preset_changed)

        self.ww_mic_level = Gtk.LevelBar()
        self.ww_mic_level.set_min_value(0); self.ww_mic_level.set_max_value(1)
        _labeled(ww_card, "Input level", self.ww_mic_level, width=LW,
                 tooltip="Live microphone level — the bar should move when you speak.")

        self.ww_test_btn = Gtk.Button(label="Test wakeword"); self.ww_test_btn.set_halign(Gtk.Align.START)
        self.ww_test_btn.connect("clicked", self._ww_test)
        self.ww_test_lbl = Gtk.Label(label=""); self.ww_test_lbl.set_xalign(0.0)
        test_box = Gtk.Box(spacing=10)
        test_box.pack_start(self.ww_test_btn, False, False, 0)
        test_box.pack_start(self.ww_test_lbl, False, False, 0)
        _labeled(ww_card, "", test_box, width=LW)

        self.ww_silence = _labeled(ww_card, "Silence to stop (s)", _entry(str(self.cfg.wakeword_silence_seconds)), width=LW,
                                   tooltip="After the wakeword fires, stop recording this many seconds after you stop speaking. Default 2.0.")
        self.cancel_keywords = _labeled(ww_card, "Cancel words", _entry(", ".join(self.cfg.cancel_keywords),
                                        placeholder="abbrechen, cancel"), width=LW,
                                        tooltip="Say one of these at the start or end of a clip to DISCARD it — nothing is typed. Empty = off.")
        self.send_keywords = _labeled(ww_card, "Send words", _entry(", ".join(self.cfg.send_keywords),
                                      placeholder="computer send, computer abschicken"), width=LW,
                                      tooltip="Say one of these to type AND press Enter (spoken ‘submit’). Use a distinctive multi-word phrase. Empty = off.")

        # ── Wakeword sound cues ───────────────────────────────────────────────
        ww_snd_card = _card_section(page, "Wakeword sound cues (hands-free only)")
        self.ww_snd_detected = self._sound_field(ww_snd_card, "Wakeword detected", self.cfg.wakeword_sound_detected,
            "Plays the instant the wake word fires — your ‘speak now’ cue. Leave empty for no sound.", width=LW)
        self.ww_snd_done = self._sound_field(ww_snd_card, "Speech captured", self.cfg.wakeword_sound_done,
            "Plays when your spoken command is captured and recording stops.", width=LW)

        # ── Manual dictation sounds card ──────────────────────────────────────
        snd_card = _card_section(page, "Audio cues (keyboard / hotkey dictation)")
        self.snd_enabled = Gtk.Switch(); self.snd_enabled.set_active(self.cfg.sounds_enabled)
        _switch_row(snd_card, "Play audio cues", self.snd_enabled, width=LW,
                    description="On/off for the manual start/stop chimes below. Does not affect wakeword sounds.")
        self.snd_before = self._sound_field(snd_card, "Start sound", self.cfg.sound_before,
            "Plays when manual recording starts.", width=LW)
        self.snd_after  = self._sound_field(snd_card, "Stop sound", self.cfg.sound_after,
            "Plays when manual recording stops (paste, paste+Enter, or auto-stop).", width=LW)

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
        if isinstance(page, Gtk.ListBox):
            if not row.get_margin_start():
                row.set_margin_start(12); row.set_margin_end(8)
                row.set_margin_top(6); row.set_margin_bottom(6)
            _lb_add(page, row)
        else:
            page.pack_start(row, False, False, 0)
        return chooser

    def _play_sound_file(self, path) -> None:
        from . import sound
        if path:
            sound.play(path)

    # ===== General ==========================================================
    def _build_general(self, page: Gtk.Box) -> None:
        _infobox(page, "Choose your microphone, how text is delivered, the spoken language, "
                       "and whether Blitztext starts automatically when you log in.")

        # ── Microphone card ───────────────────────────────────────────────────
        mic_card = _card_section(page, "Microphone", margin_top=4)
        self._mics = audio.list_mics()
        names = [label for _, label in self._mics]
        cur   = next((lbl for nm, lbl in self._mics if nm == self.cfg.mic), names[0] if names else "")
        self.gen_mic = _labeled(mic_card, "Device", _combo(names, cur),
                                tooltip="Which microphone Blitztext records from.")
        self.mic_level = Gtk.LevelBar()
        self.mic_level.set_min_value(0); self.mic_level.set_max_value(1)
        _labeled(mic_card, "Input level", self.mic_level,
                 tooltip="Live microphone level — should move when you speak.")
        self.gen_mic.connect("changed", lambda _c: self._restart_meter())

        # ── Output card ───────────────────────────────────────────────────────
        out_card = _card_section(page, "Text output & language")
        self.gen_output = _labeled(out_card, "Output mode", _combo(["type", "paste"], self.cfg.output),
                                   tooltip="’type’ types the text key by key via xdotool. "
                                           "’paste’ copies it to the clipboard and presses Ctrl+V (faster for long text).")
        self.gen_lang = _labeled(out_card, "Language hint", _entry(self.cfg.language, placeholder="de, en, …   (blank = autodetect)"),
                                 tooltip="Spoken language code (de, en, …). Leave blank to auto-detect.")

        # ── Notifications card ────────────────────────────────────────────────
        notif_card = _card_section(page, "Notifications & overlay")
        self.gen_notify = Gtk.Switch(); self.gen_notify.set_active(self.cfg.notify)
        _switch_row(notif_card, "Notifications", self.gen_notify,
                    "Desktop pop-ups for recording, transcription, and errors (manual dictation).")
        self.gen_notify_routing = Gtk.Switch(); self.gen_notify_routing.set_active(self.cfg.notify_routing)
        _switch_row(notif_card, "Announce preset", self.gen_notify_routing,
                    "After a voice command, show which preset and keyword matched — even hands-free.")
        self.gen_overlay = Gtk.Switch(); self.gen_overlay.set_active(self.cfg.overlay_enabled)
        _switch_row(notif_card, "Visual overlay", self.gen_overlay,
                    "Show a microphone, live waveform, and recognised text in a bubble at the cursor while you dictate.")

        # ── Startup card ──────────────────────────────────────────────────────
        start_card = _card_section(page, "Startup")
        self.gen_boot = Gtk.Switch(); self.gen_boot.set_active(autostart.is_enabled())
        _switch_row(start_card, "Launch on login", self.gen_boot,
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

    def _ww_preset_changed(self, combo) -> None:
        idx = combo.get_active()
        if idx <= 0 or idx - 1 >= len(self.cfg.wakeword_engines):
            return  # (custom) selected — leave fields as-is
        e = self.cfg.wakeword_engines[idx - 1]
        self.cfg.wakeword_active = e.name
        self.ww_uri.set_text(e.uri)
        _fill_combo(self.ww_model, [], e.model)
        self._probe_dot(self.ww_dot, e.uri, 10400)
        self._ww_load()

    def _ww_load(self) -> None:
        self._probe_dot(self.ww_dot, self.ww_uri.get_text(), 10400)

        uri = self.ww_uri.get_text().strip()  # capture on GTK thread before spawning
        def work():
            import socket, json
            from urllib.parse import urlparse
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
                GLib.idle_add(lambda e=e: self._error(f"Failed to load models:\n{e}"))
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

        # Restore saved paths
        if self.cfg.bench_wav and Path(self.cfg.bench_wav).exists():
            wavf.set_filename(self.cfg.bench_wav)
        if self.cfg.bench_ref and Path(self.cfg.bench_ref).exists():
            reff.set_filename(self.cfg.bench_ref)

        def _on_wav_set(_b):
            fn = wavf.get_filename()
            if not fn: return
            self.cfg.bench_wav = fn
            p = Path(fn)
            for ext in (".reference.txt", ".txt"):
                cand = p.with_name(p.stem + ext)
                if cand.exists():
                    reff.set_filename(str(cand))
                    self.cfg.bench_ref = str(cand)
                    break
            save(self.cfg)
        wavf.connect("file-set", _on_wav_set)

        def _on_ref_set(_b):
            fn = reff.get_filename()
            if fn:
                self.cfg.bench_ref = fn
                save(self.cfg)
        reff.connect("file-set", _on_ref_set)

        # ── Engine / model selector ───────────────────────────────────────────
        _section_title(page, "Engines to benchmark", margin_top=10)

        sel_hdr = Gtk.Box(spacing=6); sel_hdr.set_margin_bottom(4)
        self._bench_filter = Gtk.SearchEntry()
        self._bench_filter.set_placeholder_text("Filter by name, model or URL…")
        sel_hdr.pack_start(self._bench_filter, True, True, 0)
        all_b = Gtk.Button(label="All")
        all_b.connect("clicked", lambda _: [cb.set_active(True)
                                             for cb in self._bench_checks.values()])
        none_b = Gtk.Button(label="None")
        none_b.connect("clicked", lambda _: [cb.set_active(False)
                                              for cb in self._bench_checks.values()])
        sel_hdr.pack_start(all_b, False, False, 0)
        sel_hdr.pack_start(none_b, False, False, 0)
        page.pack_start(sel_hdr, False, False, 0)

        sel_sw = Gtk.ScrolledWindow()
        sel_sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sel_sw.set_min_content_height(80)
        sel_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        sel_list.set_margin_start(4); sel_list.set_margin_end(4)
        sel_list.set_margin_top(2); sel_list.set_margin_bottom(2)
        sel_sw.add(sel_list)

        self._bench_checks: dict[str, Gtk.CheckButton] = {}
        self._bench_dots: dict[str, Gtk.Label] = {}
        self._bench_lang_labels: dict[str, Gtk.Label] = {}
        self._bench_sel_rows: list[tuple[Gtk.Box, str, list[str]]] = []  # (row, name, mutable_search)

        for e in self.cfg.stt_engines:
            row = Gtk.Box(spacing=6)
            dot = Gtk.Label(); dot.set_markup(_dot(GREY))
            self._bench_dots[e.name] = dot
            row.pack_start(dot, False, False, 0)
            label = e.name
            if e.model:
                label += f"  [{e.model}]"
            cb = Gtk.CheckButton(label=label)
            cb.set_active(True)
            self._bench_checks[e.name] = cb
            row.pack_start(cb, True, True, 0)
            lang_lbl = Gtk.Label(xalign=1.0)
            lang_lbl.set_markup(f"<small><span foreground='{GREY}'>—</span></small>")
            lang_lbl.set_margin_end(4)
            self._bench_lang_labels[e.name] = lang_lbl
            row.pack_end(lang_lbl, False, False, 0)
            sel_list.pack_start(row, False, False, 2)
            search_parts = [e.name, e.model, e.url]
            self._bench_sel_rows.append((row, e.name, search_parts))

        def _filter_bench(_e=None):
            q = self._bench_filter.get_text().lower()
            for row, _name, parts in self._bench_sel_rows:
                row.set_visible(not q or any(q in p.lower() for p in parts))
        self._bench_filter.connect("changed", _filter_bench)

        # Background: reachability + language metadata
        def _check_bench_status():
            meta_cache: dict[str, list] = {}
            for e in self.cfg.stt_engines:
                ok = stt.status(e, timeout=2.0)
                color = GREEN if ok else RED
                dot = self._bench_dots.get(e.name)
                if dot:
                    GLib.idle_add(dot.set_markup, _dot(color))
                # Fetch language metadata for remote engines
                if not e.is_local and e.url:
                    if e.url not in meta_cache:
                        meta_cache[e.url] = stt.list_models_meta(e.url, e.api_key_env, timeout=4.0)
                    langs: list[str] = []
                    for m in meta_cache[e.url]:
                        if not e.model or m.id == e.model or m.id.endswith("/" + e.model):
                            langs = m.languages
                            break
                    if not langs and meta_cache[e.url]:
                        langs = meta_cache[e.url][0].languages
                    if langs:
                        # Update search parts so filter works on language codes
                        for row, name, parts in self._bench_sel_rows:
                            if name == e.name:
                                parts.extend(langs)
                        lang_str = stt.fmt_languages(langs)
                        lbl = self._bench_lang_labels.get(e.name)
                        if lbl:
                            GLib.idle_add(lbl.set_markup,
                                f"<small><span foreground='{GREY}'>{GLib.markup_escape_text(lang_str)}</span></small>")
        threading.Thread(target=_check_bench_status, daemon=True).start()

        # ── Run controls ──────────────────────────────────────────────────────
        run_row = Gtk.Box(spacing=16)
        run_row.set_margin_top(6); run_row.set_margin_bottom(4)
        run = Gtk.Button(label="Run benchmark"); run.connect("clicked", self._run_bench)
        run.set_halign(Gtk.Align.START)
        run_row.pack_start(run, False, False, 0)
        self.bench_expand = Gtk.CheckButton(label="Test all models per engine")
        self.bench_expand.set_tooltip_text(
            "Fetch every available model from each remote engine and run a separate "
            "benchmark row per model — useful to compare models on the same server.")
        self.bench_expand.set_active(self.cfg.bench_expand_models)
        self.bench_expand.connect("toggled",
            lambda cb: setattr(self.cfg, "bench_expand_models", cb.get_active()))
        run_row.pack_start(self.bench_expand, False, False, 0)
        page.pack_start(run_row, False, False, 0)

        # ── Resizable pane: engine list (top) ↕ results table (bottom) ───────
        # engine, url, model, device, best_for, lang, time, accuracy, output, tooltip
        self.bench_store = Gtk.ListStore(str, str, str, str, str, str, str, str, str, str)
        bench_sort = Gtk.TreeModelSort(model=self.bench_store)
        tree = Gtk.TreeView(model=bench_sort)
        tree.set_has_tooltip(True)
        tree.set_tooltip_column(9)
        for title, i, expand, max_w in [
                ("Engine",   0, False, 0),
                ("URL",      1, False, 180),
                ("Model",    2, False, 0),
                ("Device",   3, False, 0),
                ("Best for", 4, False, 0),
                ("Lang",     5, False, 160),
                ("Time (s)", 6, False, 0),
                ("Accuracy", 7, False, 0),
                ("Output",   8, True,  0)]:
            r = Gtk.CellRendererText()
            r.set_property("ellipsize", Pango.EllipsizeMode.END)
            col = Gtk.TreeViewColumn(title, r, text=i); col.set_resizable(True)
            col.set_sort_column_id(i)
            col.set_expand(expand)
            if max_w:
                col.set_max_width(max_w)
            tree.append_column(col)
        tree_sw = Gtk.ScrolledWindow()
        tree_sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        tree_sw.add(tree)

        # Wrap tree + summary in a box so summary stays below the table inside the pane
        results_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        results_box.pack_start(tree_sw, True, True, 0)
        self.bench_summary = Gtk.Label(xalign=0.0); self.bench_summary.set_line_wrap(True)
        self.bench_summary.set_margin_top(4); self.bench_summary.set_margin_bottom(2)
        results_box.pack_start(self.bench_summary, False, False, 0)

        paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        paned.pack1(sel_sw, resize=True, shrink=False)
        paned.pack2(results_box, resize=True, shrink=False)
        paned.set_position(180)  # default: engine list gets ~180px, rest goes to results
        paned.set_size_request(-1, 320)  # never collapse below 320px total
        page.pack_start(paned, True, True, 4)

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
        # Persist to disk so paths survive without clicking Save
        changed = False
        if wav and wav != self.cfg.bench_wav:
            self.cfg.bench_wav = wav; changed = True
        if refp and refp != self.cfg.bench_ref:
            self.cfg.bench_ref = refp; changed = True
        if changed:
            save(self.cfg)
        if not wav or not refp:
            self._error("Pick a .wav file and a matching reference .txt file.")
            return
        reference = Path(refp).read_text(errors="replace")
        self.bench_store.clear()
        if hasattr(self, "stt_name"):   # only if Engines tab has been built
            self._stt_commit()

        # Filter to checked engines (deduplicate by name as safety net)
        checks = getattr(self, "_bench_checks", {})
        seen: set[str] = set()
        engines: list = []
        for e in self.cfg.stt_engines:
            if e.name in seen:
                continue
            seen.add(e.name)
            if not checks or checks.get(e.name, None) is None or checks[e.name].get_active():
                engines.append(e)

        if not engines:
            self.bench_summary.set_markup(
                f'<span foreground="{RED}">No engines selected — tick at least one above.</span>')
            return
        self.bench_summary.set_markup("<i>Running… (local models load on first use)</i>")

        expand = self.bench_expand.get_active()

        def work():
            def prog(row):
                GLib.idle_add(self._bench_add_row, row)
            rows = benchmark.run(engines, Path(wav), reference, language=self.cfg.language,
                                 get_local_transcriber=self._transcriber_for, progress=prog,
                                 expand_models=expand)
            GLib.idle_add(self._bench_done, rows)
        threading.Thread(target=work, daemon=True).start()

    @staticmethod
    def _bench_friendly_error(err: str) -> str:
        """Short human-readable reason from a raw STT error string."""
        e = err.lower()
        if "bad model" in e or ("400" in e and "model" in e):
            return "Wrong model name — clear the model field to use server default"
        if "connection refused" in e or "errno 111" in e:
            return "Server offline — check the URL and that the service is running"
        if "timed out" in e or "time out" in e:
            return "Timed out — server too slow or not responding (>60 s)"
        if "500" in e or "internal server error" in e:
            return "Server-side error — check the server logs"
        if "401" in e or "unauthorized" in e:
            return "Authentication failed — check the API key environment variable"
        if "404" in e or "not found" in e:
            return "Endpoint not found — check the URL (needs /v1 suffix?)"
        if "cannot reach" in e:
            return "Unreachable — check URL / firewall"
        return err[:120]

    def _bench_add_row(self, row) -> bool:
        acc = f"{row.accuracy:.1f}%" if row.ok else "—"
        if row.ok:
            out_friendly = row.text
            tooltip = row.text
        else:
            out_friendly = f"⚠ {self._bench_friendly_error(row.error)}"
            tooltip = row.error
        # Strip scheme from URL for display brevity (http://192.168.1.1:8080 → 192.168.1.1:8080)
        url_display = row.url.removeprefix("https://").removeprefix("http://").rstrip("/")
        lang_display = stt.fmt_languages(row.languages)
        self.bench_store.append([row.engine, url_display, row.model, row.device, row.best_for,
                                 lang_display, f"{row.seconds:.2f}", acc, out_friendly, tooltip])
        # Persist result so Engines tab can show it
        self.cfg.bench_last[row.engine] = {
            "seconds": row.seconds, "accuracy": row.accuracy, "ok": row.ok,
        }
        save(self.cfg)
        # Refresh info label if this engine is currently selected in Engines tab
        if hasattr(self, "stt_name"):
            cur = self.cfg.stt_engines[self._stt_idx].name if 0 <= self._stt_idx < len(self.cfg.stt_engines) else ""
            if cur == row.engine:
                self._stt_update_bench_info(row.engine)
        return False

    def _bench_done(self, rows) -> bool:
        fastest, acc = benchmark.best(rows)
        if not fastest or not acc:
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
                    self.cfg.wakeword_engines,
                    tts_url=url, tts_api_key_env=key, tts_model=model, voices=voices,
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

    # ===== Manual ===========================================================
    def _build_manual(self, page: Gtk.Box) -> None:
        text = _read_first(_app_paths()["manual"])
        if text == "Not available in this install.":
            # Show a clickable link instead of raw text
            lbl = Gtk.Label(xalign=0.0)
            lbl.set_line_wrap(True)
            lbl.set_markup("Manual not bundled in this install.\n\n"
                           "Read it online: "
                           "<a href='https://github.com/mARTin-B78/blitztext-app-linux'>"
                           "github.com/mARTin-B78/blitztext-app-linux</a>")
            lbl.set_margin_top(20); lbl.set_margin_start(20)
            page.pack_start(lbl, False, False, 0)
        else:
            page.pack_start(_md_panel(text, height=420), True, True, 0)

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
        changelog_box.pack_start(_md_panel(changelog, height=300), True, True, 0)
        nb.append_page(changelog_box, Gtk.Label(label="Changelog"))

        license_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        license_box.pack_start(_md_panel(license_text, height=300), True, True, 0)
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

        lvl_lbl = Gtk.Label(label="Level:"); lvl_lbl.set_margin_start(8)
        bar.pack_start(lvl_lbl, False, False, 0)
        self.log_level = Gtk.ComboBoxText()
        for lvl in ("Verbose", "Info", "Warning", "Error"):
            self.log_level.append_text(lvl)
        self.log_level.set_active(1)  # default: Info
        self.log_level.set_tooltip_text("Show log entries at or above this severity level")
        self.log_level.connect("changed", lambda _: (setattr(self, "_log_last", None), self._log_refresh()))
        bar.pack_start(self.log_level, False, False, 0)

        clear = Gtk.Button(label="Clear"); clear.connect("clicked", lambda _b: (logbuffer.clear(), self._log_refresh()))
        copy = Gtk.Button(label="Copy"); copy.connect("clicked", lambda _b: self._log_copy())
        bar.pack_end(clear, False, False, 0); bar.pack_end(copy, False, False, 0)
        page.pack_start(bar, False, False, 0)

        self._log_last = None
        self._log_refresh()
        self._log_timer = GLib.timeout_add(1000, self._log_tick)

    def _log_min_level(self) -> str:
        idx = self.log_level.get_active() if hasattr(self, "log_level") else 1
        return ("DEBUG", "INFO", "WARNING", "ERROR")[max(0, min(idx, 3))]

    def _log_tick(self) -> bool:
        self._log_refresh()
        return True

    def _log_refresh(self) -> None:
        text = "\n".join(logbuffer.lines(self._log_min_level()))
        if text == getattr(self, "_log_last", None):
            return
        self._log_last = text
        buf = self.log_view.get_buffer()
        buf.set_text(text)
        if self.log_autoscroll.get_active():
            self.log_view.scroll_to_iter(buf.get_end_iter(), 0.0, False, 0, 0)

    def _log_copy(self) -> None:
        cb = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        cb.set_text("\n".join(logbuffer.lines(self._log_min_level())), -1)

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
            preset_idx = self.ww_combo.get_active()
            c.wakeword_active = (self.cfg.wakeword_engines[preset_idx - 1].name
                                 if preset_idx > 0 and preset_idx - 1 < len(self.cfg.wakeword_engines)
                                 else "")
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
            c.device = _type_key(self.stt_device, _DEVICE_OPTIONS, "auto")
            c.compute_type = _type_key(self.stt_compute, _COMPUTE_OPTIONS, "auto")
            autostart.set_enabled(self.gen_boot.get_active())
            
            if c.wakeword_enabled:
                # Check reachability in background — don't block the GTK thread
                uri = c.wakeword_uri
                def _bg_ww_check(uri=uri):
                    import socket
                    from urllib.parse import urlparse
                    parsed = urlparse(uri)
                    host = parsed.hostname or "127.0.0.1"
                    port = parsed.port or 10400
                    try:
                        with socket.create_connection((host, port), timeout=2.0):
                            logbuffer.log(f"[wakeword] server reachable at {uri}", level="INFO")
                    except OSError as e:
                        logbuffer.log(f"[wakeword] cannot reach {uri}: {e}", level="WARNING")
                threading.Thread(target=_bg_ww_check, daemon=True).start()
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

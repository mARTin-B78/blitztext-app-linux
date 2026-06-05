"""GTK control panel for Blitztext — a polished, GNOME-native UI.

Replaces the old tkinter panel. Uses GTK3 with CSS for rounded cards, a soft
gradient background, circular icon avatars, hotkey pills, and hover states.
Runs on the GTK main loop, unified with the AppIndicator tray (no event-loop
hacks). Status updates from worker threads are marshalled with GLib.idle_add.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from . import __version__  # noqa: E402
from .config import Config, load, save  # noqa: E402
from .daemon import Daemon  # noqa: E402

ICON_PATHS = [
    "/usr/share/icons/hicolor/256x256/apps/blitztext.png",
    str(Path(__file__).resolve().parent.parent / "packaging" / "blitztext.png"),
]

CSS = b"""
.bg { background-image: linear-gradient(180deg, #f8fbff 0%, #eaf1fa 100%); }
.title { font-weight: 700; font-size: 15px; }
.status { color: #7b818b; font-size: 12px; }
.dot { font-size: 11px; }
.ver { color: #aeb3bb; font-size: 10px; }

.row { background: none; border: none; box-shadow: none; padding: 9px 12px; border-radius: 12px; }
.row:hover { background-color: rgba(10,90,240,0.07); }
.row.recording { background-color: rgba(255,59,48,0.12); }
.row.dim { opacity: 0.45; }

.name { font-weight: 600; font-size: 13px; color: #1b1c1f; }
.desc { color: #80858e; font-size: 11px; }

.pill { background-color: rgba(0,0,0,0.06); color: #6a6f78; border-radius: 8px;
        padding: 2px 8px; font-size: 10px; }
.pill.rec { background-color: #ff3b30; color: #ffffff; }

.avatar { color: #ffffff; font-weight: 700; font-size: 14px;
          border-radius: 17px; min-width: 34px; min-height: 34px; }
.c0 { background-color: #0a84ff; }
.c1 { background-color: #30b85a; }
.c2 { background-color: #ff9f0a; }
.c3 { background-color: #ff375f; }
.c4 { background-color: #af52de; }
.c5 { background-color: #18b6c9; }

.gear { background: none; border: none; box-shadow: none; padding: 4px; }
.gear:hover { background-color: rgba(0,0,0,0.06); border-radius: 8px; }
"""

AVATAR_N = 6


def pretty_hotkey(hotkey: str) -> str:
    names = {"<ctrl>": "Ctrl", "<alt>": "Alt", "<shift>": "Shift", "<cmd>": "Super", "<space>": "Space"}
    parts = []
    for raw in hotkey.split("+"):
        inner = raw.strip("<>")
        parts.append(names.get(raw, inner.upper() if len(inner) == 1 else inner.title()))
    return " ".join(parts)


def _install_css() -> None:
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )


class App:
    def __init__(self, cfg: Config, tray_mode: bool = False):
        self.cfg = cfg
        self.tray_mode = tray_mode
        self.tray = None
        self.daemon = Daemon(cfg, status_cb=self._status_cb)
        self._rows: dict[str, dict] = {}
        self._active: str | None = None

        _install_css()
        self._build_window()

        threading.Thread(target=self._startup, daemon=True).start()

    # -- window ---------------------------------------------------------------
    def _build_window(self) -> None:
        self.win = Gtk.Window()
        self.win.set_default_size(420, -1)
        self.win.set_resizable(False)
        for p in ICON_PATHS:
            if os.path.exists(p):
                try:
                    self.win.set_icon_from_file(p)
                except Exception:  # noqa: BLE001
                    pass
                break
        self.win.set_icon_name("blitztext")

        head = Gtk.HeaderBar()
        head.set_show_close_button(True)
        head.set_title("Blitztext")
        status_box = Gtk.Box(spacing=5)
        self.dot = Gtk.Label(label="●")
        self.dot.get_style_context().add_class("dot")
        self._set_dot("#ff9f0a")
        self.status_lbl = Gtk.Label(label="Starting…")
        self.status_lbl.get_style_context().add_class("status")
        status_box.pack_start(self.dot, False, False, 0)
        status_box.pack_start(self.status_lbl, False, False, 0)
        head.pack_start(status_box)
        gear = Gtk.Button()
        gear.set_image(Gtk.Image.new_from_icon_name("emblem-system-symbolic", Gtk.IconSize.BUTTON))
        gear.get_style_context().add_class("gear")
        gear.set_tooltip_text("Settings")
        gear.connect("clicked", lambda _b: self.open_settings())
        head.pack_end(gear)
        self.win.set_titlebar(head)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.get_style_context().add_class("bg")
        listbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        listbox.set_margin_top(10)
        listbox.set_margin_bottom(6)
        listbox.set_margin_start(10)
        listbox.set_margin_end(10)
        for i, wf in enumerate(self.cfg.workflows):
            listbox.pack_start(self._make_row(i, wf), False, False, 0)
        outer.pack_start(listbox, True, True, 0)

        foot = Gtk.Box(spacing=8)
        foot.set_margin_start(14)
        foot.set_margin_end(14)
        foot.set_margin_bottom(10)
        foot.set_margin_top(2)
        ver = Gtk.Label(label=f"v{__version__}")
        ver.get_style_context().add_class("ver")
        foot.pack_start(ver, False, False, 0)
        quit_b = Gtk.Button(label="Quit")
        quit_b.get_style_context().add_class("gear")
        quit_b.connect("clicked", lambda _b: self.quit_all())
        foot.pack_end(quit_b, False, False, 0)
        outer.pack_start(foot, False, False, 0)

        self.win.add(outer)
        self.win.connect("delete-event", self._on_delete)

    def _make_row(self, i: int, wf) -> Gtk.Button:
        btn = Gtk.Button()
        btn.get_style_context().add_class("row")
        box = Gtk.Box(spacing=12)

        avatar = Gtk.Label(label=(wf.name[:1] or "?").upper())
        avatar.get_style_context().add_class("avatar")
        avatar.get_style_context().add_class(f"c{i % AVATAR_N}")
        box.pack_start(avatar, False, False, 0)

        mid = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        name = Gtk.Label(label=wf.name, xalign=0.0)
        name.get_style_context().add_class("name")
        mid.pack_start(name, False, False, 0)
        if wf.description:
            desc = Gtk.Label(label=wf.description, xalign=0.0)
            desc.get_style_context().add_class("desc")
            mid.pack_start(desc, False, False, 0)
        box.pack_start(mid, True, True, 0)

        pill = Gtk.Label(label=pretty_hotkey(wf.hotkey))
        pill.get_style_context().add_class("pill")
        box.pack_end(pill, False, False, 0)

        btn.add(box)
        btn.connect("clicked", lambda _b, w=wf: self.on_row_click(w))
        self._rows[wf.name] = {"btn": btn, "pill": pill}
        return btn

    # -- startup --------------------------------------------------------------
    def _startup(self) -> None:
        try:
            self.daemon.prepare()
            self.daemon.start_input()
        except Exception as exc:  # noqa: BLE001
            GLib.idle_add(self._apply_status, "error", None, f"Startup failed: {exc}")

    # -- interaction ----------------------------------------------------------
    def on_row_click(self, wf) -> None:
        if not self.daemon.ready or self.daemon._busy:
            return
        if self._active and wf.name != self._active:
            return
        self.trigger_workflow(wf)

    def trigger_workflow(self, wf) -> None:
        if not self.daemon.ready:
            return
        threading.Thread(target=lambda: self.daemon.toggle(wf), daemon=True).start()

    # -- status (marshalled to GTK thread) ------------------------------------
    def _status_cb(self, state: str, workflow: str | None, message: str) -> None:
        GLib.idle_add(self._apply_status, state, workflow, message)

    def _set_dot(self, color: str) -> None:
        self.dot.set_markup(f'<span foreground="{color}">●</span>')

    def _apply_status(self, state: str, workflow: str | None, message: str) -> bool:
        colors = {"loading": "#ff9f0a", "idle": "#34c759", "recording": "#ff3b30",
                  "streaming": "#ff3b30", "busy": "#ff9f0a", "done": "#34c759", "error": "#ff3b30"}
        labels = {"loading": "Loading…", "idle": "Ready", "recording": "Recording",
                  "streaming": "Live", "busy": "Working…", "done": "Ready", "error": message[:40] or "Error"}
        self._set_dot(colors.get(state, "#7b818b"))
        self.status_lbl.set_text(labels.get(state, message))

        if self.tray is not None:
            self.tray.update_status(state, labels.get(state, message))

        def cls(name, add, *names):
            ctx = self._rows[name]["btn"].get_style_context()
            for n in names:
                ctx.remove_class(n)
            if add:
                ctx.add_class(add)

        if state in ("recording", "streaming"):
            self._active = workflow
            for nm, r in self._rows.items():
                if nm == workflow:
                    cls(nm, "recording", "dim")
                    r["pill"].set_text("● Live" if state == "streaming" else "● Stop")
                    r["pill"].get_style_context().add_class("rec")
                else:
                    cls(nm, "dim", "recording")
        elif state == "busy":
            for nm in self._rows:
                if nm != workflow:
                    cls(nm, "dim", "recording")
        elif state in ("idle", "done", "error"):
            self._active = None
            for nm, r in self._rows.items():
                cls(nm, None, "dim", "recording")
                r["pill"].get_style_context().remove_class("rec")
                wf_match = next((w for w in self.cfg.workflows if w.name == nm), None)
                r["pill"].set_text(pretty_hotkey(wf_match.hotkey) if wf_match else "")
        return False  # one-shot idle

    # -- panel / settings / lifecycle -----------------------------------------
    def open_settings(self) -> None:
        from .gtksettings import SettingsDialog

        SettingsDialog(self.win, self.cfg, daemon=self.daemon).run_dialog()

    def show_panel(self) -> None:
        self.win.show_all()
        self.win.present()

    def hide_panel(self) -> None:
        self.win.hide()

    def _on_delete(self, *_a) -> bool:
        if self.tray is not None:
            self.hide_panel()
            return True  # keep running in tray
        self.quit_all()
        return False

    def quit_all(self) -> None:
        try:
            self.daemon.stop_input()
        finally:
            Gtk.main_quit()

    # -- run ------------------------------------------------------------------
    def run(self) -> None:
        if self.tray_mode:
            from . import tray as tray_mod

            self.tray = tray_mod.Tray(self)
            # stay in the tray; panel opens on demand
        else:
            self.win.show_all()
        Gtk.main()


def run_gui(tray_mode: bool = False) -> int:
    cfg = load()
    App(cfg, tray_mode=tray_mode).run()
    return 0

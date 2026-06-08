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
        self._rows: dict[str, dict] = {}
        self._active: str | None = None

        # On-screen dictation HUD (mic + waveform + recognised-text bubble).
        self.overlay = None
        self._ov_state = "idle"
        self._ov_streaming = False
        if cfg.overlay_enabled:
            try:
                from .overlay import Overlay

                self.overlay = Overlay(anchor_mode=cfg.overlay_anchor)
                if cfg.overlay_anchor == "caret":
                    from . import caret

                    caret.start_tracking()
            except Exception:  # noqa: BLE001 - overlay is optional eye-candy
                self.overlay = None

        self.daemon = Daemon(
            cfg, status_cb=self._status_cb,
            level_cb=self._on_level, text_cb=self._on_text,
            countdown_cb=self._on_countdown,
            # Only consume routing on the overlay when there's an overlay to show
            # it on; otherwise the daemon keeps the desktop notification.
            routing_cb=self._on_routing if self.overlay is not None else None,
        )

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
        self.listbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.listbox.set_margin_top(10)
        self.listbox.set_margin_bottom(6)
        self.listbox.set_margin_start(10)
        self.listbox.set_margin_end(10)
        self._refresh_listbox()
        outer.pack_start(self.listbox, True, True, 0)

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
        btn.set_tooltip_text(f"{wf.name}: {wf.description}" if wf.description else wf.name)
        atk = btn.get_accessible()
        if atk:
            atk.set_name(wf.name)
            if wf.description:
                atk.set_description(wf.description)
        btn.connect("clicked", lambda _b, w=wf: self.on_row_click(w))
        self._rows[wf.name] = {"btn": btn, "pill": pill}
        return btn

    def _refresh_listbox(self) -> None:
        for child in self.listbox.get_children():
            self.listbox.remove(child)
        self._rows.clear()
        for i, wf in enumerate(self.cfg.workflows):
            btn = self._make_row(i, wf)
            btn.drag_source_set(Gdk.ModifierType.BUTTON1_MASK, [], Gdk.DragAction.MOVE)
            btn.drag_source_add_text_targets()
            btn.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.MOVE)
            btn.drag_dest_add_text_targets()
            btn.connect("drag-data-get", self._on_drag_data_get, i)
            btn.connect("drag-data-received", self._on_drag_data_received, i)
            self.listbox.pack_start(btn, False, False, 0)
        self.listbox.show_all()

    def _on_drag_data_get(self, widget, drag_context, data, info, time, idx):
        data.set_text(str(idx), -1)

    def _on_drag_data_received(self, widget, drag_context, x, y, data, info, time, target_idx):
        text = data.get_text()
        if not text or not text.isdigit():
            return
        source_idx = int(text)
        if source_idx == target_idx or source_idx < 0 or source_idx >= len(self.cfg.workflows):
            return
        wfs = self.cfg.workflows
        wf = wfs.pop(source_idx)
        wfs.insert(target_idx, wf)
        save(self.cfg)
        self._refresh_listbox()

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

    # -- overlay feedback -----------------------------------------------------
    def _on_level(self, level: float) -> None:
        if self.overlay is not None:
            self.overlay.set_level(level)

    def _on_text(self, text: str) -> None:
        if self.overlay is not None:
            self.overlay.set_text(text)

    def _on_countdown(self, remaining: float | None, total: float) -> None:
        if self.overlay is not None:
            self.overlay.set_countdown(remaining, total)

    def _on_routing(self, icon: str, name: str, keyword: str | None) -> None:
        if self.overlay is not None:
            self.overlay.set_preset(icon, name, keyword)

    def _overlay_status(self, state: str, message: str) -> None:
        """Translate engine phases into overlay show/update/hide (GTK thread)."""
        ov = self.overlay
        if ov is None:
            return
        if state in ("recording", "streaming"):
            self._ov_streaming = state == "streaming"
            self._ov_state = state
            ov.show(state, getattr(self.daemon, "_target_window", None))
        elif state == "busy":
            self._ov_state = state
            # The routing detail ("→ Nicer email (matched: …)") is shown on the
            # preset banner, not as a phase chip — keep the chip a clean phase word.
            phase = "Transcribing…" if message.startswith("→") else message
            ov.set_state("busy", phase)
        elif state == "done":
            # Non-streaming: the 'done' message carries the final text. Streaming
            # already showed it live, so don't overwrite with "Streaming stopped".
            if not self._ov_streaming and message:
                ov.set_text(message)
            self._ov_state = state
            ov.set_state("done", message)
        elif state == "error":
            self._ov_state = state
            ov.set_state("error", message)
        elif state == "idle":
            # Only when a session was actually live — and never clip a 'done'
            # linger (idle is emitted right after done in the worker's finally).
            if self._ov_state in ("recording", "streaming", "busy"):
                ov.set_state("idle", message)
            self._ov_state = "idle"

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

        self._overlay_status(state, message)

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
        # Single instance: if Settings is already open, bring it to the front
        # instead of spawning a second dialog (the tray menu bypasses the
        # dialog's own modality, so it could otherwise be opened repeatedly).
        existing = getattr(self, "_settings", None)
        if existing is not None:
            existing.dlg.present()
            return
        from .gtksettings import SettingsDialog

        self._settings = SettingsDialog(self.win, self.cfg, daemon=self.daemon)
        self._settings.dlg.connect("destroy", lambda *_: setattr(self, "_settings", None))
        self._settings.run_dialog()

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
            if self.overlay is not None:
                self.overlay.destroy()
                from . import caret

                caret.stop_tracking()
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
    # Use GIO's native /proc/mounts volume monitor instead of the gvfs/udisks2
    # one. On headless or minimal desktops the `org.gtk.vfs.UDisks2VolumeMonitor`
    # dbus service often fails to activate, and every Gtk.FileChooserButton then
    # blocks ~25s on a StartServiceByName timeout while realizing — which freezes
    # the settings dialog (and, via the stalled main loop, the panel) so neither
    # ever appears. The unix monitor needs no dbus and opens choosers instantly.
    os.environ.setdefault("GIO_USE_VOLUME_MONITOR", "unix")
    # Identify to the window manager as "blitztext" rather than the Python entry
    # point's filename. Launched via `python -m blitztext`, GTK's default program
    # name is argv[0]'s basename ("__main__.py"), which is what shows in the
    # taskbar and in GNOME's "… is not responding" dialog. Setting it here (before
    # any window is realized) gives every window the app's real name + .desktop
    # match, without touching the `-m blitztext` entry point.
    GLib.set_prgname("blitztext")
    GLib.set_application_name("Blitztext")
    cfg = load()
    App(cfg, tray_mode=tray_mode).run()
    return 0

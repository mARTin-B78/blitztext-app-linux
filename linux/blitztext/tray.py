"""System-tray (AppIndicator) integration — the macOS-menu-bar-style entry.

Requires PyGObject (apt: python3-gi); the AyatanaAppIndicator3 + GTK-3 typelibs
are already present on this system. The tray coexists with the tkinter panel by
pumping the GLib main context from tkinter's event loop, so both share one
daemon, one Whisper model, and one set of global hotkeys.
"""

from __future__ import annotations

INSTALL_HINT = (
    "The system tray needs PyGObject, which isn't installed.\n"
    "  Install it (no build required):  sudo apt install python3-gi\n"
    "The GTK/AppIndicator typelibs are already present. Then run:\n"
    "  python -m blitztext tray\n"
    "Meanwhile, `python -m blitztext gui` (window) and `run` (headless) work now."
)

# Symbolic theme icons used for the panel indicator per state.
ICONS = {
    "loading": "content-loading-symbolic",
    "idle": "audio-input-microphone-symbolic",
    "recording": "media-record-symbolic",
    "busy": "content-loading-symbolic",
    "done": "audio-input-microphone-symbolic",
    "error": "dialog-error-symbolic",
}


def gi_available() -> bool:
    """True if PyGObject + an AppIndicator + GTK-3 are importable."""
    try:
        import gi

        gi.require_version("Gtk", "3.0")
        try:
            gi.require_version("AyatanaAppIndicator3", "0.1")
        except ValueError:
            gi.require_version("AppIndicator3", "0.1")
        return True
    except (ImportError, ValueError):
        return False


class Tray:
    """An AppIndicator with a workflow menu, driven by a BlitztextGUI app."""

    def __init__(self, app):
        import gi

        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk

        try:
            gi.require_version("AyatanaAppIndicator3", "0.1")
            from gi.repository import AyatanaAppIndicator3 as AppIndicator3
        except ValueError:
            gi.require_version("AppIndicator3", "0.1")
            from gi.repository import AppIndicator3

        self._Gtk = Gtk
        self.app = app

        self.indicator = AppIndicator3.Indicator.new(
            "blitztext",
            ICONS["idle"],
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self.indicator.set_title("Blitztext")
        self._build_menu()

    def _build_menu(self) -> None:
        from .gtkui import pretty_hotkey

        Gtk = self._Gtk
        menu = Gtk.Menu()

        self.status_item = Gtk.MenuItem(label="● Ready")
        self.status_item.set_sensitive(False)
        menu.append(self.status_item)
        menu.append(Gtk.SeparatorMenuItem())

        for wf in self.app.cfg.workflows:
            item = Gtk.MenuItem(label=f"{wf.name} ({pretty_hotkey(wf.hotkey)})")
            item.connect("activate", lambda _i, w=wf: self.app.trigger_workflow(w))
            menu.append(item)

        menu.append(Gtk.SeparatorMenuItem())
        for label, cb in (
            ("Show panel", self.app.show_panel),
            ("Settings…", self.app.open_settings),
        ):
            it = Gtk.MenuItem(label=label)
            it.connect("activate", lambda _i, c=cb: c())
            menu.append(it)
        menu.append(Gtk.SeparatorMenuItem())
        quit_item = Gtk.MenuItem(label="Quit Blitztext")
        quit_item.connect("activate", lambda _i: self.app.quit_all())
        menu.append(quit_item)

        menu.show_all()
        self.menu = menu
        self.indicator.set_menu(menu)

    def update_status(self, state: str, message: str) -> None:
        self.indicator.set_icon_full(ICONS.get(state, ICONS["idle"]), state)
        self.status_item.set_label(f"● {message or state.title()}")

    def pump(self) -> None:
        """Service pending GLib/GTK events; called from tkinter's loop."""
        Gtk = self._Gtk
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)

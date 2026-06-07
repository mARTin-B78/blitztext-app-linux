"""Best-effort screen anchor for the overlay: *where* to point the bubble's tip.

The overlay wants to sit at "the cursor where the text will land". On X11 there
is no portable way to read the text caret of an arbitrary app, so we degrade
through a chain of decreasing precision:

  1. AT-SPI caret  — the real text insertion point, when the focused app exposes
     it over accessibility (native GTK/Qt apps do; many terminals / Electron /
     web views do not). We track only the *focused* object via a11y events (cheap,
     low-frequency) and read its caret rectangle lazily, once, when the overlay
     shows — never from inside an event dispatch, since synchronous AT-SPI reads
     on the hot path can wedge the accessibility bus and freeze the session.
  2. Mouse pointer — `xdotool getmouselocation`. Always available on X11; a good
     proxy since the pointer is usually near where you're typing.
  3. Window / screen — top-centre of the target window, else screen bottom-centre.

Everything here is defensive: any failure falls through to the next tier, and
the whole module is optional — if AT-SPI isn't running you simply get the
pointer anchor. Returns a `(x, y, region)` anchor in **root/screen** pixels,
where `region` is the caret/line box so the overlay can avoid covering it.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass

from .logbuffer import log


@dataclass
class Anchor:
    x: int            # root-relative x to point the tail tip at
    y: int            # root-relative y (top of the caret/line box)
    height: int = 0   # caret/line height, so the bubble can clear the line
    source: str = ""  # "caret" | "pointer" | "window" | "corner" — for logging


# --------------------------------------------------------------------------- #
# Tier 1: AT-SPI caret tracking (best-effort, passive)
# --------------------------------------------------------------------------- #
class _CaretTracker:
    """Remember the most recently focused text object; read its caret lazily.

    *Why so cautious.* AT-SPI queries (``get_character_extents`` and friends) are
    **synchronous, blocking D-Bus round-trips into the target application**. The
    earlier design subscribed to the high-frequency ``object:text-caret-moved``
    signal and ran those blocking reads from *inside* the event handler. Two ways
    that wedges a whole GNOME/X11 session:

      • Calling a synchronous AT-SPI method from within an AT-SPI event dispatch
        re-enters the a11y dispatcher and can deadlock the accessibility bus.
      • ``text-caret-moved`` fires once *per character* — and delivering text is
        exactly what this app does, typing via ``xdotool`` into the focused
        field. So a single dictation became a storm of blocking round-trips on
        the GTK main loop, congesting the a11y bus until the desktop froze.

    So we now subscribe to **focus changes only** (rare, and never emitted by our
    own synthetic typing), cache just the focused accessible, and do the one
    blocking extents read **on demand** in :meth:`rect` — called once, when the
    overlay shows, outside any event dispatch. Worst case is a slightly delayed
    overlay placement, never a frozen session.
    """

    STALE_SECONDS = 30.0  # ignore a focus older than this

    def __init__(self) -> None:
        self._ok = False
        self._listener = None
        self._focused = None          # last focused accessible (read lazily)
        self._stamp = 0.0
        self._Atspi = None

    def start(self) -> bool:
        """Register the AT-SPI focus listener on the running GLib main loop.

        Safe to call when accessibility is disabled — it just returns False and
        the anchor logic skips this tier from then on.
        """
        try:
            import gi
            gi.require_version("Atspi", "2.0")
            from gi.repository import Atspi  # noqa: N813
        except (ImportError, ValueError) as exc:
            log(f"[overlay] AT-SPI unavailable, caret anchor disabled: {exc}")
            return False
        try:
            # init() is idempotent; returns 0/1. Connects to the a11y registry.
            Atspi.init()
            self._Atspi = Atspi
            self._listener = Atspi.EventListener.new(self._on_focus)
            # Focus changes only. Deliberately NOT "object:text-caret-moved": that
            # firehose (one event per typed character, including our own output)
            # plus synchronous reads is what could freeze the session.
            self._listener.register("object:state-changed:focused")
            self._ok = True
            log("[overlay] AT-SPI caret tracking active")
            return True
        except Exception as exc:  # noqa: BLE001 - a11y bus may be down/locked
            log(f"[overlay] AT-SPI init failed, caret anchor disabled: {exc}")
            self._ok = False
            return False

    def stop(self) -> None:
        try:
            if self._listener is not None:
                self._listener.deregister("object:state-changed:focused")
        except Exception:  # noqa: BLE001
            pass
        self._listener = None
        self._focused = None
        self._ok = False

    def _on_focus(self, event) -> None:
        # Runs on the GLib main thread (same loop GTK uses). Do the *minimum*:
        # stash the focused accessible and stamp it. Crucially, make NO synchronous
        # AT-SPI calls here — that would re-enter the a11y dispatcher and risk
        # deadlocking the bus. The blocking extents read happens later, in rect().
        try:
            if not event.detail1:
                return  # a *de*focus event — nothing to track
            self._focused = event.source
            self._stamp = time.time()
        except Exception:  # noqa: BLE001
            pass

    def _caret_rect(self, acc) -> tuple[int, int, int, int] | None:
        Atspi = self._Atspi
        text = None
        try:
            text = acc.get_text_iface()
        except Exception:  # noqa: BLE001
            text = None
        if text is None:
            return None
        try:
            offset = text.get_caret_offset()
            # Extents of the character at the caret, in absolute screen coords.
            ext = text.get_character_extents(offset, Atspi.CoordType.SCREEN)
            x, y, w, h = ext.x, ext.y, ext.width, ext.height
            if w == 0 and h == 0:
                # End-of-line / empty field: fall back to the component box so we
                # at least anchor on the right widget.
                comp = acc.get_component_iface()
                if comp is None:
                    return None
                cext = comp.get_extents(Atspi.CoordType.SCREEN)
                return int(cext.x), int(cext.y), 2, int(cext.height) or 18
            if x < 0 or y < 0:
                return None
            return int(x), int(y), int(w) or 2, int(h) or 18
        except Exception:  # noqa: BLE001
            return None

    def rect(self) -> tuple[int, int, int, int] | None:
        # Called once when the overlay shows (not on the a11y hot path), so the
        # single blocking extents read here is safe: at worst it briefly delays
        # the overlay, it cannot storm or re-enter the bus.
        if not self._ok or self._focused is None:
            return None
        if time.time() - self._stamp > self.STALE_SECONDS:
            return None
        try:
            return self._caret_rect(self._focused)
        except Exception:  # noqa: BLE001 - focused app may be gone/unresponsive
            return None


# --------------------------------------------------------------------------- #
# Tier 2 + 3: pointer and window fallbacks
# --------------------------------------------------------------------------- #
def _pointer() -> tuple[int, int] | None:
    if not shutil.which("xdotool"):
        return None
    try:
        out = subprocess.run(
            ["xdotool", "getmouselocation", "--shell"],
            capture_output=True, text=True, check=True, timeout=0.5,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    vals: dict[str, str] = {}
    for line in out.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            vals[k.strip()] = v.strip()
    try:
        return int(vals["X"]), int(vals["Y"])
    except (KeyError, ValueError):
        return None


def _window_box(window_id: str | None) -> tuple[int, int, int] | None:
    """Top-centre of the target window: (x, y, height_hint)."""
    if not window_id or not shutil.which("xdotool"):
        return None
    try:
        out = subprocess.run(
            ["xdotool", "getwindowgeometry", "--shell", window_id],
            capture_output=True, text=True, check=True, timeout=0.5,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    vals: dict[str, str] = {}
    for line in out.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            vals[k.strip()] = v.strip()
    try:
        x, y = int(vals["X"]), int(vals["Y"])
        w = int(vals["WIDTH"])
        return x + w // 2, y + 40, 0
    except (KeyError, ValueError):
        return None


def _screen_bottom_centre() -> tuple[int, int]:
    try:
        import gi
        gi.require_version("Gdk", "3.0")
        from gi.repository import Gdk
        disp = Gdk.Display.get_default()
        mon = disp.get_primary_monitor() or disp.get_monitor(0)
        geo = mon.get_geometry()
        return geo.x + geo.width // 2, geo.y + geo.height - 140
    except Exception:  # noqa: BLE001
        return 960, 800  # last-ditch constant; better than crashing


_tracker: _CaretTracker | None = None


def start_tracking() -> None:
    """Begin passive caret tracking (call once, from the GTK main thread)."""
    global _tracker
    if _tracker is None:
        _tracker = _CaretTracker()
        _tracker.start()


def stop_tracking() -> None:
    global _tracker
    if _tracker is not None:
        _tracker.stop()
        _tracker = None


def resolve(anchor_mode: str, window_id: str | None) -> Anchor:
    """Resolve the on-screen anchor for the overlay, honouring `anchor_mode`.

    anchor_mode:
      "caret"   -> caret → pointer → window → corner
      "pointer" -> pointer → window → corner
      "corner"  -> window → corner
    Always returns an Anchor (never None) so callers don't special-case failure.
    """
    if anchor_mode == "caret" and _tracker is not None:
        r = _tracker.rect()
        if r is not None:
            x, y, _w, h = r
            return Anchor(x=x, y=y, height=h or 18, source="caret")

    if anchor_mode in ("caret", "pointer"):
        p = _pointer()
        if p is not None:
            return Anchor(x=p[0], y=p[1], height=0, source="pointer")

    wb = _window_box(window_id)
    if wb is not None:
        return Anchor(x=wb[0], y=wb[1], height=0, source="window")

    x, y = _screen_bottom_centre()
    return Anchor(x=x, y=y, height=0, source="corner")

"""On-screen dictation HUD: a translucent bubble at the cursor.

Shows, while you dictate:
  • a microphone glyph that pulses red as it listens,
  • a live waveform driven by the real mic level,
  • the recognised text (word-by-word in streaming mode, or the final result as
    a brief confirmation in record-then-transcribe mode),
with a little tail whose tip points at the cursor where the text will land
(see :mod:`blitztext.caret` for how that anchor is resolved).

It is a click-through, focus-free override-redirect window so it never steals
input from the field you're dictating into. All public methods are safe to call
from worker threads — they marshal onto the GTK main loop via ``GLib.idle_add``.
Pure feedback: nothing here touches recording, transcription, or delivery, and
the whole feature is gated by ``cfg.overlay_enabled`` in the caller.
"""

from __future__ import annotations

import math
import time
from collections import deque

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GLib, Gtk, Pango, PangoCairo  # noqa: E402

from . import caret  # noqa: E402

# Layout constants (logical px).
_WIDTH = 360
_PAD = 16
_HEADER_H = 40          # mic + waveform row
_RADIUS = 16
_TAIL_W = 20
_TAIL_H = 11
_GAP = 12               # clearance between the tail tip and the anchor
_BARS = 30              # waveform bar count
_PRESET_H = 22          # matched-preset header row (emoji + name + keyword)
_MIN_TEXT_H = 0
_MAX_TEXT_H = 120

_FPS_MS = 33            # ~30 fps animation tick

# Phase → (mic colour, label). Recording/streaming pulse; others are steady.
_PHASES = {
    "recording": ((1.0, 0.27, 0.23), "Listening…"),
    "streaming": ((1.0, 0.27, 0.23), "Listening…"),
    "busy": ((1.0, 0.74, 0.16), "Transcribing…"),
    "done": ((0.30, 0.80, 0.36), ""),
    "error": ((1.0, 0.35, 0.35), "Error"),
}


_CANCEL_BTN_R = 11     # hit-radius of the × button (px)

class Overlay:
    def __init__(self, anchor_mode: str = "caret", on_cancel=None) -> None:
        self.anchor_mode = anchor_mode
        self._on_cancel_cb = on_cancel   # callable() → cancels current recording
        self._visible = False
        self._state = "recording"
        self._text = ""
        self._phase_label = "Listening…"
        # Matched-preset banner (fused in from voice routing instead of a separate
        # desktop notification): the preset's emoji, its name, and the spoken
        # keyword that selected it.
        self._preset_icon = ""
        self._preset_name = ""
        self._keyword = ""
        self._anchor: caret.Anchor | None = None
        self._tail_up = False           # tail on top edge (bubble below anchor)?
        self._tail_x = _WIDTH // 2       # tail tip, window-local x
        self._height = _HEADER_H + 2 * _PAD + _TAIL_H
        self._levels: deque[float] = deque([0.0] * _BARS, maxlen=_BARS)
        self._disp = [0.0] * _BARS       # eased bar heights for smooth motion
        self._pulse = 0.0
        # Silence auto-stop countdown ring (wraps the mic): a deadline the ring
        # drains toward, the window it spans, and an eased opacity so it fades in
        # when you fall quiet and out the moment you speak again.
        self._cd_deadline: float | None = None
        self._cd_total = 1.0
        self._cd_frac = 0.0
        self._cd_alpha = 0.0
        self._tick_id: int | None = None
        self._hide_id: int | None = None
        self._t0 = time.time()
        # Coalescing text updates: background LLM streaming can fire dozens of
        # set_text() calls per second. We buffer the latest text and only ever
        # have ONE idle_add pending — so the GTK main loop is never flooded.
        self._pending_text: str = ""
        self._text_flush_queued: bool = False
        self._pending_level: float = 0.0
        self._level_flush_queued: bool = False

        self._cancel_btn_rect = (0, 0, 0, 0)   # (x, y, w, h) in window coords

        self._win = Gtk.Window(type=Gtk.WindowType.POPUP)
        self._win.set_app_paintable(True)
        self._win.set_resizable(False)
        self._win.set_skip_taskbar_hint(True)
        self._win.set_skip_pager_hint(True)
        self._win.set_accept_focus(False)
        self._win.set_focus_on_map(False)
        self._win.set_keep_above(True)
        screen = self._win.get_screen()
        visual = screen.get_rgba_visual() if screen else None
        if visual is not None:
            self._win.set_visual(visual)
        self._area = Gtk.DrawingArea()
        if visual is not None:
            self._area.set_visual(visual)
        self._area.connect("draw", self._on_draw)
        self._win.add(self._area)
        self._win.connect("realize", self._on_realize)
        self._win.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self._win.connect("button-press-event", self._on_click)
        self._win.set_default_size(_WIDTH, self._height)

    # -- click-through (all except the × button) ------------------------------
    def _on_realize(self, _w) -> None:
        self._update_input_region()

    def _update_input_region(self) -> None:
        gdkwin = self._win.get_window()
        if gdkwin is None:
            return
        if self._on_cancel_cb and self._state in ("recording", "streaming", "busy"):
            x, y, w, h = self._cancel_btn_rect
            r = cairo.Region(cairo.RectangleInt(int(x), int(y), int(w), int(h)))
        else:
            r = cairo.Region()   # empty → fully click-through
        gdkwin.input_shape_combine_region(r, 0, 0)

    def _on_click(self, _win, event) -> bool:
        if self._on_cancel_cb is None:
            return False
        x, y, w, h = self._cancel_btn_rect
        if x <= event.x <= x + w and y <= event.y <= y + h:
            self._on_cancel_cb()
        return True

    # -- thread-safe public API ----------------------------------------------
    def show(self, state: str, window_id: str | None) -> None:
        GLib.idle_add(self._show, state, window_id)

    def set_level(self, level: float) -> None:
        self._pending_level = float(level)
        if not self._level_flush_queued:
            self._level_flush_queued = True
            GLib.idle_add(self._flush_level)

    def _flush_level(self) -> bool:
        self._level_flush_queued = False
        self._set_level(self._pending_level)
        return False

    def set_text(self, text: str) -> None:
        self._pending_text = text or ""
        # Only schedule a flush if none is already queued; this collapses a burst
        # of token callbacks (e.g. 50/s from LLM streaming) into a single GTK
        # redraw, preventing main-loop flooding and session freezes.
        if not self._text_flush_queued:
            self._text_flush_queued = True
            GLib.idle_add(self._flush_text)

    def _flush_text(self) -> bool:
        self._text_flush_queued = False
        self._set_text(self._pending_text)
        return False

    def set_preset(self, icon: str, name: str, keyword: str | None) -> None:
        """Show the matched voice-routing preset on the overlay (emoji + name +
        the spoken keyword), in place of a separate desktop notification."""
        GLib.idle_add(self._set_preset, icon or "", name or "", keyword or "")

    def set_countdown(self, remaining: float | None, total: float) -> None:
        """Silence auto-stop progress: ``remaining`` seconds until it fires over
        a ``total``-second window, or ``None`` while you're still speaking."""
        GLib.idle_add(self._set_countdown, remaining, total)

    def set_state(self, state: str, message: str = "") -> None:
        GLib.idle_add(self._set_state, state, message)

    def hide(self) -> None:
        GLib.idle_add(self._hide)

    def destroy(self) -> None:
        GLib.idle_add(self._destroy)

    # -- main-thread handlers -------------------------------------------------
    def _show(self, state: str, window_id: str | None) -> bool:
        self._cancel_hide()
        self._state = state
        self._phase_label = _PHASES.get(state, ((1, 1, 1), ""))[1]
        self._text = ""
        self._preset_icon = ""
        self._preset_name = ""
        self._keyword = ""
        self._levels = deque([0.0] * _BARS, maxlen=_BARS)
        self._disp = [0.0] * _BARS
        self._cd_deadline = None
        self._cd_frac = 0.0
        self._cd_alpha = 0.0
        self._anchor = caret.resolve(self.anchor_mode, window_id)
        self._relayout()
        self._visible = True
        self._win.show_all()
        if self._tick_id is None:
            self._tick_id = GLib.timeout_add(_FPS_MS, self._tick)
        return False

    def _set_level(self, level: float) -> bool:
        self._levels.append(max(0.0, min(1.0, level)))
        return False

    def _set_text(self, text: str) -> bool:
        if text == self._text:
            return False
        self._text = text
        self._relayout()
        self._area.queue_draw()
        return False

    def _set_preset(self, icon: str, name: str, keyword: str) -> bool:
        if (icon, name, keyword) == (self._preset_icon, self._preset_name, self._keyword):
            return False
        self._preset_icon = icon
        self._preset_name = name
        self._keyword = keyword
        self._relayout()
        self._area.queue_draw()
        return False

    def _set_countdown(self, remaining: float | None, total: float) -> bool:
        if remaining is None:
            self._cd_deadline = None
        else:
            self._cd_total = max(0.1, total)
            self._cd_deadline = time.time() + max(0.0, remaining)
        return False

    def _set_state(self, state: str, message: str) -> bool:
        self._state = state
        if state == "busy":
            # Honour a clean phase word from the caller ("Transcribing…",
            # "Rewriting…") so the overlay narrates what's happening; fall back to
            # the canned label otherwise.
            self._phase_label = (message.strip() or _PHASES["busy"][1])[:28]
        else:
            self._phase_label = _PHASES.get(state, ((1, 1, 1), message[:40]))[1] or message[:40]
        if state not in ("recording", "streaming"):
            # The countdown only makes sense while listening; drop it as soon as
            # we move on to transcribing / done / idle so the ring doesn't linger.
            self._cd_deadline = None
        self._update_input_region()   # enable/disable × hit area
        if state in ("recording", "streaming", "busy"):
            self._cancel_hide()
        elif state in ("done", "idle", "error"):
            # Linger on the final text, then fade out. Errors stay a touch longer.
            delay = 2500 if state == "error" else (1600 if self._text else 700)
            self._schedule_hide(delay)
        self._area.queue_draw()
        return False

    def _hide(self) -> bool:
        self._visible = False
        self._cancel_hide()
        if self._tick_id is not None:
            GLib.source_remove(self._tick_id)
            self._tick_id = None
        self._win.hide()
        return False

    def _destroy(self) -> bool:
        self._hide()
        self._win.destroy()
        return False

    # -- hide scheduling ------------------------------------------------------
    def _schedule_hide(self, delay_ms: int) -> None:
        self._cancel_hide()
        self._hide_id = GLib.timeout_add(delay_ms, self._hide)

    def _cancel_hide(self) -> None:
        if self._hide_id is not None:
            GLib.source_remove(self._hide_id)
            self._hide_id = None

    # -- animation ------------------------------------------------------------
    def _tick(self) -> bool:
        if not self._visible:
            self._tick_id = None
            return False
        # Ease displayed bars toward the latest levels for fluid motion even
        # though real levels arrive at ~10 Hz.
        targets = list(self._levels)
        for i, t in enumerate(targets):
            self._disp[i] += (t - self._disp[i]) * 0.35
        self._pulse = (math.sin((time.time() - self._t0) * 5.0) + 1.0) * 0.5
        # Drain the silence ring against its own clock so it stays smooth between
        # the ~10 Hz level samples. Fade in gently (so word gaps don't flash it)
        # and out a touch faster.
        if self._cd_deadline is not None:
            self._cd_frac = max(0.0, min(1.0, (self._cd_deadline - time.time()) / self._cd_total))
            self._cd_alpha += (1.0 - self._cd_alpha) * 0.15
        else:
            self._cd_alpha += (0.0 - self._cd_alpha) * 0.30
        self._area.queue_draw()
        return True

    # -- geometry -------------------------------------------------------------
    def _monitor_geo(self):
        disp = Gdk.Display.get_default()
        if self._anchor is not None:
            mon = disp.get_monitor_at_point(self._anchor.x, self._anchor.y)
        else:
            mon = disp.get_primary_monitor() or disp.get_monitor(0)
        return mon.get_geometry()

    def _text_height(self) -> int:
        if not self._text:
            return _MIN_TEXT_H
        layout = self._win.create_pango_layout(self._text)
        layout.set_width((_WIDTH - 2 * _PAD) * Pango.SCALE)
        layout.set_wrap(Pango.WrapMode.WORD_CHAR)
        font = Pango.FontDescription("Sans 11")
        layout.set_font_description(font)
        _w, h = layout.get_pixel_size()
        return min(_MAX_TEXT_H, max(_MIN_TEXT_H, h))

    def _relayout(self) -> None:
        text_h = self._text_height()
        preset_h = _PRESET_H if self._preset_name else 0
        gap_preset = 8 if preset_h else 0
        gap_text = 8 if text_h else 0
        body_h = _HEADER_H + gap_preset + preset_h + gap_text + text_h + 2 * _PAD
        self._height = body_h + _TAIL_H

        geo = self._monitor_geo()
        a = self._anchor
        ax = a.x if a else geo.x + geo.width // 2
        ay = a.y if a else geo.y + geo.height - 140
        ah = a.height if a else 0

        # Prefer placing the bubble above the anchor; flip below if it won't fit.
        above_y = ay - _GAP - self._height
        if above_y >= geo.y + 4:
            self._tail_up = False
            win_y = above_y
        else:
            self._tail_up = True
            win_y = ay + ah + _GAP

        tip_x = max(geo.x + _RADIUS + _TAIL_W, min(ax, geo.x + geo.width - _RADIUS - _TAIL_W))
        win_x = tip_x - _WIDTH // 2
        win_x = max(geo.x + 6, min(win_x, geo.x + geo.width - _WIDTH - 6))
        self._tail_x = tip_x - win_x

        self._win.resize(_WIDTH, self._height)
        self._win.move(int(win_x), int(win_y))
        self._area.set_size_request(_WIDTH, self._height)

        # X button: top-right corner of the bubble body.
        _body_top = _TAIL_H if self._tail_up else 0
        btn_d = _CANCEL_BTN_R * 2
        self._cancel_btn_rect = (
            _WIDTH - _PAD - btn_d, _body_top + _PAD // 2, btn_d, btn_d)
        self._update_input_region()

    # -- drawing --------------------------------------------------------------
    def _on_draw(self, _area, cr) -> bool:
        # Start fully transparent.
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        w = _WIDTH
        body_top = _TAIL_H if self._tail_up else 0
        body_h = self._height - _TAIL_H
        body_bottom = body_top + body_h

        # Bubble + tail as one path, so the fill/stroke wrap the tail cleanly.
        self._bubble_path(cr, 0, body_top, w, body_h)
        cr.set_source_rgba(0.10, 0.11, 0.14, 0.94)
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, 0.08)
        cr.set_line_width(1.0)
        cr.stroke()

        cx = _PAD + 14
        cy = body_top + _PAD + 12
        self._draw_mic(cr, cx, cy)
        self._draw_countdown(cr, cx, cy)

        # Waveform fills the space right of the mic across the header row.
        wf_x = cx + 26
        wf_w = w - _PAD - wf_x
        self._draw_wave(cr, wf_x, body_top + _PAD, wf_w, _HEADER_H)

        # × cancel button (top-right corner, recording/streaming/busy).
        if self._on_cancel_cb and self._state in ("recording", "streaming", "busy"):
            self._draw_cancel_btn(cr, body_top)

        # Phase label by the waveform — only when there's no preset banner and no text.
        # Shift left to leave room for the × button.
        label_right = (w - _PAD - _CANCEL_BTN_R * 2 - 6
                       if self._on_cancel_cb and self._state in ("recording", "streaming", "busy")
                       else w - _PAD)
        if self._phase_label and not self._text and not self._preset_name:
            self._draw_label(cr, label_right, body_top + _PAD + 12, self._phase_label)

        y = body_top + _PAD + _HEADER_H
        # Matched-preset banner: emoji + name (left), live phase chip (right).
        if self._preset_name:
            y += 8
            self._draw_preset(cr, _PAD, y, w - 2 * _PAD)
            y += _PRESET_H
        # Recognised / rewritten text below.
        if self._text:
            y += 8
            self._draw_text(cr, _PAD, y, w - 2 * _PAD)
        return False

    def _draw_preset(self, cr, x, y, w) -> None:
        """The matched voice-routing preset, fused onto the overlay in place of a
        desktop notification: emoji + name (and the spoken keyword) on the left,
        the current phase ("Transcribing…", "Rewriting…") on the right."""
        cy = y + _PRESET_H / 2
        cursor = x
        if self._preset_icon:
            ic = self._win.create_pango_layout(self._preset_icon)
            ic.set_font_description(Pango.FontDescription("Sans 13"))
            iw, ih = ic.get_pixel_size()
            cr.set_source_rgba(1, 1, 1, 0.95)
            cr.move_to(cursor, cy - ih / 2)
            PangoCairo.show_layout(cr, ic)
            cursor += iw + 7
        name = GLib.markup_escape_text(self._preset_name)
        if self._keyword:
            kw = GLib.markup_escape_text(self._keyword)
            markup = f'<b>{name}</b>  <span alpha="55%">“{kw}”</span>'
        else:
            markup = f"<b>{name}</b>"
        layout = self._win.create_pango_layout("")
        layout.set_markup(markup, -1)
        layout.set_font_description(Pango.FontDescription("Sans 10"))
        layout.set_ellipsize(Pango.EllipsizeMode.END)
        avail = (x + w) - cursor - 96      # leave room for the phase chip
        layout.set_width(max(40, avail) * Pango.SCALE)
        _nw, nh = layout.get_pixel_size()
        cr.set_source_rgba(0.95, 0.96, 0.99, 0.98)
        cr.move_to(cursor, cy - nh / 2)
        PangoCairo.show_layout(cr, layout)
        if self._phase_label:
            self._draw_label(cr, x + w, cy, self._phase_label)

    def _bubble_path(self, cr, x, y, w, h) -> None:
        r = _RADIUS
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
        cr.close_path()
        # Tail: a small triangle on the top or bottom edge at self._tail_x.
        tx = max(r + _TAIL_W, min(self._tail_x, w - r - _TAIL_W))
        if self._tail_up:
            cr.move_to(tx - _TAIL_W / 2, y)
            cr.line_to(tx, y - _TAIL_H)
            cr.line_to(tx + _TAIL_W / 2, y)
        else:
            cr.move_to(tx - _TAIL_W / 2, y + h)
            cr.line_to(tx, y + h + _TAIL_H)
            cr.line_to(tx + _TAIL_W / 2, y + h)
        cr.close_path()

    def _draw_mic(self, cr, cx, cy) -> None:
        colour, _ = _PHASES.get(self._state, ((1, 1, 1), ""))
        pulsing = self._state in ("recording", "streaming")
        # Soft pulsing halo while listening — but yield to the countdown ring as
        # it takes over (you've gone quiet, so the pulse fades out under it).
        if pulsing:
            rad = 12 + self._pulse * 6
            cr.set_source_rgba(*colour, 0.18 * (1 - self._pulse * 0.6) * (1 - self._cd_alpha))
            cr.arc(cx, cy, rad, 0, 2 * math.pi)
            cr.fill()
        cr.set_source_rgba(*colour, 1.0)
        cr.set_line_width(2.0)
        # Capsule head.
        head_w, head_top, head_bot = 9.0, cy - 11, cy + 1
        cr.arc(cx, head_top + head_w / 2, head_w / 2, math.pi, 2 * math.pi)
        cr.arc(cx, head_bot - head_w / 2, head_w / 2, 0, math.pi)
        cr.close_path()
        cr.fill()
        # Stand arc + post + base.
        cr.set_source_rgba(*colour, 0.95)
        cr.arc(cx, cy, 8, math.radians(25), math.radians(155))
        cr.stroke()
        cr.move_to(cx, cy + 8)
        cr.line_to(cx, cy + 12)
        cr.stroke()
        cr.move_to(cx - 5, cy + 12)
        cr.line_to(cx + 5, cy + 12)
        cr.stroke()

    def _draw_countdown(self, cr, cx, cy) -> None:
        """Silence auto-stop ring wrapping the mic: a full circle that drains
        clockwise as the trailing-silence timer runs out, recolouring from calm
        cyan to an urgent red just before it fires."""
        a = self._cd_alpha
        if a <= 0.01:
            return
        r, lw = 16.0, 2.6
        cr.set_line_width(lw)
        # Faint full track so the drained part of the ring stays legible.
        cr.set_source_rgba(1, 1, 1, 0.10 * a)
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.stroke()
        frac = self._cd_frac
        if frac <= 0.0:
            return
        spent = 1.0 - frac
        red = 0.30 + spent * 0.70
        grn = 0.80 - spent * 0.45
        blu = 0.90 - spent * 0.60
        cr.set_source_rgba(red, grn, blu, 0.95 * a)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        start = -math.pi / 2          # 12 o'clock
        cr.arc(cx, cy, r, start, start + frac * 2 * math.pi)
        cr.stroke()
        cr.set_line_cap(cairo.LINE_CAP_BUTT)

    def _draw_wave(self, cr, x, y, w, h) -> None:
        gap = 2.0
        bw = max(1.5, (w - gap * (_BARS - 1)) / _BARS)
        mid = y + h / 2
        listening = self._state in ("recording", "streaming")
        for i in range(_BARS):
            v = self._disp[i] if i < len(self._disp) else 0.0
            # Idle baseline shimmer so the meter never looks frozen.
            if listening and v < 0.04:
                v = 0.04 + 0.03 * math.sin((self._t0 - time.time()) * 4 + i * 0.5)
            bh = max(2.0, v * (h - 2))
            bx = x + i * (bw + gap)
            alpha = 0.85 if listening else 0.4
            cr.set_source_rgba(0.42, 0.62, 1.0, alpha)
            self._round_rect(cr, bx, mid - bh / 2, bw, bh, min(bw / 2, 2))
            cr.fill()

    def _draw_label(self, cr, right_x, cy, text) -> None:
        layout = self._win.create_pango_layout(text)
        layout.set_font_description(Pango.FontDescription("Sans 9"))
        tw, th = layout.get_pixel_size()
        cr.set_source_rgba(1, 1, 1, 0.55)
        cr.move_to(right_x - tw, cy - th / 2)
        PangoCairo.show_layout(cr, layout)

    def _draw_cancel_btn(self, cr, body_top) -> None:
        x, y, w, h = self._cancel_btn_rect
        cx_btn = x + w / 2
        cy_btn = y + h / 2
        cr.set_source_rgba(1, 1, 1, 0.15)
        cr.arc(cx_btn, cy_btn, _CANCEL_BTN_R, 0, 2 * math.pi)
        cr.fill()
        arm = _CANCEL_BTN_R * 0.45
        cr.set_source_rgba(1, 1, 1, 0.80)
        cr.set_line_width(1.8)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.move_to(cx_btn - arm, cy_btn - arm)
        cr.line_to(cx_btn + arm, cy_btn + arm)
        cr.stroke()
        cr.move_to(cx_btn + arm, cy_btn - arm)
        cr.line_to(cx_btn - arm, cy_btn + arm)
        cr.stroke()
        cr.set_line_cap(cairo.LINE_CAP_BUTT)

    def _draw_text(self, cr, x, y, w) -> None:
        layout = self._win.create_pango_layout(self._text)
        layout.set_width(w * Pango.SCALE)
        layout.set_wrap(Pango.WrapMode.WORD_CHAR)
        layout.set_ellipsize(Pango.EllipsizeMode.END)
        layout.set_height(_MAX_TEXT_H * Pango.SCALE)
        layout.set_font_description(Pango.FontDescription("Sans 11"))
        cr.set_source_rgba(0.95, 0.96, 0.99, 0.97)
        cr.move_to(x, y)
        PangoCairo.show_layout(cr, layout)

    @staticmethod
    def _round_rect(cr, x, y, w, h, r) -> None:
        r = min(r, w / 2, h / 2)
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
        cr.close_path()

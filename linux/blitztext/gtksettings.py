"""GTK settings dialog for Blitztext.

A functional editor for the engine, rewrite endpoint, and per-workflow prompts.
The richer presets manager + remote-engine controls build on this next.
"""

from __future__ import annotations

import os
import sys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from .config import Config, save  # noqa: E402

RESP_SAVE = 1
RESP_SAVE_RESTART = 2


def _row(parent: Gtk.Box, label: str) -> Gtk.Box:
    box = Gtk.Box(spacing=10)
    box.set_margin_top(4)
    box.set_margin_bottom(4)
    lbl = Gtk.Label(label=label, xalign=0.0)
    lbl.set_size_request(150, -1)
    box.pack_start(lbl, False, False, 0)
    parent.pack_start(box, False, False, 0)
    return box


def _entry(parent: Gtk.Box, label: str, value) -> Gtk.Entry:
    box = _row(parent, label)
    e = Gtk.Entry()
    e.set_text(str(value))
    e.set_hexpand(True)
    box.pack_start(e, True, True, 0)
    return e


def _combo(parent: Gtk.Box, label: str, value: str, options: list[str]) -> Gtk.ComboBoxText:
    box = _row(parent, label)
    c = Gtk.ComboBoxText()
    for i, o in enumerate(options):
        c.append_text(o)
        if o == value:
            c.set_active(i)
    if c.get_active() < 0:
        c.set_active(0)
    box.pack_start(c, False, False, 0)
    return c


def _page(nb: Gtk.Notebook, title: str) -> Gtk.Box:
    page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    page.set_margin_top(12)
    page.set_margin_bottom(12)
    page.set_margin_start(14)
    page.set_margin_end(14)
    nb.append_page(page, Gtk.Label(label=title))
    return page


class SettingsDialog:
    def __init__(self, parent: Gtk.Window, cfg: Config):
        self.cfg = cfg
        self.dlg = Gtk.Dialog(title="Blitztext — Settings", transient_for=parent, modal=True)
        self.dlg.set_default_size(580, 580)
        self.dlg.add_button("Close", Gtk.ResponseType.CLOSE)
        self.dlg.add_button("Save", RESP_SAVE)
        self.dlg.add_button("Save & Restart", RESP_SAVE_RESTART)

        nb = Gtk.Notebook()
        self.dlg.get_content_area().pack_start(nb, True, True, 0)

        # Engine
        p = _page(nb, "Engine")
        self.e_model = _entry(p, "Whisper model", cfg.model)
        self.e_device = _combo(p, "Device", cfg.device, ["auto", "cpu", "cuda"])
        self.e_compute = _combo(p, "Compute type", cfg.compute_type, ["auto", "int8", "float16", "int8_float16"])
        self.e_lang = _entry(p, "Language hint", cfg.language)
        self.e_output = _combo(p, "Output", cfg.output, ["type", "paste"])
        self.e_delay = _entry(p, "Type delay (ms)", cfg.type_delay_ms)
        nbox = _row(p, "Notifications")
        self.e_notify = Gtk.Switch()
        self.e_notify.set_active(cfg.notify)
        self.e_notify.set_halign(Gtk.Align.START)
        nbox.pack_start(self.e_notify, False, False, 0)

        # Rewrite
        p = _page(nb, "Rewrite LLM")
        self.r_url = _entry(p, "Base URL", cfg.base_url)
        self.r_keyenv = _entry(p, "API key env var", cfg.api_key_env)
        self.r_model = _entry(p, "Model", cfg.rewrite_model)
        self.r_temp = _entry(p, "Temperature", cfg.temperature)
        self.r_timeout = _entry(p, "Timeout (s)", cfg.timeout)
        hint = Gtk.Label(xalign=0.0, wrap=True)
        hint.set_markup(
            f'<small>OpenAI-compatible endpoint (OpenAI, vLLM, llama-swap…). '
            f'Env <tt>{cfg.api_key_env}</tt>: '
            f'{"set ✓" if cfg.api_key else "NOT set"}.</small>'
        )
        p.pack_start(hint, False, False, 8)

        # Per-workflow prompts
        self.wf_widgets: list[dict] = []
        for wf in cfg.workflows:
            p = _page(nb, wf.name[:14])
            w = {
                "name": _entry(p, "Name", wf.name),
                "description": _entry(p, "Description", wf.description),
                "hotkey": _entry(p, "Hotkey", wf.hotkey),
                "model": _entry(p, "Model (opt.)", wf.model or ""),
                "temperature": _entry(p, "Temp (opt.)", "" if wf.temperature is None else wf.temperature),
                "mode": _combo(p, "Mode", wf.mode, ["transcribe", "rewrite"]),
            }
            p.pack_start(Gtk.Label(label="Rewrite prompt (system):", xalign=0.0), False, False, 6)
            sw = Gtk.ScrolledWindow()
            sw.set_min_content_height(150)
            sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            tv = Gtk.TextView()
            tv.set_wrap_mode(Gtk.WrapMode.WORD)
            tv.get_buffer().set_text(wf.prompt)
            sw.add(tv)
            p.pack_start(sw, True, True, 0)
            w["prompt"] = tv
            self.wf_widgets.append(w)

        self.dlg.connect("response", self._on_response)

    # -- helpers --------------------------------------------------------------
    @staticmethod
    def _tv_text(tv: Gtk.TextView) -> str:
        b = tv.get_buffer()
        return b.get_text(b.get_start_iter(), b.get_end_iter(), True).strip()

    def _collect(self) -> bool:
        try:
            c = self.cfg
            c.model = self.e_model.get_text().strip()
            c.device = self.e_device.get_active_text()
            c.compute_type = self.e_compute.get_active_text()
            c.language = self.e_lang.get_text().strip()
            c.output = self.e_output.get_active_text()
            c.type_delay_ms = int(self.e_delay.get_text())
            c.notify = self.e_notify.get_active()
            c.base_url = self.r_url.get_text().strip().rstrip("/")
            c.api_key_env = self.r_keyenv.get_text().strip()
            c.rewrite_model = self.r_model.get_text().strip()
            c.temperature = float(self.r_temp.get_text())
            c.timeout = int(self.r_timeout.get_text())
            for wf, w in zip(c.workflows, self.wf_widgets):
                wf.name = w["name"].get_text().strip() or wf.name
                wf.description = w["description"].get_text().strip()
                wf.hotkey = w["hotkey"].get_text().strip()
                wf.model = w["model"].get_text().strip() or None
                t = w["temperature"].get_text().strip()
                wf.temperature = float(t) if t else None
                wf.mode = w["mode"].get_active_text()
                wf.prompt = self._tv_text(w["prompt"])
        except ValueError as exc:
            self._error(f"Check numeric fields: {exc}")
            return False
        return True

    def _error(self, msg: str) -> None:
        d = Gtk.MessageDialog(transient_for=self.dlg, modal=True,
                              message_type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.OK, text=msg)
        d.run()
        d.destroy()

    def _info(self, msg: str) -> None:
        d = Gtk.MessageDialog(transient_for=self.dlg, modal=True,
                              message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.OK, text=msg)
        d.run()
        d.destroy()

    def _on_response(self, dlg: Gtk.Dialog, resp: int) -> None:
        if resp == RESP_SAVE:
            if self._collect():
                save(self.cfg)
                self._info("Saved. Restart Blitztext to apply hotkey/model changes.")
            return
        if resp == RESP_SAVE_RESTART:
            if self._collect():
                save(self.cfg)
                os.execv(sys.executable, [sys.executable, "-m", "blitztext", "tray"])
            return
        dlg.destroy()

    def run_dialog(self) -> None:
        self.dlg.show_all()

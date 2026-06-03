"""tkinter control panel for Blitztext — a Linux analogue of the macOS menu bar.

A minimal, flat design: clickable workflow rows with hover, a single status dot,
and the Ubuntu font throughout. Global hotkeys keep working in the background, so
the panel is optional once it's running.
"""

from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk

from . import __version__
from .config import Config, load, save
from .daemon import Daemon

# --- palette (light, minimal) ------------------------------------------------
WIN = "#ffffff"
TEXT = "#1a1a1c"
SUBTLE = "#8e8e93"
FAINT = "#b8b8be"
HOVER = "#f5f5f7"
LINE = "#ececee"
ACCENT = "#0a84ff"
GREEN = "#34c759"
RED = "#ff3b30"
AMBER = "#ff9f0a"

DOT = {"loading": AMBER, "idle": GREEN, "recording": RED, "busy": AMBER, "done": GREEN, "error": RED}
DOT_LABEL = {"loading": "Loading…", "idle": "Ready", "recording": "Recording",
             "busy": "Working…", "done": "Ready", "error": "Error"}

_FONT = "TkDefaultFont"
_MONO = "TkFixedFont"


def _pick_fonts(root: tk.Tk) -> None:
    """Apply the nicest available UI/mono fonts to the default named fonts."""
    global _FONT, _MONO
    fams = set(tkfont.families(root))
    for f in ("Ubuntu", "Cantarell", "Noto Sans", "DejaVu Sans"):
        if f in fams:
            _FONT = f
            break
    for f in ("Ubuntu Mono", "DejaVu Sans Mono", "Noto Sans Mono"):
        if f in fams:
            _MONO = f
            break
    if _FONT != "TkDefaultFont":
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
            try:
                tkfont.nametofont(name).configure(family=_FONT, size=11)
            except tk.TclError:
                pass


def pretty_hotkey(hotkey: str) -> str:
    names = {"<ctrl>": "Ctrl", "<alt>": "Alt", "<shift>": "Shift", "<cmd>": "Super", "<space>": "Space"}
    parts = []
    for raw in hotkey.split("+"):
        inner = raw.strip("<>")
        parts.append(names.get(raw, inner.upper() if len(inner) == 1 else inner.title()))
    return " ".join(parts)


class Row:
    """One clickable workflow row."""

    def __init__(self, app: "BlitztextGUI", parent: tk.Widget, wf):
        self.app = app
        self.wf = wf
        self.dimmed = False

        self.frame = tk.Frame(parent, bg=WIN, cursor="hand2")
        self.frame.pack(fill="x")
        self.strip = tk.Frame(self.frame, bg=WIN, width=3)
        self.strip.pack(side="left", fill="y")

        body = tk.Frame(self.frame, bg=WIN)
        body.pack(side="left", fill="x", expand=True, padx=(18, 16), pady=11)

        top = tk.Frame(body, bg=WIN)
        top.pack(fill="x")
        self.name = tk.Label(top, text=wf.name, font=(_FONT, 13), bg=WIN, fg=TEXT, anchor="w")
        self.name.pack(side="left")
        self.hint = tk.Label(top, text=pretty_hotkey(wf.hotkey), font=(_MONO, 9), bg=WIN, fg=FAINT, anchor="e")
        self.hint.pack(side="right")

        self.desc = None
        if wf.description:
            self.desc = tk.Label(body, text=wf.description, font=(_FONT, 9), bg=WIN, fg=SUBTLE, anchor="w")
            self.desc.pack(fill="x")

        self._widgets = [self.frame, body, top, self.name, self.hint] + ([self.desc] if self.desc else [])
        for w in self._widgets:
            w.bind("<Button-1>", lambda _e: self.app.on_row_click(self))
            w.bind("<Enter>", lambda _e: self._hover(True))
            w.bind("<Leave>", lambda _e: self._hover(False))

    def _paint(self, bg: str) -> None:
        for w in self._widgets:
            w.configure(bg=bg)

    def _hover(self, on: bool) -> None:
        if self.dimmed or not self.app.daemon.ready:
            return
        self._paint(HOVER if on else WIN)
        self.strip.configure(bg=HOVER if on else WIN)

    def set_idle(self) -> None:
        self.dimmed = False
        self._paint(WIN)
        self.strip.configure(bg=WIN)
        self.name.configure(fg=TEXT)
        if self.desc:
            self.desc.configure(fg=SUBTLE)
        self.hint.configure(text=pretty_hotkey(self.wf.hotkey), fg=FAINT)

    def set_recording(self) -> None:
        self.dimmed = False
        self._paint(WIN)
        self.strip.configure(bg=RED)
        self.name.configure(fg=TEXT)
        if self.desc:
            self.desc.configure(fg=SUBTLE)
        self.hint.configure(text="● Stop", fg=RED)

    def set_busy(self) -> None:
        self.hint.configure(text="Working…", fg=AMBER)

    def set_dimmed(self) -> None:
        self.dimmed = True
        self._paint(WIN)
        self.strip.configure(bg=WIN)
        self.name.configure(fg=FAINT)
        if self.desc:
            self.desc.configure(fg=FAINT)
        self.hint.configure(fg=FAINT)


class BlitztextGUI:
    def __init__(self, cfg: Config, tray_mode: bool = False):
        self.cfg = cfg
        self.tray_mode = tray_mode
        self.tray = None
        self.daemon = Daemon(cfg, status_cb=self._status_cb)
        self._events: queue.Queue = queue.Queue()
        self._rows: list[Row] = []
        self._active: str | None = None

        self.root = tk.Tk()
        self.root.title("Blitztext")
        self.root.configure(bg=WIN)
        _pick_fonts(self.root)
        self.root.minsize(380, 320)

        self._build_header()
        tk.Frame(self.root, bg=LINE, height=1).pack(fill="x", padx=22)
        self._build_rows()
        tk.Frame(self.root, bg=LINE, height=1).pack(fill="x", padx=22)
        self._build_footer()

        self.root.after(80, self._drain_events)
        threading.Thread(target=self._startup, daemon=True).start()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # -- startup --------------------------------------------------------------
    def _startup(self) -> None:
        try:
            self.daemon.prepare()
            self.daemon.start_hotkeys()
        except Exception as exc:  # noqa: BLE001
            self._events.put(("error", None, f"Startup failed: {exc}"))

    # -- layout ---------------------------------------------------------------
    def _build_header(self) -> None:
        head = tk.Frame(self.root, bg=WIN)
        head.pack(fill="x", padx=22, pady=(20, 14))
        tk.Label(head, text="Blitztext", font=(_FONT, 17), bg=WIN, fg=TEXT).pack(side="left")
        wrap = tk.Frame(head, bg=WIN)
        wrap.pack(side="right")
        self.dot = tk.Label(wrap, text="●", font=(_FONT, 10), bg=WIN, fg=AMBER)
        self.dot.pack(side="left", padx=(0, 5))
        self.status_label = tk.Label(wrap, text="Starting…", font=(_FONT, 11), bg=WIN, fg=SUBTLE)
        self.status_label.pack(side="left")

    def _build_rows(self) -> None:
        body = tk.Frame(self.root, bg=WIN)
        body.pack(fill="both", expand=True, padx=8, pady=6)
        for wf in self.cfg.workflows:
            self._rows.append(Row(self, body, wf))

    def _build_footer(self) -> None:
        foot = tk.Frame(self.root, bg=WIN)
        foot.pack(fill="x", padx=22, pady=(12, 16))
        tk.Label(foot, text=f"v{__version__}", font=(_FONT, 9), bg=WIN, fg=FAINT).pack(side="left")
        self._text_button(foot, "Quit", self.quit_all).pack(side="right")
        self._text_button(foot, "Settings", self.open_settings).pack(side="right", padx=(0, 18))

    def _text_button(self, parent, label, cmd) -> tk.Label:
        b = tk.Label(parent, text=label, font=(_FONT, 11), bg=WIN, fg=ACCENT, cursor="hand2")
        b.bind("<Button-1>", lambda _e: cmd())
        b.bind("<Enter>", lambda _e: b.configure(fg=TEXT))
        b.bind("<Leave>", lambda _e: b.configure(fg=ACCENT))
        return b

    # -- interaction ----------------------------------------------------------
    def on_row_click(self, row: Row) -> None:
        if not self.daemon.ready or self.daemon._busy:
            return
        if self._active and row.wf.name != self._active:
            return  # another workflow is recording
        self.trigger_workflow(row.wf)

    def trigger_workflow(self, wf) -> None:
        if not self.daemon.ready:
            return
        threading.Thread(target=lambda: self.daemon.toggle(wf), daemon=True).start()

    # -- status plumbing (thread-safe via queue) ------------------------------
    def _status_cb(self, state: str, workflow: str | None, message: str) -> None:
        self._events.put((state, workflow, message))

    def _drain_events(self) -> None:
        try:
            while True:
                self._apply_status(*self._events.get_nowait())
        except queue.Empty:
            pass
        self.root.after(80, self._drain_events)

    def _apply_status(self, state: str, workflow: str | None, message: str) -> None:
        label = DOT_LABEL.get(state, message) or message
        self.dot.configure(fg=DOT.get(state, SUBTLE))
        self.status_label.configure(text=label)
        if self.tray is not None:
            self.tray.update_status(state, label)

        if state == "recording":
            self._active = workflow
            for r in self._rows:
                r.set_recording() if r.wf.name == workflow else r.set_dimmed()
        elif state == "busy":
            for r in self._rows:
                if r.wf.name == workflow:
                    r.set_busy()
                else:
                    r.set_dimmed()
        elif state == "loading":
            for r in self._rows:
                r.set_dimmed()
        else:  # idle / done / error
            self._active = None
            for r in self._rows:
                r.set_idle()
            if state == "error" and message:
                self.status_label.configure(text=message[:42], fg=RED)

    # -- settings / panel -----------------------------------------------------
    def open_settings(self) -> None:
        SettingsWindow(self.root, self.cfg)

    def show_panel(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide_panel(self) -> None:
        self.root.withdraw()

    # -- lifecycle ------------------------------------------------------------
    def _on_close(self) -> None:
        if self.tray is not None:
            self.hide_panel()
        else:
            self.quit_all()

    def quit_all(self) -> None:
        try:
            self.daemon.stop_hotkeys()
        finally:
            self.root.destroy()

    def _pump_gtk(self) -> None:
        if self.tray is not None:
            self.tray.pump()
        self.root.after(50, self._pump_gtk)

    def run(self) -> None:
        if self.tray_mode:
            from . import tray as tray_mod

            if tray_mod.gi_available():
                self.tray = tray_mod.Tray(self)
                self.root.withdraw()
                self._pump_gtk()
            else:
                print(tray_mod.INSTALL_HINT, file=sys.stderr)
                self.tray_mode = False
        self.root.mainloop()


class SettingsWindow:
    """Edit config and save. Hotkey/model changes apply after a restart."""

    def __init__(self, parent: tk.Misc, cfg: Config):
        self.cfg = cfg
        self.win = tk.Toplevel(parent)
        self.win.title("Blitztext — Settings")
        self.win.configure(bg=WIN)
        self.win.minsize(560, 500)

        style = ttk.Style(self.win)
        try:
            style.configure("TNotebook", background=WIN, borderwidth=0)
            style.configure("TNotebook.Tab", padding=(14, 7), font=(_FONT, 10))
        except tk.TclError:
            pass

        nb = ttk.Notebook(self.win)
        nb.pack(fill="both", expand=True, padx=14, pady=14)

        self.vars: dict[str, tk.Variable] = {}
        self._build_general(nb)
        self._build_rewrite(nb)
        self.prompt_texts: dict[int, tk.Text] = {}
        self.wf_vars: dict[int, dict[str, tk.Variable]] = {}
        for idx, wf in enumerate(cfg.workflows):
            self._build_workflow_tab(nb, idx, wf)

        bar = tk.Frame(self.win, bg=WIN)
        bar.pack(fill="x", padx=14, pady=(0, 14))
        save_btn = tk.Label(bar, text="Save & Restart", font=(_FONT, 11), bg=ACCENT, fg="white",
                            padx=14, pady=7, cursor="hand2")
        save_btn.bind("<Button-1>", lambda _e: self._save_restart())
        save_btn.pack(side="right")
        save2 = tk.Label(bar, text="Save", font=(_FONT, 11), bg=HOVER, fg=TEXT, padx=14, pady=7, cursor="hand2")
        save2.bind("<Button-1>", lambda _e: self._save())
        save2.pack(side="right", padx=8)
        tk.Label(bar, text="Hotkey & model changes apply after restart.",
                 font=(_FONT, 9), bg=WIN, fg=SUBTLE).pack(side="left")

    def _field(self, parent, label, value, key):
        frame = tk.Frame(parent, bg=WIN)
        frame.pack(fill="x", padx=16, pady=6)
        tk.Label(frame, text=label, font=(_FONT, 10), bg=WIN, fg=TEXT, width=16, anchor="w").pack(side="left")
        var = tk.StringVar(value=str(value))
        self.vars[key] = var
        tk.Entry(frame, textvariable=var, font=(_FONT, 10), relief="solid", bd=1,
                 highlightthickness=0).pack(side="left", fill="x", expand=True, ipady=3)
        return var

    def _combo(self, parent, label, value, options, key):
        frame = tk.Frame(parent, bg=WIN)
        frame.pack(fill="x", padx=16, pady=6)
        tk.Label(frame, text=label, font=(_FONT, 10), bg=WIN, fg=TEXT, width=16, anchor="w").pack(side="left")
        var = tk.StringVar(value=value)
        self.vars[key] = var
        ttk.Combobox(frame, textvariable=var, values=options, state="readonly", width=18).pack(side="left")
        return var

    def _build_general(self, nb):
        tab = tk.Frame(nb, bg=WIN)
        nb.add(tab, text="Engine")
        self._field(tab, "Whisper model", self.cfg.model, "model")
        self._combo(tab, "Device", self.cfg.device, ["auto", "cpu", "cuda"], "device")
        self._combo(tab, "Compute type", self.cfg.compute_type, ["auto", "int8", "float16", "int8_float16"], "compute_type")
        self._field(tab, "Language hint", self.cfg.language, "language")
        self._combo(tab, "Output", self.cfg.output, ["type", "paste"], "output")
        self._field(tab, "Type delay (ms)", self.cfg.type_delay_ms, "type_delay_ms")
        nv = tk.BooleanVar(value=self.cfg.notify)
        self.vars["notify"] = nv
        f = tk.Frame(tab, bg=WIN)
        f.pack(fill="x", padx=16, pady=6)
        tk.Checkbutton(f, text="Desktop notifications", variable=nv, bg=WIN, fg=TEXT,
                       font=(_FONT, 10), activebackground=WIN, selectcolor=WIN).pack(side="left")

    def _build_rewrite(self, nb):
        tab = tk.Frame(nb, bg=WIN)
        nb.add(tab, text="Rewrite LLM")
        self._field(tab, "Base URL", self.cfg.base_url, "base_url")
        self._field(tab, "API key env var", self.cfg.api_key_env, "api_key_env")
        self._field(tab, "Model", self.cfg.rewrite_model, "rewrite_model")
        self._field(tab, "Temperature", self.cfg.temperature, "temperature")
        self._field(tab, "Timeout (s)", self.cfg.timeout, "timeout")
        present = "set ✓" if self.cfg.api_key else "NOT set"
        tk.Label(tab, text=f"OpenAI-compatible endpoint (OpenAI, vLLM, llama-swap…). "
                           f"Env {self.cfg.api_key_env}: {present}.",
                 font=(_FONT, 9), bg=WIN, fg=SUBTLE, wraplength=500, justify="left").pack(fill="x", padx=16, pady=(10, 0))

    def _build_workflow_tab(self, nb, idx, wf):
        tab = tk.Frame(nb, bg=WIN)
        nb.add(tab, text=wf.name[:14])
        v: dict[str, tk.Variable] = {}
        self.wf_vars[idx] = v
        for label, key, val in [("Name", "name", wf.name),
                                ("Description", "description", wf.description),
                                ("Hotkey", "hotkey", wf.hotkey),
                                ("Model (opt.)", "model", wf.model or ""),
                                ("Temp (opt.)", "temperature", "" if wf.temperature is None else wf.temperature)]:
            frame = tk.Frame(tab, bg=WIN)
            frame.pack(fill="x", padx=16, pady=5)
            tk.Label(frame, text=label, font=(_FONT, 10), bg=WIN, fg=TEXT, width=14, anchor="w").pack(side="left")
            sv = tk.StringVar(value=str(val))
            v[key] = sv
            tk.Entry(frame, textvariable=sv, font=(_FONT, 10), relief="solid", bd=1,
                     highlightthickness=0).pack(side="left", fill="x", expand=True, ipady=3)

        mframe = tk.Frame(tab, bg=WIN)
        mframe.pack(fill="x", padx=16, pady=5)
        tk.Label(mframe, text="Mode", font=(_FONT, 10), bg=WIN, fg=TEXT, width=14, anchor="w").pack(side="left")
        mv = tk.StringVar(value=wf.mode)
        v["mode"] = mv
        ttk.Combobox(mframe, textvariable=mv, values=["transcribe", "rewrite"], state="readonly", width=14).pack(side="left")

        tk.Label(tab, text="Rewrite prompt (system):", font=(_FONT, 10), bg=WIN, fg=TEXT, anchor="w").pack(fill="x", padx=16, pady=(10, 2))
        txt = tk.Text(tab, height=9, wrap="word", font=(_FONT, 10), relief="solid", bd=1, highlightthickness=0)
        txt.insert("1.0", wf.prompt)
        txt.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        self.prompt_texts[idx] = txt

    def _collect(self) -> bool:
        try:
            self.cfg.model = self.vars["model"].get().strip()
            self.cfg.device = self.vars["device"].get()
            self.cfg.compute_type = self.vars["compute_type"].get()
            self.cfg.language = self.vars["language"].get().strip()
            self.cfg.output = self.vars["output"].get()
            self.cfg.type_delay_ms = int(self.vars["type_delay_ms"].get())
            self.cfg.notify = bool(self.vars["notify"].get())
            self.cfg.base_url = self.vars["base_url"].get().strip().rstrip("/")
            self.cfg.api_key_env = self.vars["api_key_env"].get().strip()
            self.cfg.rewrite_model = self.vars["rewrite_model"].get().strip()
            self.cfg.temperature = float(self.vars["temperature"].get())
            self.cfg.timeout = int(self.vars["timeout"].get())
            for idx, wf in enumerate(self.cfg.workflows):
                v = self.wf_vars[idx]
                wf.name = v["name"].get().strip() or wf.name
                wf.description = v["description"].get().strip()
                wf.hotkey = v["hotkey"].get().strip()
                wf.mode = v["mode"].get()
                wf.model = v["model"].get().strip() or None
                temp = v["temperature"].get().strip()
                wf.temperature = float(temp) if temp else None
                wf.prompt = self.prompt_texts[idx].get("1.0", "end").strip()
        except ValueError as exc:
            messagebox.showerror("Invalid value", f"Check numeric fields: {exc}", parent=self.win)
            return False
        return True

    def _save(self) -> None:
        if not self._collect():
            return
        save(self.cfg)
        messagebox.showinfo("Saved", "Settings saved. Restart Blitztext to apply hotkey/model changes.", parent=self.win)

    def _save_restart(self) -> None:
        if not self._collect():
            return
        save(self.cfg)
        os.execv(sys.executable, [sys.executable, "-m", "blitztext", "tray"])


def run_gui(tray_mode: bool = False) -> int:
    cfg = load()
    BlitztextGUI(cfg, tray_mode=tray_mode).run()
    return 0

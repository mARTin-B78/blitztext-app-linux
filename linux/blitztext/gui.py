"""tkinter control panel for Blitztext — a Linux analogue of the macOS menu bar.

Shows the workflow list with per-row Record buttons and a live status dot, plus
a Settings window to edit hotkeys, the Whisper engine, the rewrite endpoint, and
each workflow's prompt. Global hotkeys keep working in the background, so the
panel is optional once it's running.
"""

from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from . import __version__
from .config import Config, load, save
from .daemon import Daemon

# Light palette, loosely matching the macOS panel.
BG = "#ececf1"
CARD = "#ffffff"
TEXT = "#1c1c1e"
MUTED = "#8a8a8e"
BADGE = "#e3e3e8"
DIVIDER = "#d8d8de"
AVATAR_COLORS = ["#0a84ff", "#34c759", "#ff9f0a", "#ff375f", "#bf5af2", "#5ac8fa"]
DOT = {
    "loading": "#ff9f0a",
    "idle": "#34c759",
    "recording": "#ff3b30",
    "busy": "#ff9f0a",
    "done": "#34c759",
    "error": "#ff3b30",
}
DOT_LABEL = {
    "loading": "Loading model…",
    "idle": "Ready",
    "recording": "Recording…",
    "busy": "Working…",
    "done": "Ready",
    "error": "Error",
}


def pretty_hotkey(hotkey: str) -> str:
    names = {"<ctrl>": "Ctrl", "<alt>": "Alt", "<shift>": "Shift", "<cmd>": "Super", "<space>": "Space"}
    parts = []
    for raw in hotkey.split("+"):
        parts.append(names.get(raw, raw.strip("<>").upper() if len(raw.strip("<>")) == 1 else raw.strip("<>").title()))
    return "+".join(parts)


class BlitztextGUI:
    def __init__(self, cfg: Config, tray_mode: bool = False):
        self.cfg = cfg
        self.tray_mode = tray_mode
        self.tray = None
        self.daemon = Daemon(cfg, status_cb=self._status_cb)
        self._events: queue.Queue = queue.Queue()
        self._active_wf: str | None = None
        self._row_buttons: dict[str, tk.Button] = {}

        self.root = tk.Tk()
        self.root.title("Blitztext")
        self.root.configure(bg=BG)
        self.root.minsize(420, 360)
        self._build_header()
        self._build_rows()
        self._build_footer()

        # Disable controls until the model is loaded.
        self._set_buttons_enabled(False)
        self.root.after(80, self._drain_events)

        # Load model + start hotkeys off the UI thread.
        threading.Thread(target=self._startup, daemon=True).start()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # -- startup --------------------------------------------------------------
    def _startup(self) -> None:
        try:
            self.daemon.prepare()
            self.daemon.start_hotkeys()
        except Exception as exc:  # noqa: BLE001
            self._events.put(("error", None, f"Startup failed: {exc}"))

    # -- header ---------------------------------------------------------------
    def _build_header(self) -> None:
        head = tk.Frame(self.root, bg=BG)
        head.pack(fill="x", padx=16, pady=(14, 8))
        tk.Label(head, text="Blitztext", font=("", 15, "bold"), bg=BG, fg=TEXT).pack(side="left")

        status = tk.Frame(head, bg=BG)
        status.pack(side="right")
        self.dot = tk.Label(status, text="●", font=("", 12), bg=BG, fg=DOT["loading"])
        self.dot.pack(side="left")
        self.status_label = tk.Label(status, text="Starting…", font=("", 11), bg=BG, fg=MUTED)
        self.status_label.pack(side="left", padx=(4, 0))

    # -- workflow rows --------------------------------------------------------
    def _build_rows(self) -> None:
        body = tk.Frame(self.root, bg=CARD, highlightthickness=1, highlightbackground=DIVIDER)
        body.pack(fill="both", expand=True, padx=12, pady=4)
        for i, wf in enumerate(self.cfg.workflows):
            if i:
                tk.Frame(body, bg=DIVIDER, height=1).pack(fill="x", padx=12)
            row = tk.Frame(body, bg=CARD)
            row.pack(fill="x", padx=12, pady=8)

            color = AVATAR_COLORS[i % len(AVATAR_COLORS)]
            avatar = tk.Canvas(row, width=32, height=32, bg=CARD, highlightthickness=0)
            avatar.create_oval(3, 3, 29, 29, fill=color, outline="")
            avatar.create_text(16, 16, text=(wf.name[:1] or "?").upper(), fill="white", font=("", 13, "bold"))
            avatar.pack(side="left", padx=(0, 10))

            mid = tk.Frame(row, bg=CARD)
            mid.pack(side="left", fill="x", expand=True)
            tk.Label(mid, text=wf.name, font=("", 12, "bold"), bg=CARD, fg=TEXT, anchor="w").pack(fill="x")
            sub = wf.description or ("Transcribe only" if wf.mode == "transcribe" else "Transcribe → rewrite")
            tk.Label(mid, text=sub, font=("", 10), bg=CARD, fg=MUTED, anchor="w").pack(fill="x")

            badge = tk.Label(row, text=pretty_hotkey(wf.hotkey), font=("", 9), bg=BADGE, fg=MUTED, padx=6, pady=2)
            badge.pack(side="left", padx=8)

            btn = tk.Button(
                row, text="● Rec", font=("", 10, "bold"), width=7,
                relief="flat", bg="#e8453c", fg="white", activebackground="#c93b33", activeforeground="white",
                command=lambda w=wf: self._on_record(w),
            )
            btn.pack(side="right")
            self._row_buttons[wf.name] = btn

    # -- footer ---------------------------------------------------------------
    def _build_footer(self) -> None:
        foot = tk.Frame(self.root, bg=BG)
        foot.pack(fill="x", padx=16, pady=(6, 12))
        tk.Label(foot, text=f"recorder: {self.daemon.recorder_name}  ·  v{__version__}",
                 font=("", 9), bg=BG, fg=MUTED).pack(side="left")
        tk.Button(foot, text="Quit", font=("", 10), relief="flat", bg=BADGE, fg=TEXT,
                  command=self.quit_all).pack(side="right")
        tk.Button(foot, text="Settings", font=("", 10), relief="flat", bg=BADGE, fg=TEXT,
                  command=self.open_settings).pack(side="right", padx=6)

    # -- record button --------------------------------------------------------
    def _on_record(self, wf) -> None:
        self.trigger_workflow(wf)

    def trigger_workflow(self, wf) -> None:
        """Start/stop a workflow (from a row button or the tray menu)."""
        if not self.daemon.ready:
            return
        threading.Thread(target=lambda: self.daemon.toggle(wf), daemon=True).start()

    def _set_buttons_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for btn in self._row_buttons.values():
            btn.configure(state=state)

    # -- status plumbing (thread-safe via queue) ------------------------------
    def _status_cb(self, state: str, workflow: str | None, message: str) -> None:
        self._events.put((state, workflow, message))

    def _drain_events(self) -> None:
        try:
            while True:
                state, workflow, message = self._events.get_nowait()
                self._apply_status(state, workflow, message)
        except queue.Empty:
            pass
        self.root.after(80, self._drain_events)

    def _apply_status(self, state: str, workflow: str | None, message: str) -> None:
        label = DOT_LABEL.get(state, message) or message
        self.dot.configure(fg=DOT.get(state, MUTED))
        self.status_label.configure(text=label)
        if self.tray is not None:
            self.tray.update_status(state, label)

        if state == "recording":
            self._active_wf = workflow
            for name, btn in self._row_buttons.items():
                if name == workflow:
                    btn.configure(text="■ Stop", state="normal")
                else:
                    btn.configure(state="disabled")
        elif state in ("busy", "loading"):
            self._set_buttons_enabled(False)
        elif state in ("idle", "done", "error"):
            self._active_wf = None
            for btn in self._row_buttons.values():
                btn.configure(text="● Rec", state="normal")
            if state == "error" and message:
                self.status_label.configure(text=message[:48])

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
        # In tray mode the window close button just hides to the tray.
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
                self.root.withdraw()  # live in the tray; panel opens on demand
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
        self.win.configure(bg=BG)
        self.win.minsize(560, 480)

        nb = ttk.Notebook(self.win)
        nb.pack(fill="both", expand=True, padx=10, pady=10)

        self.vars: dict[str, tk.Variable] = {}
        self._build_general(nb)
        self._build_rewrite(nb)
        self.prompt_texts: dict[int, tk.Text] = {}
        self.wf_vars: dict[int, dict[str, tk.Variable]] = {}
        for idx, wf in enumerate(cfg.workflows):
            self._build_workflow_tab(nb, idx, wf)

        bar = tk.Frame(self.win, bg=BG)
        bar.pack(fill="x", padx=10, pady=(0, 10))
        tk.Button(bar, text="Save & Restart", font=("", 10, "bold"), relief="flat",
                  bg="#0a84ff", fg="white", command=self._save_restart).pack(side="right")
        tk.Button(bar, text="Save", font=("", 10), relief="flat", bg=BADGE, fg=TEXT,
                  command=self._save).pack(side="right", padx=6)
        tk.Label(bar, text="Hotkey & model changes apply after restart.",
                 font=("", 9), bg=BG, fg=MUTED).pack(side="left")

    def _field(self, parent, label, value, key, width=42):
        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill="x", padx=14, pady=5)
        tk.Label(frame, text=label, font=("", 10), bg=BG, fg=TEXT, width=16, anchor="w").pack(side="left")
        var = tk.StringVar(value=str(value))
        self.vars[key] = var
        tk.Entry(frame, textvariable=var, width=width).pack(side="left", fill="x", expand=True)
        return var

    def _build_general(self, nb):
        tab = tk.Frame(nb, bg=BG)
        nb.add(tab, text="Engine")
        self._field(tab, "Whisper model", self.cfg.model, "model")
        self._combo(tab, "Device", self.cfg.device, ["auto", "cpu", "cuda"], "device")
        self._combo(tab, "Compute type", self.cfg.compute_type, ["auto", "int8", "float16", "int8_float16"], "compute_type")
        self._field(tab, "Language hint", self.cfg.language, "language")
        self._combo(tab, "Output", self.cfg.output, ["type", "paste"], "output")
        self._field(tab, "Type delay (ms)", self.cfg.type_delay_ms, "type_delay_ms")
        nv = tk.BooleanVar(value=self.cfg.notify)
        self.vars["notify"] = nv
        f = tk.Frame(tab, bg=BG); f.pack(fill="x", padx=14, pady=5)
        tk.Checkbutton(f, text="Desktop notifications", variable=nv, bg=BG, fg=TEXT,
                       activebackground=BG, selectcolor=CARD).pack(side="left")

    def _build_rewrite(self, nb):
        tab = tk.Frame(nb, bg=BG)
        nb.add(tab, text="Rewrite LLM")
        self._field(tab, "Base URL", self.cfg.base_url, "base_url")
        self._field(tab, "API key env var", self.cfg.api_key_env, "api_key_env")
        self._field(tab, "Model", self.cfg.rewrite_model, "rewrite_model")
        self._field(tab, "Temperature", self.cfg.temperature, "temperature")
        self._field(tab, "Timeout (s)", self.cfg.timeout, "timeout")
        present = "set ✓" if self.cfg.api_key else "NOT set"
        tk.Label(tab, text=f"OpenAI-compatible endpoint (OpenAI, vLLM, llama-swap…). "
                           f"Env {self.cfg.api_key_env}: {present}.",
                 font=("", 9), bg=BG, fg=MUTED, wraplength=500, justify="left").pack(fill="x", padx=14, pady=(8, 0))

    def _build_workflow_tab(self, nb, idx, wf):
        tab = tk.Frame(nb, bg=BG)
        nb.add(tab, text=wf.name[:14])
        v: dict[str, tk.Variable] = {}
        self.wf_vars[idx] = v
        for label, key, val in [("Name", "name", wf.name),
                                ("Description", "description", wf.description),
                                ("Hotkey", "hotkey", wf.hotkey),
                                ("Model (opt.)", "model", wf.model or ""),
                                ("Temp (opt.)", "temperature", "" if wf.temperature is None else wf.temperature)]:
            frame = tk.Frame(tab, bg=BG); frame.pack(fill="x", padx=14, pady=4)
            tk.Label(frame, text=label, font=("", 10), bg=BG, fg=TEXT, width=14, anchor="w").pack(side="left")
            sv = tk.StringVar(value=str(val))
            v[key] = sv
            tk.Entry(frame, textvariable=sv).pack(side="left", fill="x", expand=True)

        mframe = tk.Frame(tab, bg=BG); mframe.pack(fill="x", padx=14, pady=4)
        tk.Label(mframe, text="Mode", font=("", 10), bg=BG, fg=TEXT, width=14, anchor="w").pack(side="left")
        mv = tk.StringVar(value=wf.mode); v["mode"] = mv
        ttk.Combobox(mframe, textvariable=mv, values=["transcribe", "rewrite"], state="readonly", width=14).pack(side="left")

        tk.Label(tab, text="Rewrite prompt (system):", font=("", 10), bg=BG, fg=TEXT, anchor="w").pack(fill="x", padx=14, pady=(8, 2))
        txt = tk.Text(tab, height=10, wrap="word")
        txt.insert("1.0", wf.prompt)
        txt.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        self.prompt_texts[idx] = txt

    def _combo(self, parent, label, value, options, key):
        frame = tk.Frame(parent, bg=BG); frame.pack(fill="x", padx=14, pady=5)
        tk.Label(frame, text=label, font=("", 10), bg=BG, fg=TEXT, width=16, anchor="w").pack(side="left")
        var = tk.StringVar(value=value); self.vars[key] = var
        ttk.Combobox(frame, textvariable=var, values=options, state="readonly", width=18).pack(side="left")
        return var

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
        os.execv(sys.executable, [sys.executable, "-m", "blitztext", "gui"])


def run_gui(tray_mode: bool = False) -> int:
    cfg = load()
    BlitztextGUI(cfg, tray_mode=tray_mode).run()
    return 0

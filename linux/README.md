# Blitztext for Linux (native dictation)

A native Linux port of the Blitztext workflow: **focus any text field → press a
hotkey → speak → the text is typed into that field**, optionally rewritten by an
LLM first (e.g. turn rough speech into a nicer, more detailed email).

This runs **on the host** (not in a container), so it can type into *any*
application — the Linux equivalent of the macOS app's Accessibility-based
auto-paste. (A sandboxed Docker/browser version can't do that; an earlier
experiment along those lines was moved out to
`~/Docker/correspondence/blitztext`.) Transcription is **local** via
[faster-whisper]; only the optional rewrite step calls out to an LLM.

## How it works

```
hotkey ──▶ record mic (pw-record/arecord) ──▶ faster-whisper (local)
                                                    │
                          ┌── mode "transcribe" ────┤
                          │                          └── mode "rewrite": LLM (OpenAI-compatible)
                          ▼
                 xdotool types it into the focused window
```

Each hotkey **toggles**: press to start recording, press again to stop — then it
transcribes, optionally rewrites, and types the result where your cursor is.

## Requirements

- **X11 session** (this uses `xdotool`; Wayland would need `ydotool`/`wtype`).
- Host tools: `xdotool`, `notify-send` (libnotify-bin), and a recorder
  (`pw-record` from pipewire, or `arecord`/`parecord`).
  ```bash
  sudo apt install xdotool libnotify-bin pipewire-bin
  ```
- Python 3.11+.

## Install

```bash
cd linux
./install.sh
```

This creates `.venv`, installs `faster-whisper` + `pynput`, and writes the
default config to `~/.config/blitztext/config.toml`.

## Run

Three front-ends, same engine (local Whisper + global hotkeys + xdotool typing):

```bash
# optional: only needed for the "rewrite" workflows
export OPENAI_API_KEY=sk-...

.venv/bin/python -m blitztext tray   # system-tray menu (macOS-menu-bar-like, default)
.venv/bin/python -m blitztext gui    # control-panel window
.venv/bin/python -m blitztext run    # headless, hotkeys only
```

### System tray (recommended)

The tray is the closest match to the macOS menu-bar app: a status icon with a
menu listing every workflow (click to record), plus **Show panel**, **Settings…**,
and **Quit**. It needs PyGObject once (the GTK/AppIndicator typelibs and the
GNOME `ubuntu-appindicators` extension are already present here):

```bash
sudo apt install python3-gi      # one-time; no build, just the bindings
.venv/bin/python -m blitztext tray
```

If PyGObject is missing, `tray` prints this hint and falls back to the window.
(The venv is created with `--system-site-packages` so it can see the
apt-installed `gi`.)

Either way, focus any text field and trigger a workflow — by tray menu, panel
button, or hotkey (defaults):

| Hotkey                  | Workflow      | What it does                              |
| ----------------------- | ------------- | ----------------------------------------- |
| `Ctrl+Alt+Space`        | Transcribe    | Types the raw transcript                  |
| `Ctrl+Alt+E`            | Nicer email   | Rewrites speech into a polished email     |
| `Ctrl+Alt+I`            | Improve text  | Proofreads / improves wording             |
| `Ctrl+Alt+C`            | Calm down     | Rewrites an angry message into a calm one |
| `Ctrl+Alt+J`            | Add emojis    | Adds fitting emojis                       |

## Configuration

Everything lives in `~/.config/blitztext/config.toml` (`python -m blitztext
config-path` prints the location). You can change hotkeys, the Whisper model, and
the rewrite endpoint, and add/edit `[[workflow]]` blocks with your own prompts.

### Local Whisper

```toml
[whisper]
model = "small"      # tiny|base|small|medium|large-v3, or a local model path
device = "auto"      # auto tries cuda, falls back to cpu
compute_type = "auto"
```

> On this arm64 host the pip `ctranslate2` wheel is **CPU-only**, so it runs on
> the Grace CPU with `int8`. That's fast for dictation (≈2s for a 10s clip with
> `small`). `device = "auto"` attempts CUDA and falls back automatically — to get
> GPU you'd need a CUDA-enabled CTranslate2 build for aarch64/sm_121.

### Rewrite endpoint (OpenAI *or* your local LLM)

```toml
[rewrite]
base_url = "https://api.openai.com/v1"   # or e.g. http://localhost:8000/v1 for vLLM/llama-swap
api_key_env = "OPENAI_API_KEY"
model = "gpt-4o-mini"
```

Point `base_url` at a local OpenAI-compatible server (vLLM, llama-swap) to keep
rewriting fully on-box too.

## Run on login

See [`blitztext.service`](blitztext.service) for a systemd **user** unit.

## Verified

On this machine (Ubuntu/GNOME, X11, GB10): recorder → valid 16 kHz WAV;
faster-whisper CPU transcription accurate; config + all hotkeys parse; and
`xdotool` typing of German text into a focused GTK field. The live global-hotkey
loop and the LLM rewrite HTTP call were not auto-tested here (the former hijacks
the keyboard during a session; the latter needs your key) — try them with the
`run` command above.

## CLI

```bash
python -m blitztext tray               # tray menu (default)
python -m blitztext gui                # control-panel window
python -m blitztext run                # headless daemon, hotkeys only
python -m blitztext transcribe f.wav   # one-shot, prints text (no hotkeys)
python -m blitztext config-path        # print config location
```

[faster-whisper]: https://github.com/SYSTRAN/faster-whisper

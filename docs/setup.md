# Setup

This guide is for people who want to build and inspect Blitztext App Linux themselves.

## 1. Requirements

- Linux desktop with an X11 session
- Python 3.11+
- `xdotool`
- `notify-send` from `libnotify-bin`
- one recorder: `pw-record`, `parecord`, or `arecord`
- GTK/PyGObject for the tray and settings UI (`python3-gi` on Ubuntu/Debian)
- Optional rewrite workflows: an OpenAI-compatible chat endpoint and API key if needed
- Optional realtime STT streaming: a Riva/NIM realtime server such as Nemotron ASR Streaming

On Ubuntu/Debian:

```bash
sudo apt install xdotool libnotify-bin pipewire-bin python3-gi
```

## 2. Clone And Install

```bash
git clone https://github.com/mARTin-B78/blitztext-app-linux.git
cd blitztext-app-linux/linux
./install.sh
```

If your local repository still uses the older `blitztext-app` name, the commands are the same once you `cd linux`.

## 3. Run

```bash
.venv/bin/python -m blitztext tray
```

Alternatives:

```bash
.venv/bin/python -m blitztext gui
.venv/bin/python -m blitztext run
.venv/bin/python -m blitztext config-path
```

## 4. Debian Package

```bash
cd linux
bash packaging/build-deb.sh
sudo apt install ./dist/blitztext_*.deb
blitztext tray
```

The package installs Blitztext under `/opt/blitztext`, adds a desktop entry, and bundles the Python dependencies from `requirements.txt`.

## 5. Configure STT Engines

Open **Settings > Engines**.

Common options:

- `local`: in-process `faster-whisper`
- `openai`: OpenAI-compatible batch `/audio/transcriptions` endpoint
- `riva_realtime`: Riva/NIM realtime WebSocket transcription for `mode = "stream"`

For Nemotron ASR Streaming:

```toml
[[stt_engine]]
name = "Nemotron ASR Streaming"
type = "riva_realtime"
url = "http://127.0.0.1:8006/v1"
model = ""
```

Then create or edit a workflow with:

```toml
mode = "stream"
```

## 6. Configure Rewrite Workflows

Rewrite workflows use an OpenAI-compatible chat endpoint. You can point them at OpenAI, LiteLLM, llama-swap, vLLM, LM Studio, or another compatible server.

For OpenAI:

```bash
export OPENAI_API_KEY=your-api-key-here
```

Then set the LLM engine in **Settings > Engines** or edit `~/.config/blitztext/config.toml`.

Never commit API keys into this repository, issues, logs, or screenshots.

## 7. Permissions And Desktop Session

Blitztext needs microphone access through your Linux audio stack and uses `xdotool` to type into the currently focused X11 window.

If text delivery does not work:

- confirm you are on X11, not Wayland
- check that `xdotool getactivewindow` works in a terminal
- focus a normal text field before triggering a workflow
- try `output = "paste"` or `output = "type"` in config

## Troubleshooting

- If the tray does not start, confirm `python3-gi` is visible to the venv. `install.sh` uses `--system-site-packages` for this reason.
- If local Whisper is slow on arm64, use a smaller model such as `small`, `base`, or `tiny`.
- If realtime streaming connects but produces poor text, confirm the server language. The tested Nemotron ASR Streaming NIM is `en-US`.
- If a batch STT endpoint returns `bad model`, check whether it is actually a streaming-only NIM. Use `riva_realtime` for realtime services and `openai` only for batch-compatible services.
- If audio is missing, check the selected microphone in **Settings > General** and watch the input level meter.
- If rewriting fails, verify your LLM endpoint, model name, API key environment variable, and account billing if using a cloud provider.

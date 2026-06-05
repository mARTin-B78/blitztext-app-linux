# Blitztext App Linux

Blitztext App Linux is a native Linux dictation and writing assistant. Focus any
text field, trigger a workflow, speak, and Blitztext types the result back into
the application you were already using.

It can type a plain transcript, rewrite rough speech with an OpenAI-compatible
LLM, route spoken commands to different workflows, benchmark STT engines, and
stream live words from a Riva/NIM realtime speech server.

This is a host desktop app, not a browser app and not a hosted service. The
current Linux version is built around GTK, AppIndicator, global hotkeys,
`faster-whisper`, optional OpenAI-compatible endpoints, optional Riva/NIM
realtime STT, and `xdotool` text delivery.

> Status: experimental Linux/X11 app. Bring your own local models or endpoints.
> No hosted Blitztext backend is included.

## Inspiration

Blitztext App Linux is inspired by
[cmagnussen/blitztext-app](https://github.com/cmagnussen/blitztext-app), the
original macOS menu-bar app for turning speech into text and cleaner writing.
This repository keeps the spirit of that workflow while implementing a
Linux-native version with Linux desktop APIs and Linux-friendly model backends.

## Features

- **Native Linux tray app**: run Blitztext from the system tray, open the GTK
  control panel, or run it headless with global hotkeys only.
- **Plain dictation**: record speech, transcribe it, and type the raw text into
  the focused X11 window.
- **Rewrite workflows**: turn rough speech into a nicer email, improved text, a
  calmer message, emoji-rich text, or any custom prompt you define.
- **Realtime STT streaming**: use a `riva_realtime` STT engine, such as
  Nemotron ASR Streaming, to type stable words while you are still speaking.
- **Voice-keyword routing**: use one routing hotkey and say a workflow keyword
  at the start or end of your speech to choose the preset.
- **Two input styles**: use direct workflow hotkeys, or the modifier workflow:
  Ctrl+Super to start, Ctrl to stop and type, Alt to stop/type/send, Esc to
  cancel.
- **Push-to-talk option**: hold the start modifier to record and release it to
  finish.
- **Multiple STT engines**: local `faster-whisper`, OpenAI-compatible batch STT
  endpoints, and Riva/NIM realtime WebSocket STT.
- **Multiple LLM engines**: OpenAI-compatible chat endpoints for OpenAI, local
  vLLM, llama-swap, Ollama `/v1`, LM Studio, Groq, OpenRouter, and similar
  servers.
- **STT benchmark tab**: compare configured STT engines against a reference WAV
  and transcript.
- **Settings UI**: edit workflows, engines, input mode, microphone, language,
  benchmark files, autostart, logs, and About metadata.
- **About page**: shows the app version, source repository, changelog, license,
  and legal notes.
- **Debian package**: build a local `.deb` with the launcher, icon, bundled
  Python environment, and system dependency declarations.

## How It Works

```text
Batch workflows
---------------
focused app -> global hotkey -> record mic -> STT engine
                                      |
                                      +-> mode "transcribe" -> type/paste text
                                      |
                                      +-> mode "rewrite" -> LLM -> type/paste text

Realtime workflow
-----------------
focused app -> stream workflow -> mic PCM chunks -> Riva/NIM WebSocket
                                               |
                                               +-> stable partial text -> xdotool
```

Blitztext remembers the focused X11 window when recording starts, then delivers
the final text back to that window. Delivery can be direct typing or clipboard
paste, depending on your configuration.

## Requirements

- Linux desktop running an **X11 session**.
- Python 3.11+ when running from source.
- `xdotool` for text delivery.
- `notify-send` from `libnotify-bin` for desktop notifications.
- One recorder: `pw-record`, `parecord`, or `arecord`.
- `python3-gi` and AppIndicator/Ayatana typelibs for the GTK tray.
- Optional: CUDA-capable `faster-whisper`/CTranslate2 setup for GPU local STT.
- Optional: an OpenAI-compatible chat endpoint for rewrite workflows.
- Optional: a Riva/NIM realtime server for live streaming STT.

On Ubuntu/Debian:

```bash
sudo apt install xdotool libnotify-bin pipewire-bin python3-gi
```

Wayland is not the primary target yet. The current app uses `xdotool`, so use an
X11 session for reliable typing into other applications.

## Install

### Debian Package

The recommended Ubuntu/Debian path is to build and install the local package:

```bash
cd linux
bash packaging/build-deb.sh
sudo apt install ./dist/blitztext_*.deb
```

This installs Blitztext under `/opt/blitztext`, adds a desktop launcher, installs
the app icon, and provides the `blitztext` command.

Start it with:

```bash
blitztext tray
```

### From Source

```bash
cd linux
./install.sh
.venv/bin/python -m blitztext tray
```

`install.sh` creates a virtual environment with `--system-site-packages` so the
app can see the system `python3-gi` package used by GTK/AppIndicator.

## Run

```bash
blitztext tray          # tray app with workflow menu, default installed mode
blitztext gui           # GTK control panel
blitztext run           # headless hotkey daemon
blitztext config-path   # print config file path
blitztext --version     # print app version
```

From a source checkout, use:

```bash
cd linux
.venv/bin/python -m blitztext tray
.venv/bin/python -m blitztext gui
.venv/bin/python -m blitztext run
.venv/bin/python -m blitztext transcribe sample.wav
```

## Default Workflows

| Workflow | Mode | Default trigger | Result |
| --- | --- | --- | --- |
| Transcribe | `transcribe` | voice-routing default | Types the raw transcript |
| Nicer email | `rewrite` | `Ctrl+Alt+E` | Turns rough notes into a polished email |
| Improve text | `rewrite` | `Ctrl+Alt+I` | Cleans spelling, grammar, and wording |
| Calm down | `rewrite` | `Ctrl+Alt+C` | Rewrites frustrated speech into a calm message |
| Add emojis | `rewrite` | `Ctrl+Alt+J` | Keeps the text and adds fitting emojis |
| STT Streaming | `stream` | user-created / optional | Types live words from realtime STT |

The default config uses voice-keyword routing as the primary input style. Press
the routing hotkey, speak normally, and optionally say a preset keyword such as
"nicer email" or "calm down" at the beginning or end of the utterance.

## Configuration

Blitztext writes its configuration to:

```text
~/.config/blitztext/config.toml
```

You can edit it through **Settings** or directly as TOML. The settings window
contains:

- **Presets**: workflow name, icon, description, mode, hotkey, keywords, prompt,
  model override, and temperature override.
- **Engines**: STT and LLM engine presets, status checks, and STT test.
- **Input**: modifier mode, direct hotkey mode, push-to-talk, microphone, output
  method, typing delay, language, and quality gates.
- **General**: notifications, autostart, and app behavior.
- **Benchmark**: compare STT engines with a reference WAV and text file.
- **Log**: inspect runtime messages.
- **About**: version, changelog, source, license, and legal information.

## STT Engines

Local transcription uses `faster-whisper`:

```toml
[stt]
active = "Local faster-whisper"

[[stt_engine]]
name = "Local faster-whisper"
type = "local"

[whisper]
model = "small"
device = "auto"
compute_type = "auto"
beam_size = 5
```

Batch remote transcription uses OpenAI-compatible `/audio/transcriptions`
servers:

```toml
[[stt_engine]]
name = "faster-whisper-server"
type = "openai"
url = "http://localhost:8010/v1"
model = "Systran/faster-whisper-base"
api_key_env = ""
```

Realtime streaming uses a Riva/NIM realtime WebSocket server:

```toml
[[stt_engine]]
name = "Nemotron ASR Streaming"
type = "riva_realtime"
url = "http://127.0.0.1:8006/v1"
model = ""
api_key_env = ""
```

Streaming engines are live-only. They are used by workflows with
`mode = "stream"`, not by batch transcription or the benchmark tab.

## Realtime STT Streaming

To use Nemotron ASR Streaming or another compatible Riva/NIM realtime server:

1. Start the realtime STT server.
2. Open **Settings > Engines**.
3. Click **+ Stream** to add the Nemotron ASR Streaming preset.
4. Save and restart Blitztext if prompted.
5. Create or edit a workflow with `mode = "stream"`.

Example:

```toml
[general]
language = "en-US"

[stt]
active = "Nemotron ASR Streaming"

[[workflow]]
name = "STT Streaming"
description = "Live words while you speak."
hotkey = "<ctrl>+<alt>+s"
mode = "stream"
```

The tested Nemotron ASR Streaming NIM exposes an English `en-US` model. For that
server, use `language = "en"` or `language = "en-US"`.

## Rewrite Engines

Rewrite workflows send the transcript to an OpenAI-compatible chat endpoint:

```toml
[llm]
active = "Default"

[[llm_engine]]
name = "Default"
type = "cloud"
url = "https://api.openai.com/v1"
model = "gpt-4o-mini"
api_key_env = "OPENAI_API_KEY"
temperature = 0.3
```

For local rewriting, point the URL at a local OpenAI-compatible server:

```toml
[[llm_engine]]
name = "Local llama-swap"
type = "local"
url = "http://localhost:28080/v1"
model = "Qwen3.5-4B"
api_key_env = ""
temperature = 0.3
```

## Privacy

Blitztext App Linux does not include a hosted backend. Where your audio or text
goes depends on the engines you configure:

```text
Local STT:              your desktop -> local faster-whisper
Remote batch STT:       your desktop -> configured /audio/transcriptions endpoint
Realtime STT:           your desktop -> configured Riva/NIM realtime endpoint
Rewrite workflows:      your desktop -> configured OpenAI-compatible chat endpoint
Text delivery:          Blitztext -> xdotool -> focused X11 window
```

Do not use remote endpoints with sensitive content unless you understand and
accept the data handling of those services. See [docs/privacy.md](docs/privacy.md)
for more detail.

## Project Structure

```text
linux/
  blitztext/      Linux app package: GTK UI, tray, daemon, STT, LLM, config
  packaging/      Debian packaging, desktop file, app icons
  README.md       Detailed Linux usage guide
  CHANGELOG.md    Linux app changelog
docs/             Setup, privacy, roadmap, release, and project notes
BlitztextMac/     Legacy/upstream macOS reference code kept for context
README.md         This Linux-first project overview
```

## Development

Useful checks:

```bash
cd linux
.venv/bin/python -m py_compile blitztext/*.py
.venv/bin/python -m blitztext --version
.venv/bin/python -m blitztext config-path
```

Useful docs:

- [linux/README.md](linux/README.md) for the detailed Linux guide.
- [docs/setup.md](docs/setup.md) for setup notes.
- [linux/CHANGELOG.md](linux/CHANGELOG.md) for app changes.
- [ROADMAP.md](ROADMAP.md) for planned work.
- [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.

## Current Limits

- X11 is required for reliable text delivery through `xdotool`.
- Realtime streaming depends on a compatible Riva/NIM realtime server.
- Rewrite workflows depend on the LLM endpoint you configure.
- Local STT speed depends on your `faster-whisper` model, CPU/GPU, and
  CTranslate2 build.
- This is experimental open-source software provided as-is.

## License

Code is released under the MIT License. See [LICENSE](LICENSE).

Project names, logos, and app icons are not automatically granted as trademarks
or brand assets. See [TRADEMARKS.md](TRADEMARKS.md).

## Legal / Impressum & Datenschutz

This is an experimental, non-commercial open-source project, provided as-is under
the MIT License without warranty or support. Nothing is sold here and no
installation or operation is performed on your behalf.

The companion website (blitztext.de) is operated by Blackboat Internet GmbH:

- Impressum: https://martin-bierschenk.de/impressum/
- Datenschutz / Privacy: https://martin-bierschenk.de/datenschutz/

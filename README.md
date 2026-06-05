# Blitztext App Linux

Blitztext App Linux is an experimental open-source Linux dictation app: focus any text field, press a hotkey, speak, and the text is typed back into the app you were using. It can also rewrite rough speech with an OpenAI-compatible LLM, or write live words through a Riva/NIM realtime STT server.

This is a native host tool, not a browser app and not a hosted service. It is intentionally small, inspectable, and still rough around the edges.

> Preview status: Linux/X11, bring your own local models or endpoints, no hosted Blitztext backend, no warranty, no support guarantee.

## Inspiration

Blitztext App Linux is inspired by [cmagnussen/blitztext-app](https://github.com/cmagnussen/blitztext-app), the original macOS menu-bar workflow for turning speech into text and cleaner writing. This Linux version keeps the spirit of that workflow while using Linux-native pieces: GTK, AppIndicator, global hotkeys, local `faster-whisper`, optional Riva/NIM realtime STT, and `xdotool` delivery.

## What It Does

- **Dictate**: record speech and type the raw transcript into the focused field.
- **Rewrite**: transcribe speech, send it to an OpenAI-compatible LLM, and type the improved result.
- **Calm down / email / emoji workflows**: use configurable prompts for common writing transformations.
- **Realtime STT streaming**: stream mic audio to a Riva/NIM realtime server, such as Nemotron ASR Streaming, and type stable words while you speak.
- **Benchmark STT engines**: compare local and remote batch transcription engines against a reference clip.

## Important Preview Notes

- Linux first; tested on Ubuntu/GNOME with X11.
- Auto-typing uses `xdotool`, so Wayland needs future `wtype`/`ydotool` support.
- Batch transcription can run locally with `faster-whisper`.
- Live streaming can use a local Riva/NIM realtime WebSocket endpoint.
- Rewrite workflows call the OpenAI-compatible LLM endpoint you configure.
- No hosted Blitztext backend is included or provided.
- Debian packaging exists for local installation, but this is still preview software.
- No warranty and no support guarantee.

You are welcome to use, fork, adapt, and share this project under the license terms.

The intent is not to ship a one-click finished product. The intent is to make a real AI workflow understandable: clone it, build it, read the code, change it, break it, fix it, and suggest improvements. If you only want to download something and never look inside, this preview will probably feel rough. If you want to learn how a small native Linux AI dictation tool is put together, you are in the right place.

## Screenshots

The old macOS screenshots were removed from this Linux-facing README so the docs do not misrepresent the app. Current Linux screenshots should show:

- the GTK control panel with workflow rows
- Settings > Engines with local, OpenAI-compatible, and `riva_realtime` STT engines
- Settings > Benchmark results
- Settings > About with version, source, changelog, and license

The Linux icon assets live in [`linux/packaging`](linux/packaging/).

## Requirements

- Linux desktop with an **X11 session**.
- Host tools: `xdotool`, `notify-send` from `libnotify-bin`, and one recorder: `pw-record`, `parecord`, or `arecord`.
- Python 3.11+ when running from source.
- Optional rewrite workflows: an OpenAI-compatible chat endpoint and API key if needed.
- Optional realtime STT streaming: a Riva/NIM realtime server reachable through `/v1/realtime`.

On Ubuntu/Debian:

```bash
sudo apt install xdotool libnotify-bin pipewire-bin python3-gi
```

## Install And Run

Recommended local package path:

```bash
cd linux
bash packaging/build-deb.sh
sudo apt install ./dist/blitztext_*.deb
blitztext tray
```

Run from source:

```bash
cd linux
./install.sh
.venv/bin/python -m blitztext tray
```

Other entry points:

```bash
.venv/bin/python -m blitztext gui
.venv/bin/python -m blitztext run
.venv/bin/python -m blitztext config-path
.venv/bin/python -m blitztext --version
```

For the full Linux guide, see [linux/README.md](linux/README.md). For setup details, see [docs/setup.md](docs/setup.md).

## Data Flow

The preview has no custom backend.

```text
Batch transcription:    Your Linux desktop -> local faster-whisper or your configured STT endpoint
Realtime streaming:     Your Linux desktop -> your configured Riva/NIM realtime endpoint
Text rewriting:         Your Linux desktop -> your configured OpenAI-compatible chat endpoint
Text delivery:          Blitztext -> xdotool -> focused X11 window
```

Read [docs/privacy.md](docs/privacy.md) before using the preview with sensitive content.

## Project Structure

```text
linux/
  blitztext/      Linux app package: GTK UI, daemon, STT/LLM engines, config
  packaging/      Debian package script, desktop entry, icon assets
  README.md       Detailed Linux guide
BlitztextMac/     Legacy/upstream macOS app code kept for reference
build.sh          Legacy macOS build script
README.md         Linux-first project overview
docs/             Setup, privacy, roadmap, release notes, web brief
```

## Configuration

Blitztext writes configuration to:

```text
~/.config/blitztext/config.toml
```

The Settings window can edit workflows, STT engines, LLM engines, input mode, microphone, language, benchmark clips, and About metadata. You can also edit the TOML directly.

## Realtime STT Streaming

For Nemotron ASR Streaming, add a realtime engine in **Settings > Engines** with `+ Stream`, save/restart, then create or edit a workflow with `mode = "stream"`.

```toml
[[stt_engine]]
name = "Nemotron ASR Streaming"
type = "riva_realtime"
url = "http://127.0.0.1:8006/v1"
model = ""

[[workflow]]
name = "STT Streaming"
hotkey = "<ctrl>+<alt>+s"
mode = "stream"
```

The tested Nemotron ASR Streaming NIM exposes an English `en-US` model, so use `language = "en"` or `language = "en-US"` in `[general]` for that engine.

## Contributing

Contributions are welcome, especially if they make the preview easier to build, understand, test, or fork.

Please read [CONTRIBUTING.md](CONTRIBUTING.md) first.

## Support And Roadmap

This preview has no formal support promise. See [SUPPORT.md](SUPPORT.md) for how to ask for help without sharing secrets.

The current direction is documented in [ROADMAP.md](ROADMAP.md). Maintainer-facing release checks live in [docs/open-source-preflight.md](docs/open-source-preflight.md).

## License

Code is released under the MIT License. See [LICENSE](LICENSE).

Project names, logos, and app icons are not automatically granted as trademarks or brand assets. See [TRADEMARKS.md](TRADEMARKS.md).

## Legal / Impressum & Datenschutz

This is an experimental, non-commercial open-source project, provided as-is under the MIT License without warranty or support. Nothing is sold here and no installation or operation is performed on your behalf.

The companion website (blitztext.de) is operated by Blackboat Internet GmbH:

- Impressum: https://martin-bierschenk.de/impressum/
- Datenschutz / Privacy: https://martin-bierschenk.de/datenschutz/

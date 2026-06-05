# Local And Realtime Speech Models

Blitztext App Linux supports two local-first speech paths:

- in-process `faster-whisper` for batch transcription
- external Riva/NIM realtime servers for live streaming transcription

The app does not bundle speech models. You choose the model in Settings or in `~/.config/blitztext/config.toml`.

## Local Batch Transcription

The default local engine uses `faster-whisper`.

Recommended first model:

```toml
[whisper]
model = "small"
device = "auto"
compute_type = "auto"
```

Useful model sizes:

- `tiny`: fastest, lowest quality
- `base`: small and responsive
- `small`: good first default for dictation
- `medium`: better quality, slower
- `large-v3`: highest quality, much heavier

You can also use a local model path supported by `faster-whisper`.

## Realtime Riva/NIM Transcription

For live words while speaking, use a `riva_realtime` STT engine. The tested Nemotron ASR Streaming NIM exposes a WebSocket endpoint through `/v1/realtime` and reports this model:

```text
cache-aware-parakeet-rnnt-en-US-asr-streaming-sortformer
```

Recommended engine config:

```toml
[[stt_engine]]
name = "Nemotron ASR Streaming"
type = "riva_realtime"
url = "http://127.0.0.1:8006/v1"
model = ""
```

Use `model = ""` to keep the server default. For the tested Nemotron container, set the general language to English:

```toml
[general]
language = "en"
```

## Batch NIMs And Other STT Servers

Use `type = "openai"` only for servers that implement batch `/v1/audio/transcriptions` correctly.

Example:

```toml
[[stt_engine]]
name = "Parakeet batch ASR"
type = "openai"
url = "http://127.0.0.1:8090/v1"
model = "parakeet-tdt-0.6b-v3"
```

Streaming-only NIMs may still show `/v1/audio/transcriptions` in Swagger, but return `bad model` or `No Offline ASR models found`. Use `riva_realtime` for those.

## Notes

- First local Whisper use can be slower because the model has to load or download.
- Realtime streaming needs `sounddevice` and `websockets`; both are in `linux/requirements.txt`.
- The benchmark tab is for batch engines. Streaming engines are live-only and are not benchmarked with WAV uploads.

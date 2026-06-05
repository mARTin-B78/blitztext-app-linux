# Privacy Notes

Blitztext App Linux does not include a hosted backend.

Data goes only to the engines and endpoints you configure:

- local `faster-whisper` for local batch transcription
- your configured OpenAI-compatible STT endpoint for remote batch transcription
- your configured Riva/NIM realtime endpoint for streaming transcription
- your configured OpenAI-compatible chat endpoint for rewriting workflows

You are responsible for API access, billing, endpoint security, and data handling for any remote or local service you connect.

## Local Data

The app stores:

- workflow, hotkey, engine, model, microphone, and UI settings in `~/.config/blitztext/config.toml`
- temporary audio files while a batch transcription is being processed; the app attempts to delete each recording when the workflow ends or is cancelled
- local Python dependencies in the source venv or bundled package venv

Blitztext does not store API keys itself. Instead, config entries name environment variables such as `OPENAI_API_KEY`; you provide those variables in your shell, service, or desktop environment.

Workflow output may be typed directly into the focused X11 window or placed on the clipboard, depending on the configured output mode. Clipboard managers and other apps may observe clipboard contents while they are present.

## Network Data Flow

```text
Local batch STT:      microphone -> temporary WAV -> local faster-whisper
Remote batch STT:     microphone -> temporary WAV -> configured /audio/transcriptions endpoint
Realtime STT:         microphone PCM chunks -> configured Riva/NIM realtime WebSocket endpoint
Rewrite workflows:    transcript text -> configured OpenAI-compatible chat endpoint
Delivery:             generated text -> xdotool / clipboard -> focused app
```

The app uses your system trust store for HTTPS connections made by Python libraries. It does not pin certificates.

## Offline Scope

Batch transcription can run locally with `faster-whisper`. Realtime transcription can be local if your Riva/NIM server is local. Rewriting is local only if you configure a local OpenAI-compatible LLM endpoint.

Do not describe a workflow as fully offline unless every configured endpoint is local and you have verified the network path.

## Sensitive Content

Do not use this preview with confidential, regulated, or highly sensitive content unless you have reviewed the code, your local services, your remote provider settings, and your legal/privacy requirements.

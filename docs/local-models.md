# Local Models

Blitztext can run transcription locally with WhisperKit/CoreML. The app does not bundle a speech model, but it can download the selected compatible model from Hugging Face into the local cache.

## Recommended First Model

Use Whisper Small for the first local test. It is multilingual, supports German, and is much lighter than the large variants.

- [argmaxinc/whisperkit-coreml: openai_whisper-small_216MB](https://huggingface.co/argmaxinc/whisperkit-coreml/tree/main/openai_whisper-small_216MB)

Local cache path:

```text
~/Library/Application Support/Blitztext/models/whisperkit/openai_whisper-small_216MB
```

## Other Compatible Models

You can also install larger WhisperKit CoreML models into the same cache directory:

- [openai_whisper-large-v3-v20240930_626MB](https://huggingface.co/argmaxinc/whisperkit-coreml/tree/main/openai_whisper-large-v3-v20240930_626MB)
- [openai_whisper-large-v3-v20240930_turbo_632MB](https://huggingface.co/argmaxinc/whisperkit-coreml/tree/main/openai_whisper-large-v3-v20240930_turbo_632MB)

The app detects installed model folders that contain `AudioEncoder.mlmodelc`, `MelSpectrogram.mlmodelc`, and `TextDecoder.mlmodelc`.

## Install From The App

Open Blitztext, go to **Settings > Anpassen**, choose a local model, and click **Installieren**. You can also switch on **Sicherer Lokaler Modus** from the main popover; if the selected model is missing, Blitztext starts the download and installs it into the local cache.

After the model is installed, the Blitztext transcription workflow can run in local mode. The rewriting workflows still use OpenAI, so they are paused while secure local mode is active.

## Optional Manual Install

If you prefer the CLI path, install the Hugging Face CLI so the `hf` command is available:

```bash
python3 -m pip install --upgrade "huggingface_hub[cli]"
```

Create the local model cache:

```bash
mkdir -p "$HOME/Library/Application Support/Blitztext/models/whisperkit"
```

Download the recommended first model:

```bash
hf download argmaxinc/whisperkit-coreml \
  --include 'openai_whisper-small_216MB/*' \
  --local-dir "$HOME/Library/Application Support/Blitztext/models/whisperkit" \
  --max-workers 4
```

Expected folder layout:

```text
~/Library/Application Support/Blitztext/models/whisperkit/
  openai_whisper-small_216MB/
    AudioEncoder.mlmodelc/
    MelSpectrogram.mlmodelc/
    TextDecoder.mlmodelc/
```

If the folder is nested differently, the app will not detect the model.

## Notes

- First use can be slower because the model has to load and prewarm.
- Local transcription avoids sending audio to OpenAI for the Blitztext workflow.
- The app currently supports local transcription only, not local rewriting.
- Models are downloaded on demand so the repository and app package stay small and auditable.

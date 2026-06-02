# Setup

This guide is for people who want to build and inspect the preview themselves.

## 1. Requirements

- macOS 14 or newer
- Full Xcode, with Command Line Tools installed
- XcodeGen
- Homebrew, if you want to install XcodeGen with `brew install xcodegen`
- Optional for online workflows: an OpenAI API key
- Optional for secure local transcription: a local WhisperKit/CoreML model

Install XcodeGen manually if needed:

```bash
brew install xcodegen
```

## 2. Clone And Build

```bash
git clone https://github.com/cmagnussen/blitztext-app.git
cd blitztext-app
./build.sh --debug
```

To launch after building:

```bash
./build.sh --run
```

## 3. Configure OpenAI For Online Workflows

Open the app settings and paste your own OpenAI API key if you want online transcription or rewriting workflows.

The preview currently uses:

- `whisper-1` for transcription
- `gpt-4o-mini` for lightweight rewriting
- `gpt-4o` for the calmer-message workflow

You are responsible for API access, billing, and data handling in your own OpenAI account.

Never commit your API key into this repository, issues, logs, or screenshots.

You can skip this step if you only want to test local transcription with a local WhisperKit model.

## 4. Optional Local Transcription

To use secure local transcription, choose a compatible WhisperKit CoreML model in the app and click **Installieren**. Blitztext stores models in:

```text
~/Library/Application Support/Blitztext/models/whisperkit/
```

Recommended first model: `openai_whisper-small_216MB`.

See [local-models.md](local-models.md) for the exact command, model links, and expected folder layout.

## 5. macOS Permissions

The app needs Microphone permission to record audio.

For automatic paste into the previous app, grant Accessibility permission in macOS System Settings. Without it, you can still copy and paste manually.

Blitztext does not need Full Disk Access. Auto-paste uses the Accessibility permission because the app simulates Cmd+V after putting the result on the clipboard.

## Troubleshooting

- If `xcodebuild` reports that the active developer directory is only Command Line Tools, run `sudo xcode-select -s /Applications/Xcode.app/Contents/Developer`.
- If the build cannot find XcodeGen, install it explicitly with `brew install xcodegen`.
- If online transcription fails immediately, check whether the API key is present and valid.
- If secure local mode is disabled, check whether a WhisperKit model is installed in the expected folder.
- If transcription works but paste does not, this is not an OpenAI billing issue. Check **Privacy & Security -> Accessibility**, restart Blitztext after changing the permission, and make sure the cursor is focused in a text field before starting the workflow.
- If macOS shows multiple Blitztext entries under Accessibility, remove or disable stale entries, run the app from the final location (`/Applications` if you used `./build.sh --install`), then grant the permission again.
- If the target app blocks synthetic paste or the target app was not detected, the result still stays on the clipboard so you can press Cmd+V manually.
- If audio is missing, check Microphone permission and macOS input settings.
- If you see OpenAI errors, verify model access and account billing.

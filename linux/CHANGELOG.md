# Changelog

All notable changes to **Blitztext for Linux** (the native dictation tool in
`linux/`) are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The version is defined in [`blitztext/__init__.py`](blitztext/__init__.py).

## [Unreleased]

## [2.03.24] - 2026-06-10

### Fixed
- **Input level meter works without visiting General first.** The level meter
  was only started inside `_build_general()` and referenced `mic_level`
  unconditionally. If Input was opened first the meter never started. Now
  `_build_input()` also starts the meter when it isn't running yet, and both
  level bars (`mic_level` in General and `ww_mic_level` in Input) are updated
  defensively via `hasattr` so either tab can be visited in any order.

## [2.03.23] - 2026-06-10

### Fixed
- **Wakeword results table actually resizable.** The controls pane is now
  wrapped in a ScrolledWindow with `shrink=True`, so dragging the divider
  upward collapses the controls and expands the table freely.

## [2.03.22] - 2026-06-10

### Changed
- **Wakeword benchmark uses a split pane.** The TTS config / engine selector
  controls sit in the top pane; the results table sits in the bottom pane.
  Drag the divider to give the table as much vertical space as needed.

## [2.03.21] - 2026-06-10

### Added
- **Wakeword results table: sortable columns.** Click any column header to sort
  ascending/descending. Numeric columns (Detected, Total, Recall %, False fires,
  Time) sort numerically.
- **Wakeword results table: CSV export.** "Copy as CSV" copies the table to the
  clipboard; "Save CSV…" opens a file chooser to write a `.csv` file.

## [2.03.20] - 2026-06-10

### Added
- **Wakeword benchmark results table.** Results are now shown in a TreeView
  with one row per engine per voice: Engine | Wakeword | Voice | Detected |
  Total | Recall % | False fires | Time. Rows are colour-coded green/orange/red
  by recall. An aggregate "ALL (N voices)" row is appended per engine.

### Fixed
- **Section header icons now vertically centred with the headline text.**
  The `.bt-section` CSS class was inadvertently applied to the icon widget,
  giving it a 14 px top margin and pushing it down. The image no longer
  receives that class; a `set_pixel_size(14)` pin ensures consistent sizing.

## [2.03.19] - 2026-06-10

### Added
- **Wakeword engine checkboxes in benchmark.** A row of checkboxes above the
  "Run wakeword benchmark" button lets you pick which engines to include.
  All are checked by default.
- **Wakeword model selector in benchmark.** A "Wakeword" combo lets you
  override which wakeword phrase (model) to test. Leave empty for the default
  (each engine uses its own configured model). Pick a specific model (e.g.
  `okay_computer`) to test that phrase on every selected engine.

## [2.03.18] - 2026-06-10

### Fixed
- **TTS model dropdown no longer floods with voice names.** Servers like Kokoro
  expose each voice as a `/models` entry. The ⟳ button now detects this case
  and skips filling the model combo, prompting the user to type the model id
  manually (e.g. `kokoro`). The status line shows "type model id manually" as
  a hint.

### Changed
- **Wakeword benchmark runs across all engines and shows per-engine results.**
  Previously a callback signature mismatch caused the benchmark to crash when
  more than one engine was configured. Now progress shows `[1/3] engine name`,
  and the results panel lists Recall / False fires / time per engine.

## [2.03.17] - 2026-06-10

### Added
- **Wakeword model fetch feedback.** The ⟳ button now shows a status line while
  connecting; after loading it reports how many models were found (with their
  names) or "Unreachable" if the server is down.
- **Wakeword Quickstart covers all four ports.** The Quickstart menu now lists
  presets for ports 10400–10403, plus `hey_jarvis` and `alexa` variants.
- **Wakeword info box.** An info banner explains how wyoming-openwakeword works,
  where to put model files, and lists the common built-in models.

## [2.03.16] - 2026-06-10

### Added
- **MP3/OGG/FLAC support for sound cues.** The sound file picker now accepts
  WAV, MP3, OGG, FLAC, M4A, AAC, AIFF, and Opus. Playback uses `ffplay` or
  `gst-play-1.0` as a universal fallback when the native `pw-play`/`paplay`
  can't handle the format.
- **Browse dialog with auto-preview.** The 📁 browse button opens a
  `FileChooserDialog`; selecting a file auto-plays it so you can hear it before
  confirming. The ▶ play button still works on the current selection.

## [2.03.15] - 2026-06-10

### Added
- **Wakeword engine CRUD.** The wakeword server section now has the same full
  management UI as STT engines: a named-preset selector combo, + Add, Quickstart
  (with 4 common wyoming-openwakeword templates), ⟳ reload, and Delete. Existing
  users are migrated: their `wakeword_uri` / `wakeword_model` become the first
  preset automatically.

## [2.03.14] - 2026-06-10

### Fixed
- **Engines tab.** Removed the "Internal engine — device & precision" section
  header. The Device and Compute type fields already only appear when a local
  engine type is selected; the separate header was redundant.

## [2.03.13] - 2026-06-10

### Changed
- **Settings header bar.** Save and Save & Restart moved from the bottom button
  bar into the title bar (GTK HeaderBar). The X button closes without saving.
  Bottom button row removed.
- **Section icon alignment.** Icons in section headers are now vertically
  centred with the label text (`SMALL_TOOLBAR` size, `valign=CENTER`).

## [2.03.12] - 2026-06-10

### Added
- **Icons in settings.** All tab labels (Presets, Engines, Input, General,
  Benchmark, Log, Manual, About) and every section header inside each tab now
  show a small GTK symbolic icon, making the layout easier to scan.

### Fixed
- **Resize grip position.** The grip indicator now appears correctly at the
  bottom-right corner below the notebook, not misplaced in the tab bar.

## [2.03.11] - 2026-06-09

### Added
- **Resize grip indicator.** A dotted SE-corner grip is drawn over the
  bottom-right of the settings window so users discover it is resizable.

## [2.03.10] - 2026-06-09

### Fixed
- **Server RAM probe.** Prometheus `/metrics` is almost always at the server
  root (`http://host:port/metrics`), not under `/v1`. Now tries the root URL
  first before falling back to the API base path.

## [2.03.09] - 2026-06-09

### Added
- **Server RAM in benchmark.** For remote/Docker STT engines the benchmark now
  probes the server's Prometheus `/metrics` endpoint for
  `process_resident_memory_bytes` (standard Python/Go exporter) or
  `container_memory_rss` (cAdvisor) and shows the server-side RSS in MB in the
  RAM column. Falls back to `server` when the endpoint is not exposed.

## [2.03.08] - 2026-06-09

### Fixed
- **Engines tab layout.** The "Internal engine — device & precision" section is
  now hidden when a remote (Server) or streaming engine type is selected —
  removing the confusing whitespace gap and irrelevant device controls for
  non-local engines.

## [2.03.01] - 2026-06-09

### Added
- **RAM usage column in benchmark.** The results table now shows a **RAM (MB)**
  column — the increase in process RSS while the transcription ran. For local
  models this captures the memory cost of loading the model on first use; for
  remote engines it shows `—` (work happens server-side). Values are measured via
  `/proc/self/status` (VmRSS), so they reflect actual resident memory, not
  virtual address space.

## [2.03.00] - 2026-06-09

### Fixed
- **"Not responding" / system instability on Save.** `_collect()` was calling
  `socket.create_connection()` *synchronously* on the GTK main thread when
  wakeword is enabled — freezing the UI for up to 1.5 s (longer if DNS is slow).
  The check is now done on a daemon thread and the result is logged instead of
  blocking the save path.
- **GTK thread-safety crash in wakeword model load.** `_ww_load()` read
  `self.ww_uri.get_text()` from inside a background thread — unsafe. The URI is
  now captured on the main thread before the thread is spawned.
- **HTTP 404 with WhisperX and other non-standard endpoints.** The remote
  transcription call always appended `/audio/transcriptions` to the base URL, but
  services like WhisperX use `/transcribe` as the full path. The URL path is now
  inspected: if it is anything other than empty / `/v1` / `/v1.0`, the URL is
  used as the complete endpoint with nothing appended — so
  `http://host:8081/transcribe` works out of the box.
- **Log levels.** `logbuffer` now stores `(timestamp, level, message)` tuples and
  accepts a `level=` keyword (`DEBUG` / `INFO` / `WARNING` / `ERROR`). The Log
  tab gains a **Level** dropdown (Verbose · Info · Warning · Error) that filters
  the displayed entries live. Wakeword and socket errors are now tagged
  `WARNING`; library records are forwarded at their native level.

### Added
- **Wakeword server preset dropdown** (Input → Hands-free wakeword). A
  **Server preset** combo lists all configured wakeword server engines by name.
  Picking one auto-fills the URI and model fields and re-probes reachability.
  The selection is persisted as `wakeword_active` in config.

## [2.02.03] - 2026-06-09

### Added
- Wakeword server preset dropdown in Input tab.

## [2.02.02] - 2026-06-09

### Fixed
- License tab now renders with markdown styling.
- Benchmark pane minimum height (320 px, `shrink=False`) prevents the engine
  list or results table from collapsing to zero when the window is small.

## [2.02.01] - 2026-06-09

### Added
- Last benchmark time and accuracy shown on the selected STT engine in the
  Engines tab. Persisted to config so it survives restarts.

## [2.02.00] - 2026-06-09

### Added
- **Language metadata in benchmark.** The engine checkbox list shows supported
  language codes next to each engine (fetched async). Filter box searches by
  language code. Results table has a **Lang** column. Data comes from the
  `/v1/models` `language` field (faster-whisper-server) or NVIDIA NIM `/metadata`.

## [1.9.5] - 2026-06-09

### Added
- **Emoji picker search.** A search field at the top of the emoji picker filters
  all categories in real time using Unicode character names (e.g. "fire", "dog",
  "heart"). Typing hides the category bar and shows matching results; clearing
  restores the category view.

### Fixed
- **Manual tab now shows content.** `MANUAL.md` is copied next to the package
  module so the Manual tab finds it in both venv and deb installs.
- **Info banner no longer bright blue.** The `.bt-infobox` background now uses
  a neutral 5 % tint of the foreground colour instead of the theme accent
  colour, so text stays readable on any theme.

## [1.9.4] - 2026-06-09

### Changed
- **Settings UI completely redesigned.** All six settings tabs (Presets, Engines,
  Input, General, Input, General) now use a card-based layout following GTK3 best
  practices: related fields are grouped inside visually distinct cards with bold
  section titles. CSS is injected at start-up to give cards a consistent rounded
  border (`boxed-list` + `bt-card`) and a styled info banner at the top of each
  tab.
- **Dialog is larger (740×700 px) and every tab scrolls.** The notebook pages
  now wrap their content in a `Gtk.ScrolledWindow` so no fields are ever clipped,
  even on small screens.
- **Engines toolbar reorganised.** Creation actions (+ Add, + Stream, Quickstart)
  are left-aligned; destructive/status actions (Delete, Test, ⟳) are
  right-aligned via `pack_end`, making the bar scannable at a glance.
- **Section titles replace plain separators.** The old `Gtk.Separator` +
  unstyled `Gtk.Label` pattern is gone; every section now has a small, dimmed,
  bold all-caps header rendered with markup.
- **Cleaner section names.** "WW - Wakeword (Hands-free)" → "Hands-free
  wakeword"; "Audio cues (manual dictation)" → "Audio cues (keyboard / hotkey
  dictation)"; "Local engine … device & precision" → "Internal engine — device &
  precision".

## [1.9.3] - 2026-06-09

### Added
- **ⓘ info buttons on every settings field.** Each field in every tab now has a
  small information icon that opens a plain-language help popover when clicked —
  so non-technical users can understand what each setting does without hovering
  or reading the manual.
- **Manual tab in Settings.** A new "Manual" tab shows the full `MANUAL.md`
  reference doc directly inside the Settings window.
- **Quickstart templates for engines.** A "Quickstart ▾" button in the STT and
  LLM engine toolbars opens a menu of common services (OpenAI, Groq, OpenRouter,
  Ollama, LM Studio, vLLM, llama-swap, faster-whisper-server, NVIDIA Riva) and
  pre-fills the form — one click to configure a provider.

### Changed
- **Engine type names are now human-readable.** STT types now read "Internal —
  faster-whisper, runs inside the app", "Server — OpenAI-compatible API (LAN or
  cloud)", and "Realtime — NVIDIA Riva / NIM streaming" instead of the raw
  identifiers. LLM types read "LAN server — runs on your machine or local
  network" and "Cloud service — OpenAI, Groq, OpenRouter, …".
- **Device selector now shows "GPU (CUDA)" instead of "cuda"**, and compute
  types have plain-language descriptions (e.g. "int8 — fast, less memory").

## [1.9.2] - 2026-06-09

### Added
- **Emoji picker for preset icons.** The "Icon (emoji)" field in Settings →
  Presets now has a 😀 button that opens a scrollable emoji grid (60 common
  emojis across six categories). Click any emoji to insert it — or keep typing
  directly into the field as before.

## [1.9.1] - 2026-06-08

### Changed
- **Settings opens instantly.** Each tab's contents are now built the first time
  you view it instead of all up front, so the dialog no longer pauses ~1.3s
  constructing the file-choosers in the Input/Benchmark tabs. Saving force-builds
  any tab you didn't visit first, so no field is ever missed.
- **Connection dots moved beside their field.** The Wakeword and TTS reachability
  dots now sit just left of the URL entry (matching the Engines tab) instead of
  at the far right of the row.

### Fixed
- **Settings could be opened more than once.** Choosing Settings while it's
  already open now raises the existing window instead of stacking a second copy.

## [1.9.0] - 2026-06-08

### Added
- **Connection indicators** for remote endpoints. The **Wakeword engine** field
  (Input tab — renamed from "Wyoming URI" to read more generally) and the **TTS
  URL** field (Benchmark tab) now show a coloured dot: green when the server is
  reachable, red when it's configured but unreachable, grey when blank — mirroring
  the STT/LLM engine dots. It's a lightweight background TCP probe, refreshed when
  the dialog opens, when you press ⟳, and when you leave the field.

## [1.8.1] - 2026-06-08

### Fixed
- **Settings dialog and control panel wouldn't open on some desktops.** When the
  gvfs `org.gtk.vfs.UDisks2VolumeMonitor` dbus service fails to activate (common
  on headless or minimal sessions), every `Gtk.FileChooserButton` blocked ~25s on
  a `StartServiceByName` timeout while realizing — so the Settings dialog never
  finished appearing, and the stalled GTK main loop froze the panel too. Blitztext
  now selects GIO's native `/proc/mounts` volume monitor
  (`GIO_USE_VOLUME_MONITOR=unix`) before any window is realized, so file choosers
  open instantly with no dbus dependency.

## [1.8.0] - 2026-06-08

### Added
- **Send by voice**: say a distinctive phrase like **"computer send"** at the
  start or end of a clip and the word is stripped, then the rest is typed **and
  submitted with Enter** — the spoken equivalent of "stop + paste + Enter".
  Mainly for hands-free use, where you can't press a key. Configure under
  Settings → Input → "Send words", or `[routing] send_keywords`. Off by default;
  because it presses Enter, use a multi-word phrase (e.g. your wakeword + "send")
  so a sentence that merely ends in "send" doesn't submit by accident. Matched
  the same edge-anchored, ASR-tolerant way as routing/cancel keywords.
- **Wakeword benchmark** (Settings → Benchmark): stress-test hands-free
  detection. It synthesizes short sentences with your wake phrase spoken in
  random voices (plus pure-filler utterances with none), streams them to your
  wyoming-openwakeword server, and reports **recall** (how reliably it fires),
  **false fires**, and a **per-voice** breakdown. Speech comes from any
  OpenAI-compatible TTS server (Kokoro-FastAPI, XTTS, OpenAI, …): set its URL,
  optional API-key env var, model, and voices under the new `[tts]` config / the
  Benchmark tab, and use **Connect** to test it (it auto-fills the voice list
  when the server exposes one).

## [1.7.1] - 2026-06-08

### Fixed
- **Overlay waveform and silence countdown ring never appeared** on systems
  where PortAudio/`sounddevice` can't open the default input — notably PipeWire
  boxes, where opening an input stream simply hangs. Both the live waveform and
  the auto-stop countdown are driven by a single level meter, which was the only
  part of the app still using `sounddevice` (everything else records via
  `pw-record`). The meter now streams raw PCM from the **same system recorder as
  the WAV recorder** (`pw-record`/`parecord`/`arecord`) and computes the level
  itself, so it works wherever recording works — on both the hotkey and
  hands-free (wakeword) paths, plus the mic-level preview in Settings. No more
  PortAudio dependency for metering.
- **App reported itself as "`__main__.py`"** in the taskbar and in GNOME's
  "… is not responding" dialog. Launched via `python -m blitztext`, GTK's default
  program name is `argv[0]`'s basename. It now sets `prgname`/application name to
  **Blitztext** before any window is realized (and the desktop file gains
  `StartupWMClass=blitztext` for the .desktop match + icon), without touching the
  `-m blitztext` entry point.

## [1.7.0] - 2026-06-07

### Added
- **Spoken cancel keyword**: say a word like **"abbrechen"** (or "cancel") at the
  start or end of a clip and the whole dictation is **discarded** — it is never
  routed, rewritten, or typed anywhere. Mainly rescues an accidentally triggered
  (e.g. wakeword) recording. Configure under Settings → Mic/Cues → "Cancel words",
  or `[routing] cancel_keywords` (default `["abbrechen", "cancel"]`; empty list
  disables it). Matched the same edge-anchored, ASR-tolerant way as routing
  keywords, so the word buried mid-sentence won't trip it.

## [1.6.0] - 2026-06-07

### Fixed
- **Session freeze when the overlay's caret tracking was active** (could lock up
  the whole GNOME/X11 desktop, forcing a logout/reboot). The AT-SPI caret tracker
  subscribed to the high-frequency `object:text-caret-moved` signal and made
  **synchronous, blocking AT-SPI reads from inside the event handler** — which
  re-enters the accessibility dispatcher and is stormed by the app's *own*
  `xdotool` typing (one event per character), congesting the a11y bus until the
  desktop stopped responding. It now tracks **focus changes only** and reads the
  caret rectangle lazily (once, when the overlay shows), never from inside an
  event dispatch.

### Changed
- **Matched preset is fused into the overlay instead of a desktop notification**:
  when voice routing picks a preset, the overlay shows its emoji icon, name, and
  the spoken keyword on a banner, and narrates the phase ("Transcribing…" →
  "Rewriting…"). With the overlay on, the redundant per-dictation notifications
  are suppressed (errors still notify); headless/overlay-off keeps notifications.

### Added
- **Live LLM rewrite in the overlay**: rewrite presets now stream the model's
  output into the bubble token-by-token, so you watch it write. The delivered
  text is still the complete result, typed once the rewrite finishes.

## [1.5.1] - 2026-06-07

### Added
- **Silence auto-stop countdown ring** on the dictation overlay: when you stop
  speaking, a full circle wrapping the microphone glyph drains clockwise as the
  trailing-silence timer runs out, recolouring from calm cyan to an urgent red
  and emptying exactly as the recording auto-stops. It spans the configured
  "Silence to stop (s)" window (`[wakeword] silence_seconds`), fades back in/out
  as you pause and resume, and so finally makes the hands-free auto-stop visible
  instead of a silent surprise.

## [1.5.0] - 2026-06-07

### Added
- **On-screen dictation overlay** (Settings → General → "Visual overlay", or
  `[general] overlay_enabled`, default on): the moment recording starts — by
  hotkey **or** wakeword — a translucent bubble appears at the cursor showing a
  pulsing **microphone**, a **live waveform** of your mic level, and the
  **recognised text** (word-by-word with a realtime streaming STT engine, or the
  final result as a brief confirmation otherwise). Its tail points at where the
  text will land: it follows the **text caret** when the focused app exposes it
  over accessibility (AT-SPI), otherwise the **mouse pointer**, otherwise a
  screen corner — tune via `[general] overlay_anchor = "caret" | "pointer" |
  "corner"`. The window is click-through and never takes focus, and it finally
  gives **hands-free wakeword sessions** visible feedback (their notifications
  are suppressed by design). X11 only; falls back to a corner where the cursor
  can't be located.

### Changed
- **Presets are speakable by name**: voice routing now matches a preset's *name*
  as an implicit keyword, so a preset works by voice even with no keywords
  configured (e.g. just say "nicer email …"). Explicit keywords still take
  precedence, and preset names also bias the STT for better recognition.
- **General settings switches** moved to the far right of each row, each with an
  inline description so it's clear what the toggle does without hovering.
- **About**: added a "Copyright: 2026 mARTin Bierschenk - Design" line.

## [1.4.0] - 2026-06-07

### Added
- **"Announce matched preset" notification** (Settings → General, or
  `[general] notify_routing`, default on): after a voice command, a notification
  shows which preset and spoken keyword matched — **shown even for hands-free
  wakeword sessions**, so you can see what you triggered. It only fires on a real
  match, so it never spams when nothing is said.
- **Per-preset emoji icon** (Presets → "Icon (emoji)"): give each preset a
  distinct emoji, shown in the matched-preset notification so you can tell at a
  glance which fired.

### Fixed
- **Voice-routing default went to a rewrite**: when no `[routing] default` preset
  is set, the no-keyword fallback used the *first* preset — which, if that happened
  to be an LLM rewrite (e.g. "Improve text"), sent every unrouted wakeword command
  to the language model (and failed when the LLM was down). The fallback now
  prefers a `transcribe` preset, so the default action is plain transcription.

## [1.3.0] - 2026-06-07

### Added
- **Pause wakeword (tray)**: a reversible "Pause wakeword" toggle appears in the
  system-tray menu when the wakeword is enabled. It pauses/resumes hands-free
  detection by toggling the `/tmp/wake_muted` flag (external scripts may toggle
  the same file).
- **"Play audio cues" switch** (Settings → Input → Audio cues, or
  `[sounds] enabled`): on/off for the **manual** (keyboard/hotkey) start/stop
  chimes. Defaults to on. The hands-free wakeword sounds are independent of it.
- **Configurable wakeword auto-stop silence** (Settings → Input → Hands-free →
  "Silence to stop (s)", or `[wakeword] silence_seconds`): end a hands-free
  recording this many seconds after you stop speaking. Defaults to `2.0`
  (previously hard-coded to 2.5 s).

### Fixed
- **Wakeword sounds silenced by the manual cue switch**: the "Play audio cues"
  master switch wrongly muted the hands-free *Sound: detected/captured* cues too.
  Wakeword cues are now independent — they play whenever a file is set and stay
  silent when cleared (no surprise system-chime fallback), regardless of the
  manual switch.
- **PortAudio/ALSA teardown noise**: the level meter no longer leaks
  `pthread_join ... failed` / `PaUnixThread_Terminate ... failed` lines to the
  terminal when a clip ends — that C-library chatter (written straight to fd 2)
  is now suppressed around the stream open/close.
- **Wakeword stuck muted**: a leftover `/tmp/wake_muted` flag silently disabled
  detection with no in-app way to clear it. The state is now exposed and
  reversible from the tray, so a stale flag no longer kills hands-free use. The
  daemon also logs a clear `Starting PAUSED` warning when it boots muted.
- **Away-from-keyboard "Busy" storm**: a wakeword hit arriving while the previous
  clip was still transcribing went through `toggle()` and popped a "Busy"
  notification. Wakeword triggers now go straight to `start_dictation()`, so a
  busy/not-ready state is ignored silently instead.
- **Quiet hands-free errors**: transcription/rewrite failures during a
  wakeword-triggered session no longer raise critical desktop notifications —
  they are logged instead, keeping background sessions silent.
- **Notification storm / lock-screen pile-up**: desktop notifications are now
  sent as transient with a short expiry and reuse a single bubble, so they no
  longer stack in the notification log or persist on the lock screen.
- **Quiet hands-free sessions**: per-dictation notifications are suppressed for
  wakeword-triggered sessions (audio cues are used instead).

## [1.2.0] - 2026-06-05

### Added
- **Wyoming Wakeword Support**: Complete hands-free integration via Wyoming protocol (e.g., openWakeWord), with live configuration testing and model fetching in the UI.
- **ATK Screen Reader Accessibility**: Fully mapped GTK labels, inputs, tooltips, and properties to the ATK bridge, enabling seamless navigation for blind users via screen readers like Orca.
- **Drag-and-Drop Workflow Ordering**: Workflows in the main tray menu can now be reordered via native drag-and-drop.
- **Voice Activity Detection (VAD) Auto-Stop**: Dictation now automatically stops after detecting 2.5 seconds of silence, removing the need to manually click Stop.
- **Audio Feedback**: Added audible start/stop/cancel chimes mapping to system-native alert sounds.
- **Benchmark Autocomplete**: The Benchmark UI automatically fills in the reference `.txt` transcript if it matches the selected audio file.
- **Realtime STT streaming mode**: new `mode = "stream"` workflow support and a
  `riva_realtime` STT engine for Riva/NIM WebSocket transcription, including a
  Settings shortcut for Nemotron ASR Streaming on `http://127.0.0.1:8006/v1`.
- **Settings About tab** with the app version, source link, changelog, and
  license text.
- **STT & LLM engine manager**: add, rename, and delete engine presets, each
  with an online/offline status dot, a per-engine type (local/cloud), and a
  **searchable model dropdown** populated from the server's `/models` (with a
  reload button). Local Whisper device/precision now live with the STT engine.
- **Benchmark tab**: run a reference clip through every STT engine and compare
  **time**, **case-sensitive accuracy** (WER), and a **CPU/GPU/remote device**
  column, with the fastest and most accurate highlighted.
- **Custom audio cues**: pick your own WAV files to play when recording starts
  and stops (covers stop+paste, stop+paste+Enter, and silence auto-stop), each
  with play-test and clear-to-default buttons. Built-in system sounds otherwise.
- **Settings Log tab**: a live activity log (model load/download, transcriptions,
  errors) with Copy and Clear, so a long "Loading…" is no longer opaque.
- **Per-tab info boxes** and expanded **tooltips** across Settings, written in
  plain language and exposed to screen readers (ATK) — for non-technical and
  blind users (barrierefrei).
- **Click-to-bind hotkeys**: a *Set* button captures the next keypress (including
  modifier-only chords like Ctrl+Win) into any hotkey field.

### Changed
- **GUI rebuilt in GTK 3** (replacing tkinter): a native GNOME panel unified with
  the tray, with the Ubuntu font and a dropdown+editor pattern in Settings.
- **Voice-keyword routing** and a **modifier hotkey scheme** (Ctrl+Win start,
  Ctrl stop+paste, Alt stop+paste+Enter, Esc cancel) replace per-preset combos as
  the default way to dictate.
- **Quality gate** rejects silent/too-short clips and stock Whisper
  hallucinations before they reach the screen.

## [1.1.0] - 2026-06-04

### Added
- **Debian package** (`packaging/build-deb.sh`) producing an installable
  `blitztext_<ver>_arm64.deb` with a desktop entry, app icon, and a `blitztext`
  launcher. Installs via the Software app or `apt install ./…deb`. Bundles a
  relocatable venv with all Python deps (no pip/network at install) and declares
  system deps (python3-gi, xdotool, libnotify-bin, a recorder) so they pull in
  automatically. The bundled venv is built on the system `/usr/bin/python3`, so
  the tray works out of the box.

### Notes
- `python3-gi` is already present on a standard Ubuntu GNOME install; the tray
  only seemed unavailable from source when the project venv was built from a
  non-system Python (e.g. conda/miniforge). The `.deb` avoids this entirely.

## [1.0.1] - 2026-06-03

### Changed
- Redesigned the control-panel window: minimal flat layout, Ubuntu font
  throughout, clickable workflow rows with hover (click to record / stop),
  subtle dividers, and text-style Settings/Quit actions. Dropped the monogram
  avatars and per-row buttons in favour of a cleaner, simpler look. The Settings
  window picks up the same font and styling.

## [1.0.0] - 2026-06-03

First release of the Linux port. The upstream project is a macOS-only menu-bar
app (Swift/SwiftUI, CoreML/WhisperKit) that cannot run on Linux or in a
container; this is a native host tool that reproduces the workflow — focus any
text field, press a hotkey, speak, and the (optionally rewritten) text is typed
into that field.

### Added
- **Native dictation engine** (`daemon.py`): global hotkeys via pynput, each
  hotkey toggles record → transcribe → optional rewrite → deliver.
- **Local transcription** via faster-whisper (`transcribe.py`); `device="auto"`
  tries CUDA and falls back to CPU `int8` (CPU-only on this arm64 host).
- **Microphone recording** (`recorder.py`) through pw-record / parecord /
  arecord — 16 kHz mono WAV, no Python audio bindings required.
- **Optional LLM rewrite** (`rewrite.py`) against any OpenAI-compatible endpoint
  (OpenAI, or a local vLLM / llama-swap), configurable per workflow.
- **Typing into the focused window** via xdotool (`paste.py`): `type` directly
  or `paste` through the clipboard; re-activates the target window first.
- **Configurable workflows** (`config.py`) in `~/.config/blitztext/config.toml`,
  with five defaults (Transcribe, Nicer email, Improve text, Calm down, Add
  emojis), per-workflow prompt/model/temperature overrides, and a TOML writer.
- **Control-panel window** (`gui.py`, tkinter): workflow rows with monogram
  avatars, hotkey badges, per-row Record buttons, a live status dot, and a
  Settings window that edits config and can Save & Restart.
- **System-tray mode** (`tray.py`, AppIndicator): macOS-menu-bar-style status
  icon with a menu to trigger each workflow, Show panel, Settings…, and Quit;
  shares one daemon/model/hotkey set with the window. Falls back to the window
  with an install hint when PyGObject is absent.
- **CLI** (`__main__.py`): `tray` (default), `gui`, `run`, `transcribe`,
  `config-path`, and `--version`.
- **Packaging**: `install.sh` (venv with `--system-site-packages`),
  `requirements.txt`, and a `blitztext.service` systemd user unit.

### Notes
- Targets an **X11** session (uses xdotool); Wayland would need ydotool/wtype.
- System tray requires a one-time `sudo apt install python3-gi` (the GTK /
  AppIndicator typelibs and GNOME `ubuntu-appindicators` extension are already
  present on the target host).

[Unreleased]: https://github.com/mARTin-B78/blitztext-app-linux/compare/v1.5.1...HEAD
[1.5.1]: https://github.com/mARTin-B78/blitztext-app-linux/compare/v1.5.0...v1.5.1
[1.5.0]: https://github.com/mARTin-B78/blitztext-app-linux/compare/v1.4.0...v1.5.0
[1.1.0]: https://github.com/mARTin-B78/blitztext-app-linux/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/mARTin-B78/blitztext-app-linux/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/mARTin-B78/blitztext-app-linux/releases/tag/v1.0.0

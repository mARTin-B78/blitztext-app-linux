"""Configuration loading and the default config template."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .llm import LLMEngine
from .stt import STTEngine

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "blitztext"
CONFIG_PATH = CONFIG_DIR / "config.toml"


@dataclass
class Workflow:
    name: str
    hotkey: str
    mode: str  # "transcribe" | "rewrite" | "stream"
    prompt: str = ""
    # Spoken trigger phrases for voice routing (matched at start/end of speech).
    keywords: list[str] = field(default_factory=list)
    # Optional per-workflow overrides of the [rewrite] defaults.
    model: str | None = None
    temperature: float | None = None
    # Which LLM engine to use for this preset's rewrite step.
    # "" (empty) = use whichever engine is currently active in the Engines tab.
    llm_engine: str = ""
    # Cosmetic, used by the GUI.
    description: str = ""
    icon: str = "⚡"


@dataclass
class WakewordEngine:
    """A wyoming-openwakeword endpoint to compare in the wakeword benchmark."""
    name: str = ""
    uri: str = "tcp://127.0.0.1:10400"
    model: str = "okay_computer"
    cancel_model: str = ""   # wakeword model(s) that cancel an in-progress recording
    send_model: str = ""     # wakeword model(s) that finish + send (Enter) a recording


@dataclass
class Config:
    # general
    recorder: str = "auto"
    mic: str = ""                 # pactl/pipewire source name; "" = default device
    output: str = "type"          # type | paste
    type_delay_ms: int = 12
    notify: bool = True
    notify_routing: bool = True   # announce which preset/keyword a voice command matched
    language: str = "de"          # whisper hint; "" = autodetect
    # on-screen overlay (mic + live waveform + recognised-text bubble)
    overlay_enabled: bool = True
    overlay_anchor: str = "pointer"  # pointer | caret (AT-SPI, may freeze) | corner
    # input scheme
    input_mode: str = "modifiers"   # "modifiers" (Ctrl+Win/Ctrl/Alt/Esc) | "hotkeys" (combos)
    push_to_talk: bool = False
    key_start: str = "<ctrl>+<cmd>"   # start recording (Ctrl+Win)
    key_stop: str = "<ctrl>"          # stop -> paste
    key_send: str = "<alt>"           # stop -> paste -> Enter
    key_cancel: str = "<esc>"         # discard
    # quality gate
    min_speech_seconds: float = 0.4
    silence_rms: float = 150.0
    reject_hallucinations: bool = True
    strip_trailing_punctuation: bool = False
    # audio cues (paths to WAV files; "" = built-in system sound)
    sounds_enabled: bool = True   # master switch for all start/stop/wakeword cues
    sound_before: str = ""
    sound_after: str = ""
    # whisper
    model: str = "small"
    device: str = "auto"          # auto | cuda | cpu
    compute_type: str = "auto"    # auto | int8 | float16 | int8_float16
    beam_size: int = 5
    # rewrite (OpenAI-compatible)
    base_url: str = "https://api.openai.com/v1"
    api_key_env: str = "OPENAI_API_KEY"
    rewrite_model: str = "gpt-4o-mini"
    temperature: float = 0.3
    timeout: int = 45
    # voice-keyword routing
    routing_enabled: bool = True
    routing_hotkey: str = "<ctrl>+<alt>+<space>"
    routing_default: str = ""        # preset name used when no keyword matches; "" = first
    routing_threshold: float = 0.82
    # Spoken abort: if one of these words is heard at the start/end of a clip, the
    # dictation is discarded — never transcribed onward, routed, rewritten, or
    # typed. Empty list = disabled. Mainly for accidental wakeword triggers.
    cancel_keywords: list[str] = field(default_factory=lambda: ["abbrechen", "cancel"])
    # Spoken send: if one of these is heard at the start/end of a clip, it is
    # stripped and the rest is delivered *and submitted with Enter* — the spoken
    # equivalent of "stop + paste + Enter". Empty = disabled. Because it presses
    # Enter, prefer a distinctive multi-word phrase (e.g. "computer send") so a
    # sentence that merely ends in "send" doesn't submit by accident.
    send_keywords: list[str] = field(default_factory=list)
    # speech-to-text engines (presets)
    stt_engines: list[STTEngine] = field(default_factory=list)
    stt_active: str = ""
    # llm engines (presets) for the rewrite step
    llm_engines: list[LLMEngine] = field(default_factory=list)
    llm_active: str = ""
    # wakeword
    wakeword_enabled: bool = False
    wakeword_active: str = ""   # name of selected WakewordEngine preset, "" = custom
    wakeword_uri: str = "tcp://127.0.0.1:10400"
    wakeword_model: str = "okay_computer"
    wakeword_sound_detected: str = ""   # WAV played when the wakeword fires (speak now)
    wakeword_sound_done: str = ""        # WAV played when the command is captured
    wakeword_silence_seconds: float = 2.0  # auto-stop after this much trailing silence
    wakeword_cancel_model: str = ""  # wakeword model that cancels an in-progress recording
    wakeword_send_model: str = ""    # wakeword model that finishes + sends (Enter) a recording
    setup_complete: bool = False     # True once the first-run wizard has been completed
    # Text-to-speech for the wakeword benchmark — its own OpenAI-compatible
    # endpoint (Kokoro, XTTS, OpenAI, …): base URL incl. /v1, an optional bearer
    # key env var, a model id, and the voices to cycle through.
    tts_url: str = ""
    tts_api_key_env: str = ""
    tts_model: str = ""
    tts_voices: list[str] = field(
        default_factory=lambda: ["alloy", "echo", "fable", "onyx", "nova", "shimmer"])
    # Wakeword engines to compare in the benchmark (each a wyoming-openwakeword
    # endpoint). Empty → the benchmark falls back to the live [wakeword] above.
    wakeword_engines: list[WakewordEngine] = field(default_factory=list)
    # STT benchmark: last-used WAV / reference transcript paths and options
    bench_wav: str = ""
    bench_ref: str = ""
    bench_expand_models: bool = False
    bench_last: dict = field(default_factory=dict)  # {engine_name: {seconds, accuracy, ok}}
    # workflows
    workflows: list[Workflow] = field(default_factory=list)

    @property
    def active_stt(self) -> STTEngine:
        e = next((x for x in self.stt_engines if x.name == self.stt_active), None)
        if e:
            return e
        return self.stt_engines[0] if self.stt_engines else STTEngine("Local", "local", model=self.model)

    @property
    def active_llm(self) -> LLMEngine:
        e = next((x for x in self.llm_engines if x.name == self.llm_active), None)
        if e:
            return e
        if self.llm_engines:
            return self.llm_engines[0]
        return LLMEngine("Default", self.base_url, self.rewrite_model, self.api_key_env, self.temperature)

    def preset_by_name(self, name: str | None) -> "Workflow | None":
        if not name:
            return None
        return next((w for w in self.workflows if w.name == name), None)

    @property
    def default_preset(self) -> "Workflow | None":
        named = self.preset_by_name(self.routing_default)
        if named:
            return named
        if not self.workflows:
            return None
        # No explicit default configured: prefer a plain transcribe preset over
        # whatever happens to be first, so the no-keyword fallback never silently
        # routes to an LLM rewrite.
        return next((w for w in self.workflows if w.mode == "transcribe"), self.workflows[0])

    @property
    def all_keywords(self) -> list[str]:
        out: list[str] = []
        for w in self.workflows:
            out.extend(w.keywords)
            if w.name and w.name not in out:
                out.append(w.name)  # names are implicit triggers — bias STT for them too
        return out

    @property
    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env) or None


def load(path: Path = CONFIG_PATH) -> Config:
    """Load config from TOML, creating a default file on first run."""
    if not path.exists():
        ensure_default(path)

    with path.open("rb") as fh:
        data = tomllib.load(fh)

    g = data.get("general", {})
    w = data.get("whisper", {})
    r = data.get("rewrite", {})
    rt = data.get("routing", {})
    inp = data.get("input", {})
    q = data.get("quality", {})
    snd = data.get("sounds", {})
    ww = data.get("wakeword", {})
    tts = data.get("tts", {})

    cfg = Config(
        recorder=g.get("recorder", "auto"),
        mic=g.get("mic", ""),
        output=g.get("output", "type"),
        type_delay_ms=int(g.get("type_delay_ms", 4)),
        notify=bool(g.get("notify", True)),
        setup_complete=bool(g.get("setup_complete", False)),
        notify_routing=bool(g.get("notify_routing", True)),
        language=g.get("language", "de"),
        overlay_enabled=bool(g.get("overlay_enabled", True)),
        overlay_anchor=g.get("overlay_anchor", "pointer"),
        model=w.get("model", "small"),
        device=w.get("device", "auto"),
        compute_type=w.get("compute_type", "auto"),
        beam_size=int(w.get("beam_size", 5)),
        base_url=r.get("base_url", "https://api.openai.com/v1").rstrip("/"),
        api_key_env=r.get("api_key_env", "OPENAI_API_KEY"),
        rewrite_model=r.get("model", "gpt-4o-mini"),
        temperature=float(r.get("temperature", 0.3)),
        timeout=int(r.get("timeout", 45)),
        routing_enabled=bool(rt.get("enabled", True)),
        routing_hotkey=rt.get("hotkey", "<ctrl>+<alt>+<space>"),
        routing_default=rt.get("default", ""),
        routing_threshold=float(rt.get("threshold", 0.82)),
        cancel_keywords=list(rt.get("cancel_keywords", ["abbrechen", "cancel"])),
        send_keywords=list(rt.get("send_keywords", [])),
        input_mode=inp.get("mode", "modifiers"),
        push_to_talk=bool(inp.get("push_to_talk", False)),
        key_start=inp.get("start", "<ctrl>+<cmd>"),
        key_stop=inp.get("stop", "<ctrl>"),
        key_send=inp.get("send", "<alt>"),
        key_cancel=inp.get("cancel", "<esc>"),
        min_speech_seconds=float(q.get("min_speech_seconds", 0.4)),
        silence_rms=float(q.get("silence_rms", 150.0)),
        reject_hallucinations=bool(q.get("reject_hallucinations", True)),
        strip_trailing_punctuation=bool(q.get("strip_trailing_punctuation", False)),
        sounds_enabled=bool(snd.get("enabled", True)),
        sound_before=snd.get("before", ""),
        sound_after=snd.get("after", ""),
        wakeword_enabled=bool(ww.get("enabled", False)),
        wakeword_active=ww.get("active", ""),
        wakeword_uri=ww.get("uri", "tcp://127.0.0.1:10400"),
        wakeword_model=ww.get("model", "okay_computer"),
        wakeword_sound_detected=ww.get("sound_detected", ""),
        wakeword_sound_done=ww.get("sound_done", ""),
        wakeword_silence_seconds=float(ww.get("silence_seconds", 2.0)),
        wakeword_cancel_model=ww.get("cancel_model", ""),
        wakeword_send_model=ww.get("send_model", ""),
        tts_url=tts.get("url", "").rstrip("/"),
        tts_api_key_env=tts.get("api_key_env", ""),
        tts_model=tts.get("model", ""),
        tts_voices=list(tts.get("voices", ["alloy", "echo", "fable", "onyx", "nova", "shimmer"])),
        bench_wav=data.get("benchmark", {}).get("wav", ""),
        bench_ref=data.get("benchmark", {}).get("ref", ""),
        bench_expand_models=bool(data.get("benchmark", {}).get("expand_models", False)),
        bench_last=dict(data.get("benchmark", {}).get("last", {})),
    )

    for entry in data.get("workflow", []):
        cfg.workflows.append(
            Workflow(
                name=entry["name"],
                hotkey=entry.get("hotkey", ""),
                mode=entry.get("mode", "transcribe"),
                prompt=entry.get("prompt", ""),
                keywords=list(entry.get("keywords", [])),
                model=entry.get("model"),
                temperature=entry.get("temperature"),
                llm_engine=entry.get("llm_engine", ""),
                description=entry.get("description", ""),
                icon=entry.get("icon", "⚡"),
            )
        )

    if not cfg.workflows:
        raise ValueError(f"No [[workflow]] entries defined in {path}")

    # STT engines (default: a single local faster-whisper engine).
    cfg.stt_engines = [
        STTEngine(
            name=e["name"],
            type=e.get("type", "local"),
            url=e.get("url", "").rstrip("/"),
            model=e.get("model", ""),
            api_key_env=e.get("api_key_env", ""),
            timeout=int(e.get("timeout", 30)),
        )
        for e in data.get("stt_engine", [])
    ] or [STTEngine("Local faster-whisper", "local", model=cfg.model)]
    cfg.stt_active = data.get("stt", {}).get("active", cfg.stt_engines[0].name)

    # Wakeword engines for the benchmark (optional; benchmark falls back to the
    # live [wakeword] config when none are listed).
    cfg.wakeword_engines = [
        WakewordEngine(
            name=e.get("name", ""),
            uri=e.get("uri", "tcp://127.0.0.1:10400"),
            model=e.get("model", "okay_computer"),
            cancel_model=e.get("cancel_model", ""),
            send_model=e.get("send_model", ""),
        )
        for e in data.get("wakeword_engine", [])
    ]
    # Migration: ensure at least one engine exists so the CRUD UI always has a row.
    if not cfg.wakeword_engines:
        cfg.wakeword_engines = [WakewordEngine(
            name=cfg.wakeword_active or "Local wyoming-openwakeword",
            uri=cfg.wakeword_uri,
            model=cfg.wakeword_model,
            cancel_model=cfg.wakeword_cancel_model,
            send_model=cfg.wakeword_send_model,
        )]
    # Migration: older configs stored cancel/send globally; seed them onto the
    # active engine so per-profile values aren't blank on first load.
    if cfg.wakeword_cancel_model or cfg.wakeword_send_model:
        active = next((e for e in cfg.wakeword_engines if e.name == cfg.wakeword_active),
                      cfg.wakeword_engines[0])
        if not active.cancel_model:
            active.cancel_model = cfg.wakeword_cancel_model
        if not active.send_model:
            active.send_model = cfg.wakeword_send_model

    # LLM engines (default: synthesized from the legacy [rewrite] block).
    cfg.llm_engines = [
        LLMEngine(
            name=e["name"],
            url=e.get("url", "https://api.openai.com/v1").rstrip("/"),
            model=e.get("model", "gpt-4o-mini"),
            api_key_env=e.get("api_key_env", ""),
            temperature=float(e.get("temperature", cfg.temperature)),
            type=e.get("type", "cloud"),
        )
        for e in data.get("llm_engine", [])
    ] or [LLMEngine("Default", cfg.base_url, cfg.rewrite_model, cfg.api_key_env, cfg.temperature)]
    cfg.llm_active = data.get("llm", {}).get("active", cfg.llm_engines[0].name)

    return cfg


def save(cfg: Config, path: Path = CONFIG_PATH) -> None:
    """Write the config back to TOML (used by the settings UI).

    Note: inline comments from the template are not preserved on save.
    """
    import tomli_w

    data: dict = {
        "general": {
            "recorder": cfg.recorder,
            "mic": cfg.mic,
            "output": cfg.output,
            "type_delay_ms": cfg.type_delay_ms,
            "notify": cfg.notify,
            "setup_complete": cfg.setup_complete,
            "notify_routing": cfg.notify_routing,
            "language": cfg.language,
            "overlay_enabled": cfg.overlay_enabled,
            "overlay_anchor": cfg.overlay_anchor,
        },
        "whisper": {
            "model": cfg.model,
            "device": cfg.device,
            "compute_type": cfg.compute_type,
            "beam_size": cfg.beam_size,
        },
        "rewrite": {
            "base_url": cfg.base_url,
            "api_key_env": cfg.api_key_env,
            "model": cfg.rewrite_model,
            "temperature": cfg.temperature,
            "timeout": cfg.timeout,
        },
        "input": {
            "mode": cfg.input_mode,
            "push_to_talk": cfg.push_to_talk,
            "start": cfg.key_start,
            "stop": cfg.key_stop,
            "send": cfg.key_send,
            "cancel": cfg.key_cancel,
        },
        "routing": {
            "enabled": cfg.routing_enabled,
            "hotkey": cfg.routing_hotkey,
            "default": cfg.routing_default,
            "threshold": cfg.routing_threshold,
            "cancel_keywords": cfg.cancel_keywords,
            "send_keywords": cfg.send_keywords,
        },
        "quality": {
            "min_speech_seconds": cfg.min_speech_seconds,
            "silence_rms": cfg.silence_rms,
            "reject_hallucinations": cfg.reject_hallucinations,
            "strip_trailing_punctuation": cfg.strip_trailing_punctuation,
        },
        "sounds": {
            "enabled": cfg.sounds_enabled,
            "before": cfg.sound_before,
            "after": cfg.sound_after,
        },
        "wakeword": {
            "enabled": cfg.wakeword_enabled,
            "active": cfg.wakeword_active,
            "uri": cfg.wakeword_uri,
            "model": cfg.wakeword_model,
            "sound_detected": cfg.wakeword_sound_detected,
            "sound_done": cfg.wakeword_sound_done,
            "silence_seconds": cfg.wakeword_silence_seconds,
            "cancel_model": cfg.wakeword_cancel_model,
            "send_model": cfg.wakeword_send_model,
        },
        "tts": {
            "url": cfg.tts_url,
            "api_key_env": cfg.tts_api_key_env,
            "model": cfg.tts_model,
            "voices": cfg.tts_voices,
        },
        "benchmark": {
            "wav": cfg.bench_wav,
            "ref": cfg.bench_ref,
            "expand_models": cfg.bench_expand_models,
            "last": cfg.bench_last,
        },
        "wakeword_engine": [
            {"name": e.name, "uri": e.uri, "model": e.model,
             "cancel_model": e.cancel_model, "send_model": e.send_model}
            for e in cfg.wakeword_engines
        ],
        "stt": {"active": cfg.stt_active},
        "stt_engine": [
            {k: v for k, v in {
                "name": e.name, "type": e.type, "url": e.url,
                "model": e.model, "api_key_env": e.api_key_env,
                "timeout": e.timeout if e.timeout != 30 else None,
            }.items() if v is not None and (v or k in ("name", "type"))}
            for e in cfg.stt_engines
        ],
        "llm": {"active": cfg.llm_active},
        "llm_engine": [
            {"name": e.name, "type": e.type, "url": e.url, "model": e.model,
             "api_key_env": e.api_key_env, "temperature": e.temperature}
            for e in cfg.llm_engines
        ],
        "workflow": [],
    }
    for wf in cfg.workflows:
        entry: dict = {"name": wf.name, "hotkey": wf.hotkey, "mode": wf.mode}
        if wf.keywords:
            entry["keywords"] = wf.keywords
        if wf.prompt:
            entry["prompt"] = wf.prompt
        if wf.model:
            entry["model"] = wf.model
        if wf.temperature is not None:
            entry["temperature"] = wf.temperature
        if wf.llm_engine:
            entry["llm_engine"] = wf.llm_engine
        if wf.description:
            entry["description"] = wf.description
        if wf.icon and wf.icon != "⚡":
            entry["icon"] = wf.icon
        data["workflow"].append(entry)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        tomli_w.dump(data, fh)


def ensure_default(path: Path = CONFIG_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    return path


# Hotkey syntax is pynput's GlobalHotKeys format, e.g. "<ctrl>+<alt>+space".
DEFAULT_CONFIG = """\
# Blitztext for Linux — configuration
# Hotkey format follows pynput: <ctrl> <alt> <shift> <cmd> + a letter/keyname.
# Each hotkey TOGGLES recording: press to start speaking, press again to finish.

[general]
recorder = "auto"        # auto | pw-record | parecord | arecord
output = "type"          # "type" = xdotool types it; "paste" = clipboard + Ctrl+V
type_delay_ms = 12       # per-keystroke delay for xdotool type (raise if chars drop)
notify = true            # desktop notifications for each phase
notify_routing = true    # announce which preset/keyword a voice command matched (shown even hands-free)
language = "de"          # Whisper language hint; "" = autodetect
overlay_enabled = true   # on-screen mic + live waveform + recognised-text bubble at the cursor
overlay_anchor = "pointer" # pointer (near the mouse — safe) | caret (AT-SPI, may freeze) | corner

[input]
# How you start/stop dictation.
#   mode = "modifiers"  ->  Ctrl+Win start | Ctrl stop+paste | Alt stop+paste+Enter | Esc cancel
#   mode = "hotkeys"    ->  the per-preset combos + the [routing] hotkey below
# Voice-keyword routing still applies to what you say in either mode.
mode = "modifiers"
push_to_talk = false     # modifiers mode: hold Start to record, release to stop+paste
start = "<ctrl>+<cmd>"   # <cmd> = the Super/Windows key
stop = "<ctrl>"
send = "<alt>"
cancel = "<esc>"

[quality]
# Reject silence/too-short clips and the stock phrases Whisper invents on
# silence (e.g. "Thank you.", "Untertitel ...") so you don't paste garbage.
min_speech_seconds = 0.4         # discard clips shorter than this
silence_rms = 150.0              # discard clips quieter than this RMS (0..32767)
reject_hallucinations = true
strip_trailing_punctuation = false

[sounds]
# Audio cues for MANUAL (keyboard/hotkey) dictation. The hands-free wakeword
# cues are separate and independent — see [wakeword] sound_detected/sound_done.
# enabled = on/off for these manual cues. "before"/"after" are optional WAV
# files; leave empty for the built-in system sound. "before" plays when
# recording starts; "after" on any stop (paste, paste+Enter, or auto-stop).
enabled = true
before = ""
after = ""

[whisper]
model = "small"          # tiny | base | small | medium | large-v3, or a local path
device = "auto"          # auto | cuda | cpu  (auto tries cuda, falls back to cpu)
compute_type = "auto"    # auto | int8 | float16 | int8_float16
beam_size = 5

[rewrite]
# OpenAI-compatible chat endpoint. Define your own provider/API/model here.
# Point base_url at OpenAI, OR any local server that speaks the OpenAI chat API
# (vLLM, llama-swap, Ollama's /v1, LM Studio, ...). Examples:
#   base_url = "https://api.openai.com/v1"          (OpenAI)
#   base_url = "http://localhost:8000/v1"           (local vLLM / llama-swap)
# api_key_env names the ENV VAR holding the key (local servers often ignore it).
base_url = "https://api.openai.com/v1"
api_key_env = "OPENAI_API_KEY"
model = "gpt-4o-mini"            # default model for rewrite workflows
temperature = 0.3
timeout = 45

[routing]
# Voice-keyword routing: ONE hotkey to dictate. Say a preset's keyword at the
# START or END of your speech and that preset is applied; otherwise the default
# preset is used. (Per-preset hotkeys below still work as direct shortcuts.)
enabled = true
hotkey = "<ctrl>+<alt>+<space>"
default = "Transcribe"   # preset used when no keyword is recognised
threshold = 0.82         # 0..1 fuzzy-match strictness (higher = stricter)
# Say one of these at the start or end of a clip to DISCARD it — nothing is
# routed, rewritten, or typed. Handy when a wakeword fires by accident. Pick
# words you won't naturally end a real dictation with. Empty list = off.
cancel_keywords = ["abbrechen", "cancel"]
# Say one of these at the start or end of a clip to SEND it: the word is stripped
# and the rest is delivered AND submitted with Enter (spoken "stop+paste+Enter").
# Because it presses Enter, use a distinctive multi-word phrase (e.g. your
# wakeword + "send") so a sentence that just ends in "send" won't submit. Off by
# default; empty list = off.
send_keywords = []

[wakeword]
# Hands-free dictation using an external wyoming-openwakeword server.
# Respects the /tmp/wake_muted file to disable listening.
enabled = false
uri = "tcp://127.0.0.1:10400"
model = "okay_computer"
# Audio cues for hands-free sessions, independent of [sounds] above: play the
# given WAV when the wakeword fires (speak now) and when the command is captured.
# Leave empty for NO sound — these are a hands-free session's only feedback,
# since its desktop notifications are suppressed.
sound_detected = ""
sound_done = ""
# Auto-stop the recording this many seconds after you stop speaking (silence).
silence_seconds = 2.0

[tts]
# Text-to-speech for the WAKEWORD BENCHMARK only (Settings → Benchmark). Point it
# at any OpenAI-compatible TTS server's /audio/speech (Kokoro-FastAPI, XTTS-v2,
# OpenAI, …). url = base incl. /v1; api_key_env = env var holding a bearer key
# (leave empty for no-auth local servers); model = the TTS model id; voices = the
# names your endpoint serves. Leave url/model empty to disable the benchmark.
url = ""
api_key_env = ""
model = ""
voices = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]

# Wakeword engines to COMPARE in the benchmark — add one block per
# wyoming-openwakeword endpoint/model you want side by side. Leave this out to
# just benchmark the live [wakeword] engine above.
# [[wakeword_engine]]
# name = "openWakeWord · computer"
# uri = "tcp://127.0.0.1:10400"
# model = "computer"
#
# [[wakeword_engine]]
# name = "microWakeWord · hey_jarvis"
# uri = "tcp://127.0.0.1:10500"
# model = "hey_jarvis"

# ----------------------------------------------------------------------------
# Speech-to-text engines (presets). The active one is used for transcription.
#   type = "local"  -> in-process faster-whisper (uses [whisper] above)
#   type = "openai" -> remote OpenAI-compatible /audio/transcriptions server
#                      (faster-whisper-server, Groq, WhisperX, batch ASR NIMs, ...)
#   type = "riva_realtime" -> Riva/NIM realtime WebSocket STT, for mode="stream"
# ----------------------------------------------------------------------------
[stt]
active = "Local faster-whisper"

[[stt_engine]]
name = "Local faster-whisper"
type = "local"

# [[stt_engine]]
# name = "faster-whisper-server"
# type = "openai"
# url = "http://localhost:8010/v1"
# model = "Systran/faster-whisper-base"
# api_key_env = ""            # e.g. GROQ_API_KEY for a cloud endpoint

# [[stt_engine]]
# name = "Nemotron ASR Streaming"
# type = "riva_realtime"
# url = "http://localhost:8006/v1"
# model = ""                  # blank = use the realtime server default
# api_key_env = ""

# ----------------------------------------------------------------------------
# LLM engines (presets) for the rewrite step. Any OpenAI-compatible chat API
# (OpenAI, vLLM, llama-swap, Ollama /v1, LM Studio, Groq, OpenRouter, ...).
# ----------------------------------------------------------------------------
[llm]
active = "Default"

[[llm_engine]]
name = "Default"
type = "cloud"           # "local" | "cloud"
url = "https://api.openai.com/v1"
model = "gpt-4o-mini"
api_key_env = "OPENAI_API_KEY"
temperature = 0.3

# [[llm_engine]]
# name = "Local llama-swap"
# type = "local"
# url = "http://localhost:28080/v1"
# model = "Qwen3.5-4B"
# api_key_env = ""
# temperature = 0.3

# ----------------------------------------------------------------------------
# Workflows / presets. mode = "transcribe" types the raw transcript. mode =
# "rewrite" sends it through the LLM with `prompt` as the system prompt.
# "stream" writes live words via a riva_realtime STT engine.
#   keywords = spoken trigger phrases for voice routing (start or end of speech)
#   hotkey   = optional direct global hotkey ("" = none; voice routing is primary)
# A workflow may override the [rewrite] defaults with its own model/temperature.
# ----------------------------------------------------------------------------

[[workflow]]
name = "Transcribe"
icon = "⚡"
description = "Speak, get plain text."
hotkey = ""
mode = "transcribe"

# [[workflow]]
# name = "STT Streaming"
# icon = "⚡"
# description = "Live words while you speak."
# hotkey = "<ctrl>+<alt>+s"
# mode = "stream"

[[workflow]]
name = "Nicer email"
icon = "✉"
description = "Rough notes → polished email."
keywords = ["nicer email", "bessere email", "schöne mail"]
hotkey = "<ctrl>+<alt>+e"
mode = "rewrite"
prompt = '''Du bist ein Schreibassistent fuer E-Mails. Du erhaeltst ein gesprochenes Transkript.
Schreibe daraus eine freundliche, gut formulierte und etwas ausfuehrlichere E-Mail:
- Korrigiere Rechtschreibung und Grammatik
- Formuliere hoeflich, klar und professionell
- Ergaenze sinnvolle Hoeflichkeitsfloskeln (Anrede/Gruss), wenn passend
- Behalte die urspruengliche Aussage und Absicht bei, erfinde keine Fakten
- Antworte in der Sprache des Transkripts
- Gib NUR den E-Mail-Text zurueck, keine Erklaerungen'''

[[workflow]]
name = "Improve text"
icon = "✨"
description = "Speak → cleaner writing."
keywords = ["improve text", "verbessere text", "bessere schreibweise"]
hotkey = "<ctrl>+<alt>+i"
mode = "rewrite"
prompt = '''Du bist ein Lektor und Schreibassistent. Verbessere den folgenden gesprochenen Text:
- Korrigiere Rechtschreibung und Grammatik
- Verbessere Formulierung und Lesefluss, behalte die Bedeutung bei
- Antworte in der Sprache des Transkripts
- Gib NUR den verbesserten Text zurueck, keine Erklaerungen'''

[[workflow]]
name = "Calm down"
icon = "☺"
description = "Frustrated in → calm out."
keywords = ["calm down", "beruhige das", "entspannte nachricht"]
hotkey = "<ctrl>+<alt>+c"
mode = "rewrite"
prompt = '''Du erhaeltst ein gesprochenes, frustriertes oder veraergertes Transkript.
Formuliere es in eine ruhige, sachliche und hoefliche Nachricht um, die dasselbe
Anliegen professionell vermittelt. Antworte in der Sprache des Transkripts.
Gib NUR die umformulierte Nachricht zurueck, keine Erklaerungen.'''

[[workflow]]
name = "Add emojis"
icon = "✿"
description = "Text in → emojis out."
keywords = ["add emojis", "mit emojis", "emojis dazu"]
hotkey = "<ctrl>+<alt>+j"
mode = "rewrite"
prompt = '''Du erhaeltst ein gesprochenes Transkript. Gib den Text moeglichst originalgetreu
zurueck, fuege aber regelmaessig passende Emojis ein (etwa alle 1-2 Saetze).
Korrigiere offensichtliche Fehler, behalte Stil und Bedeutung bei.
Gib NUR den Text mit Emojis zurueck, keine Erklaerungen.'''
"""

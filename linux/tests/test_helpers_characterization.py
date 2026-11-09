"""Characterization tests for small parsing/dispatch paths split up for SonarQube."""

import io
import json
from unittest import mock

import pytest

from blitztext import paste, sound, stt, talk, tts, wakeword_bench
from blitztext.streaming import RivaRealtimeStreamer, StreamingSTTError


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _urlopen(responses):
    def fake(req, timeout=None):
        url = req.full_url
        body = responses.get(url)
        if body is None:
            raise OSError("nope")
        return _Resp(body if isinstance(body, bytes) else json.dumps(body).encode())
    return fake


@pytest.mark.parametrize("responses, expected", [
    ({"http://h/v1/models": {"data": [{"id": "a", "language": ["de"]}, {"x": 1}, "bad"]}},
     [("a", ["de"])]),
    ({"http://h/v1/models": {"models": [{"name": "llama"}, {"model": "m2"}, {}]}},
     [("llama", []), ("m2", [])]),
    ({"http://h/v1/models": {"data": []},
      "http://h/v1/metadata": {"modelInfo": [{"shortName": ""}, {"modelUrl": "riva:1"}]}},
     [("riva", [])]),
    ({"http://h/v1/models": {"models": []}, "http://h/v1/metadata": {"modelInfo": [{"shortName": "x"}]}},
     []),
    ({}, []),
])
def test_list_models_meta(responses, expected):
    with mock.patch.object(tts, "urlopen", side_effect=_urlopen(responses)):
        got = stt.list_models_meta("http://h/v1/transcribe")
    assert [(m.id, m.languages) for m in got] == expected


def test_probe_server_ram_mb():
    text = b"# HELP x\nprocess_resident_memory_bytes abc\ncontainer_memory_rss 2097152\n"
    with mock.patch.object(tts, "urlopen",
                           side_effect=_urlopen({"http://h/v1/metrics": text})):
        assert stt.probe_server_ram_mb("http://h/v1") == 2.0
    with mock.patch.object(tts, "urlopen",
                           side_effect=_urlopen({"http://h/metrics": b"# process_resident_memory_bytes 1\n"})):
        assert stt.probe_server_ram_mb("http://h/v1") is None


def _which(available):
    return lambda name: f"/usr/bin/{name}" if name in available else None


@pytest.mark.parametrize("env, tools, mode, text, expected", [
    ("x11", {"xdotool", "xclip"}, "type", "hi", [["xdotool", "type", "--clearmodifiers", "--delay", "4", "--", "hi"]]),
    ("x11", {"xdotool", "xclip"}, "paste", "hi", [["xclip", "-selection", "clipboard"],
                                                  ["xdotool", "key", "--clearmodifiers", "ctrl+v"]]),
    # long/multi-line text: clipboard is set twice (upgrade check + paste path)
    ("x11", {"xdotool", "xclip"}, "type", "a\nb", [["xclip", "-selection", "clipboard"],
                                                   ["xclip", "-selection", "clipboard"],
                                                   ["xdotool", "key", "--clearmodifiers", "ctrl+v"]]),
    ("x11", {"xdotool"}, "type", "a\nb", [["xdotool", "type", "--clearmodifiers", "--delay", "4", "--", "a\nb"]]),
    ("wayland", {"wtype", "wl-copy"}, "paste", "hi", [["wl-copy"], ["wtype", "-M", "ctrl", "v", "-m", "ctrl"]]),
    ("wayland", {"ydotool"}, "type", "hi", [["ydotool", "type", "-d", "4", "hi"]]),
    ("wayland", {"ydotool", "wl-copy"}, "paste", "hi", [["wl-copy"], ["ydotool", "key", "ctrl+v"]]),
])
def test_deliver(monkeypatch, env, tools, mode, text, expected):
    monkeypatch.setenv("XDG_SESSION_TYPE", env)
    calls = []
    monkeypatch.setattr(paste.shutil, "which", _which(tools))
    monkeypatch.setattr(paste.subprocess, "run", lambda argv, **k: calls.append(argv))
    monkeypatch.setattr(paste.time, "sleep", lambda s: None)
    paste.deliver(text, mode=mode)
    assert calls == expected


@pytest.mark.parametrize("env, tools, msg", [
    ("x11", set(), "xdotool not found"),
    ("wayland", set(), "wtype or ydotool"),
])
def test_deliver_missing_tool(monkeypatch, env, tools, msg):
    monkeypatch.setenv("XDG_SESSION_TYPE", env)
    monkeypatch.setattr(paste.shutil, "which", _which(tools))
    with pytest.raises(RuntimeError, match=msg):
        paste.deliver("x")


def test_sound_play_selection(monkeypatch, tmp_path):
    started = []
    monkeypatch.setattr(sound, "validate_sound_path", lambda p: p if p.endswith(".mp3") else None)
    monkeypatch.setattr(sound.os.path, "exists", lambda p: True)
    monkeypatch.setattr(sound.subprocess, "Popen", lambda argv, **k: started.append(argv) or "proc")
    monkeypatch.setattr(sound.shutil, "which", lambda n: "/x")
    assert sound.play("/a.mp3") == "proc"
    first_ok = [p for p, e, w in sound._PLAYERS
                if not w and not (p == "paplay" and ".mp3" not in sound._NATIVE_EXTS)][0]
    assert started[-1][0] == first_ok and started[-1][-1] == "/a.mp3"
    assert sound.play("/bad.txt", fallback="bell") == "proc"
    assert started[-1][-1] == sound._FREEDESKTOP.format(name="bell")
    assert sound.play("/bad.txt") is None


@pytest.mark.parametrize("env, primary, tools, expected", [
    ("wayland", True, {"wl-paste", "xclip"}, ["wl-paste", "-p"]),
    ("wayland", False, {"xsel"}, ["xsel", "-o", "--clipboard"]),
    ("x11", True, {"wl-paste", "xclip"}, ["xclip", "-o", "-selection", "primary"]),
    ("x11", False, set(), None),
])
def test_read_clip(monkeypatch, env, primary, tools, expected):
    monkeypatch.setenv("XDG_SESSION_TYPE", env)
    monkeypatch.setattr(talk.shutil, "which", _which(tools))
    calls = []
    monkeypatch.setattr(talk.subprocess, "check_output", lambda c, **k: calls.append(c) or b"x")
    assert talk._read_clip(primary=primary) == (b"x" if expected else b"")
    assert calls == ([expected] if expected else [])


def test_split_text():
    text = "Eins. Zwei! Drei?\n\n" + "A" * 50 + ". Kurz."
    assert talk.split_text(text, limit=20) == ["Eins. Zwei! Drei?", "A" * 50 + ".", "Kurz."]
    assert talk.split_text("a. b.\n\nc.", limit=100) == ["a. b. c."]
    assert talk.split_text("", limit=10) == []


def test_voice_names():
    f = wakeword_bench._voice_names
    assert f(["a", {"id": "b"}, {"name": "c"}, {"voice": 3}, {}, 5]) == ["a", "b", "c", "3"]
    assert f({"voices": ["x"]}) == ["x"]
    assert f({"data": [{"id": "y"}]}) == ["y"]
    assert f({"other": 1}) == []
    assert f(None) == []


def test_realtime_event_dispatch():
    got = []
    s = RivaRealtimeStreamer.__new__(RivaRealtimeStreamer)
    s.on_text = lambda t, f: got.append((t, f))

    class WS:
        def __init__(self, events):
            self.events = [json.dumps(e) for e in events]

        async def recv(self):
            return self.events.pop(0)

    import asyncio
    events = [
        {"type": "conversation.item.input_audio_transcription.delta", "delta": " hal "},
        {"type": "conversation.item.input_audio_transcription.delta", "delta": ""},
        {"type": "other"},
        {"type": "conversation.item.input_audio_transcription.completed", "transcript": "hallo"},
        {"type": "conversation.item.input_audio_transcription.completed", "transcript": "", "is_last_result": True},
    ]
    asyncio.run(s._receive_text(WS(events)))
    assert got == [("hal", False), ("hallo", True)]
    with pytest.raises(StreamingSTTError, match="boom"):
        asyncio.run(s._receive_text(WS([{"type": "error", "error": {"message": "boom"}}])))
    with pytest.raises(StreamingSTTError, match="Transcription failed."):
        asyncio.run(s._receive_text(WS([{"type": "conversation.item.input_audio_transcription.failed"}])))

"""Coverage tests for blitztext.streaming with fake websockets/sounddevice modules."""
import asyncio
import json
import sys
import types

import pytest

from blitztext import streaming as st, tts
from blitztext.stt import STTEngine


def test_single_language():
    assert st._single_language("bn-IN, en-US,hi-IN") == "en-US"
    assert st._single_language("de-DE,fr-FR") == "de-DE"
    assert st._single_language(" , ") == ""


@pytest.mark.parametrize("base,sess,ws", [
    ("localhost:9000", "http://localhost:9000/v1/realtime/transcription_sessions", "ws://localhost:9000/v1/realtime?intent=transcription"),
    ("https://h/v1/", "https://h/v1/realtime/transcription_sessions", "wss://h/v1/realtime?intent=transcription"),
    ("http://h/x/realtime", "http://h/x/realtime/transcription_sessions", "ws://h/x/realtime?intent=transcription"),
    ("ftp://h", "http://h/v1/realtime/transcription_sessions", "ws://h/v1/realtime?intent=transcription"),
])
def test_realtime_urls(base, sess, ws):
    u = st.realtime_urls(base)
    assert (u.session_url, u.websocket_url) == (sess, ws)


@pytest.mark.parametrize("bad", ["", "   ", None])
def test_realtime_urls_missing(bad):
    with pytest.raises(st.StreamingSTTError):
        st.realtime_urls(bad)


def make(**kw):
    eng = STTEngine("s", "riva_realtime", "http://127.0.0.1:1", model=kw.pop("model", ""),
                    api_key_env=kw.pop("env", ""))
    return st.RivaRealtimeStreamer(eng, **kw)


def test_auth_headers(monkeypatch):
    monkeypatch.setenv("FAKE_RT_KEY", "fake-key")
    monkeypatch.delenv("FAKE_RT_MISSING", raising=False)
    assert make()._auth_headers() == {}
    assert make(env="FAKE_RT_KEY")._auth_headers() == {"Authorization": "Bearer fake-key"}
    assert make(env="FAKE_RT_MISSING")._auth_headers() == {}


def test_handle_event_paths():
    got = []
    s = make(on_text=lambda t, f: got.append((t, f)))
    assert s._handle_event({"type": "conversation.item.input_audio_transcription.delta", "delta": " hi "}) is False
    assert s._handle_event({"type": "conversation.item.input_audio_transcription.completed", "transcript": "hi there"}) is False
    assert s._handle_event({"type": "conversation.item.input_audio_transcription.completed", "transcript": "", "is_last_result": True}) is True
    assert s._handle_event({"type": "other"}) is False
    assert got == [("hi", False), ("hi there", True)]
    with pytest.raises(st.StreamingSTTError, match="bad audio"):
        s._handle_event({"type": "conversation.item.input_audio_transcription.failed", "error": {"message": "bad audio"}})
    with pytest.raises(st.StreamingSTTError, match="Transcription failed"):
        s._handle_event({"type": "conversation.item.input_audio_transcription.failed"})
    with pytest.raises(st.StreamingSTTError, match="boom"):
        s._handle_event({"type": "error", "error": {"message": "boom"}})
    with pytest.raises(st.StreamingSTTError, match="code"):
        s._handle_event({"type": "error", "error": {"code": 1}})
    make()._emit_text("x", True)  # no callback: no crash


def test_resolve_device():
    class SD:
        @staticmethod
        def query_devices():
            return [{"max_input_channels": 0, "name": "Mic"}, {"max_input_channels": 2, "name": "USB Mic"}]

    assert make()._resolve_device(SD) is None
    assert make(device="Mic")._resolve_device(SD) == 1
    assert make(device="zzz")._resolve_device(SD) is None

    class Bad:
        @staticmethod
        def query_devices():
            raise OSError("no audio")

    assert make(device="Mic")._resolve_device(Bad) is None


class WS:
    def __init__(self, incoming):
        self.incoming, self.sent, self.closed = list(incoming), [], False

    async def recv(self):
        if self.incoming:
            return json.dumps(self.incoming.pop(0))
        await asyncio.sleep(30)

    async def send(self, m):
        self.sent.append(json.loads(m))

    async def close(self):
        self.closed = True


GREET = {"type": "conversation.created"}
UPDATED = {"type": "transcription_session.updated"}


def run(coro):
    return asyncio.run(asyncio.wait_for(coro, timeout=5))


def test_initialize_language_and_model():
    s = make(model="m1")
    ws = WS([GREET, UPDATED])
    run(s._initialize_websocket(ws, {"input_audio_transcription": {"language": "bn-IN,en-US,indic"}}))
    sess = ws.sent[0]["session"]
    assert sess["input_audio_format"] == "pcm16"
    assert sess["input_audio_params"] == {"sample_rate_hz": 16000, "num_channels": 1}
    assert sess["recognition_config"]["max_alternatives"] == 1
    assert sess["input_audio_transcription"] == {"language": "en-US", "model": "m1"}
    # explicit hint wins; session input untouched
    s = make(language=" de-DE ")
    ws = WS([GREET, UPDATED])
    run(s._initialize_websocket(ws, {}))
    assert ws.sent[0]["session"]["input_audio_transcription"] == {"language": "de-DE"}
    # single-code default kept, no model -> no key created
    ws = WS([GREET, UPDATED])
    run(make()._initialize_websocket(ws, {"input_audio_transcription": {"language": "fr-FR"}}))
    assert ws.sent[0]["session"]["input_audio_transcription"] == {"language": "fr-FR"}


def test_initialize_failures():
    with pytest.raises(st.StreamingSTTError, match="greeting"):
        run(make()._initialize_websocket(WS([{"type": "nope"}]), {}))
    with pytest.raises(st.StreamingSTTError, match="update failed"):
        run(make()._initialize_websocket(WS([GREET, {"type": "error"}]), {}))
    with pytest.raises(asyncio.TimeoutError):
        async def go():
            ws = WS([])
            async def fast(coro, timeout):  # not used; real timeout is 5s -> emulate with tiny wait
                raise asyncio.TimeoutError
            import unittest.mock as m
            with m.patch.object(asyncio, "wait_for", fast):
                await make()._initialize_websocket(ws, {})
        run(go())


def test_connect_websocket_header_kwarg_fallback():
    calls = []

    async def connect(url, **kw):
        calls.append(kw)
        if "additional_headers" in kw:
            raise TypeError("old websockets")
        return "conn"

    mod = types.SimpleNamespace(connect=connect)
    assert run(make()._connect_websocket(mod, "ws://x", {"A": "b"})) == "conn"
    assert calls == [{"additional_headers": {"A": "b"}}, {"extra_headers": {"A": "b"}}]


def test_send_chunk_and_send_audio_drain():
    import base64
    import queue
    s = make()
    ws = WS([])
    q = queue.Queue()
    q.put(b"\x01\x02")
    s._stop.set()
    run(s._send_audio(ws, q))
    assert [m["type"] for m in ws.sent] == [
        "input_audio_buffer.append", "input_audio_buffer.commit", "input_audio_buffer.done"]
    assert base64.b64decode(ws.sent[0]["audio"]) == b"\x01\x02"


def test_send_audio_loop_sends_then_stops():
    import queue
    s = make()
    ws = WS([])
    q = queue.Queue()
    q.put(b"\x09")

    async def go():
        t = asyncio.create_task(s._send_audio(ws, q))
        await asyncio.sleep(0.5)  # one empty poll (0.2s) covers queue.Empty branch
        s._stop.set()
        await t

    run(go())
    assert ws.sent[0]["type"] == "input_audio_buffer.append"
    assert ws.sent[-1]["type"] == "input_audio_buffer.done"


def test_receive_text_streams_until_last(monkeypatch):
    got = []
    s = make(on_text=lambda t, f: got.append((t, f)))
    ws = WS([
        {"type": "conversation.item.input_audio_transcription.delta", "delta": "he"},
        {"type": "conversation.item.input_audio_transcription.completed", "transcript": "hello", "is_last_result": True},
    ])
    run(s._receive_text(ws))
    assert got == [("he", False), ("hello", True)]


def test_receive_text_timeout_retries():
    got = []
    s = make(on_text=lambda t, f: got.append(t))

    class Slow(WS):
        n = 0

        async def recv(self):
            Slow.n += 1
            if Slow.n == 1:
                raise asyncio.TimeoutError
            return json.dumps({"type": "conversation.item.input_audio_transcription.completed",
                               "transcript": "x", "is_last_result": True})

    run(s._receive_text(Slow([])))
    assert got == ["x"]


def test_create_session_ok_and_errors(monkeypatch):
    import io
    import urllib.error
    import urllib.request

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    seen = {}

    def ok(req, timeout):
        seen["req"], seen["t"] = req, timeout
        return Resp(b'{"id": "sess"}')

    monkeypatch.setenv("FAKE_RT_KEY", "fake-key")
    monkeypatch.setattr(tts, "urlopen", ok)
    s = make(env="FAKE_RT_KEY")
    assert s._create_session("http://h/x") == {"id": "sess"}
    assert seen["req"].get_header("Authorization") == "Bearer fake-key"
    assert seen["req"].get_method() == "POST" and seen["t"] == 10

    def http_err(req, timeout):
        raise urllib.error.HTTPError("http://h/x", 503, "x", {}, io.BytesIO(b"overloaded"))

    monkeypatch.setattr(tts, "urlopen", http_err)
    with pytest.raises(st.StreamingSTTError, match="HTTP 503.*overloaded") as ei:
        s._create_session("http://h/x")
    assert "fake-key" not in str(ei.value)

    def url_err(req, timeout):
        raise urllib.error.URLError("refused")

    monkeypatch.setattr(tts, "urlopen", url_err)
    with pytest.raises(st.StreamingSTTError, match="Cannot initialize"):
        s._create_session("http://h/x")

    monkeypatch.setattr(tts, "urlopen", lambda r, timeout: Resp(b"<html>"))
    with pytest.raises(st.StreamingSTTError, match="Cannot initialize"):
        s._create_session("http://h/x")


def _fake_modules(monkeypatch, ws, status="overflow"):
    holder = {}

    class Stream:
        def __init__(self, **kw):
            holder["kw"] = kw

        def __enter__(self):
            holder["kw"]["callback"](b"\x05\x06", 1, None, status)
            return self

        def __exit__(self, *a):
            return False

    async def connect(url, **kw):
        holder["url"], holder["hdr"] = url, kw
        return ws

    monkeypatch.setitem(sys.modules, "sounddevice", types.SimpleNamespace(RawInputStream=Stream, query_devices=lambda: []))
    monkeypatch.setitem(sys.modules, "websockets", types.SimpleNamespace(connect=connect))
    return holder


def test_run_full_session(monkeypatch):
    texts, stats = [], []
    ws = WS([GREET, UPDATED,
             {"type": "conversation.item.input_audio_transcription.completed", "transcript": "done", "is_last_result": True}])
    holder = _fake_modules(monkeypatch, ws)
    monkeypatch.setenv("FAKE_RT_KEY", "fake-key")
    s = make(env="FAKE_RT_KEY", on_text=lambda t, f: texts.append((t, f)), on_status=stats.append)
    monkeypatch.setattr(s, "_create_session", lambda url: {"id": "s"})
    s._stop.set()
    run(s._run())
    assert texts == [("done", True)]
    assert stats == ["Streaming", "overflow"] or stats == ["overflow", "Streaming"] or set(stats) == {"Streaming", "overflow"}
    assert holder["url"].endswith("/v1/realtime?intent=transcription")
    assert holder["hdr"] == {"additional_headers": {"Authorization": "Bearer fake-key"}}
    assert ws.closed and s._ready.is_set()
    types_sent = [m["type"] for m in ws.sent]
    assert types_sent[0] == "transcription_session.update" and types_sent[-1] == "input_audio_buffer.done"


def test_run_missing_packages(monkeypatch):
    monkeypatch.setitem(sys.modules, "sounddevice", None)  # import raises ModuleNotFoundError-like ImportError
    s = make()
    with pytest.raises((st.StreamingSTTError, ImportError)):
        run(s._run())


def test_start_surfaces_error_and_calls_on_error(monkeypatch):
    errs = []
    s = make(on_error=errs.append)
    monkeypatch.setattr(s, "_create_session", lambda url: (_ for _ in ()).throw(st.StreamingSTTError("down")))
    _fake_modules(monkeypatch, WS([]))
    with pytest.raises(st.StreamingSTTError, match="down"):
        s.start()
    s.stop()
    assert len(errs) == 1
    s.start()  # second start is a no-op (thread exists)... error already stored

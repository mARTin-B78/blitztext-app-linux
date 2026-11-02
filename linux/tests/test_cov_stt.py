"""Coverage tests for blitztext.stt using a local 127.0.0.1 HTTP server."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from blitztext import stt
from blitztext.stt import STTEngine, STTError


class _Srv:
    def __init__(self, routes):
        self.routes, self.seen = routes, []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _do(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n) if n else b""
                outer.seen.append((self.command, self.path, dict(self.headers), body))
                code, payload = outer.routes.get(self.path, (404, b"nope"))
                if not isinstance(payload, bytes):
                    payload = json.dumps(payload).encode()
                self.send_response(code)
                self.end_headers()
                self.wfile.write(payload)

            do_GET = do_POST = _do

        self.httpd = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"
        self.t = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.t.start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.t.join(2)


@pytest.fixture
def srv():
    made = []

    def make(routes):
        s = _Srv(routes)
        made.append(s)
        return s

    yield make
    for s in made:
        s.close()


@pytest.fixture
def wav(tmp_path):
    p = tmp_path / "a.wav"
    p.write_bytes(b"RIFFfake")
    return p


def _closed_url():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return f"http://127.0.0.1:{port}"


def test_reachable_and_status(srv):
    s = srv({})
    assert stt.reachable(s.url, 1)
    assert stt.reachable(s.url.replace("http://", ""), 1)  # no scheme
    assert not stt.reachable(_closed_url(), 0.5)
    assert not stt.reachable("", 0.1)
    assert not stt.reachable("http://host:notaport", 0.1)
    assert stt.status(STTEngine("l"))
    assert stt.status(STTEngine("r", "openai", s.url), 1)
    assert not stt.status(STTEngine("r", "openai", _closed_url()), 0.5)


def test_host_port_defaults():
    assert stt._host_port("https://h") == ("h", 443)
    assert stt._host_port("h") == ("h", 80)
    assert stt._host_port("http://h:99/v1") == ("h", 99)


@pytest.mark.parametrize("langs,out", [
    ([], "—"), (["en", "de"], "en, de"),
    (list("abcdefg"), "a, b, c, d, e +2"), (["x"] * 50, "multilingual (50)"),
])
def test_fmt_languages(langs, out):
    assert stt.fmt_languages(langs) == out


@pytest.mark.parametrize("url,out", [
    ("http://h:1/v1/transcribe", "http://h:1/v1"),
    ("http://h:1/transcribe", "http://h:1"),
    ("http://h:1/v1/", "http://h:1/v1"),
    ("http://h:1", "http://h:1"),
])
def test_api_base(url, out):
    assert stt._api_base(url) == out


def test_list_models_openai_with_key_and_languages(srv, monkeypatch):
    s = srv({"/v1/models": (200, {"data": [{"id": "m1", "language": ["en"]}, {"id": ""}, "junk", {"id": "m2"}]})})
    monkeypatch.setenv("FAKE_STT_KEY", "fake-secret")
    meta = stt.list_models_meta(s.url + "/v1", "FAKE_STT_KEY", 2)
    assert [(m.id, m.languages) for m in meta] == [("m1", ["en"]), ("m2", [])]
    assert s.seen[0][2]["Authorization"] == "Bearer fake-secret"
    assert stt.list_models(s.url + "/v1", timeout=2, api_key="explicit") == ["m1", "m2"]
    assert s.seen[-1][2]["Authorization"] == "Bearer explicit"


def test_list_models_ollama_shape(srv):
    s = srv({"/models": (200, {"models": [{"name": "a"}, {"model": "b"}, {}]})})
    assert stt.list_models(s.url, timeout=2) == ["a", "b"]


def test_list_models_riva_metadata_fallback(srv):
    s = srv({"/models": (200, {"data": []}),
             "/metadata": (200, {"modelInfo": [{"shortName": "parakeet:1.0"}]})})
    assert stt.list_models(s.url, timeout=2) == ["parakeet"]


def test_list_models_failures(srv):
    assert stt.list_models("") == []
    assert stt.list_models(_closed_url(), timeout=0.5) == []
    s = srv({"/models": (200, b"not json"), "/metadata": (200, {"modelInfo": [{}]})})
    assert stt.list_models(s.url, timeout=2) == []
    assert stt._models_from_listing([1]) is None
    assert stt._models_from_listing({"x": 1}) is None
    assert stt._models_from_metadata(None) == []


def test_parse_rss_mb():
    txt = "# HELP x\nfoo 1\nprocess_resident_memory_bytes 1048576\n"
    assert stt._parse_rss_mb(txt) == 1.0
    assert stt._parse_rss_mb("container_memory_rss 2097152") == 2.0
    assert stt._parse_rss_mb("process_resident_memory_bytes abc\nprocess_resident_memory_bytes") is None
    assert stt._parse_rss_mb("") is None


def test_probe_server_ram(srv):
    s = srv({"/metrics": (200, b"process_resident_memory_bytes 3145728\n")})
    assert stt.probe_server_ram_mb(s.url + "/v1", 2) == 3.0
    assert stt.probe_server_ram_mb("") is None
    s2 = srv({"/metrics": (200, b"nothing"), "/v1/metrics": (200, b"container_memory_rss 1048576")})
    assert stt.probe_server_ram_mb(s2.url + "/v1", 2) == 1.0
    assert stt.probe_server_ram_mb(_closed_url(), 0.5) is None


def test_detect_remote_device(srv):
    assert stt.detect_remote_device("") == "remote"
    assert stt.detect_remote_device(srv({"/info": (200, {"device": "CUDA:0"})}).url, 2) == "CUDA"
    assert stt.detect_remote_device(srv({"/info": (200, {"device": "cpu"})}).url, 2) == "CPU"
    assert stt.detect_remote_device(srv({"/metadata": (200, {"modelInfo": [1]})}).url, 2) == "CUDA"
    assert stt.detect_remote_device(srv({"/info": (200, {}), "/metadata": (200, [])}).url, 2) == "remote"
    assert stt.detect_remote_device(_closed_url(), 0.5) == "remote"


def test_transcribe_local_and_streaming(wav):
    class T:
        def transcribe(self, p, language, hotwords):
            return f"{language}|{hotwords}"

    assert stt.transcribe(STTEngine("l"), wav, language="de", hotwords="hw", local_transcriber=T()) == "de|hw"
    with pytest.raises(STTError, match="isn't loaded"):
        stt.transcribe(STTEngine("l"), wav)
    with pytest.raises(STTError, match="live-only"):
        stt.transcribe(STTEngine("s", "riva_realtime", "http://x"), wav)


def test_transcribe_remote_ok_and_request_shape(srv, wav, monkeypatch):
    s = srv({"/v1/audio/transcriptions": (200, {"text": "  hallo  "})})
    monkeypatch.setenv("FAKE_STT_KEY", "fake-secret")
    eng = STTEngine("r", "openai", s.url + "/v1/", "whisper-x", "FAKE_STT_KEY", timeout=0)
    assert stt.transcribe(eng, wav, language="de", hotwords="Blitz", timeout=3) == "hallo"
    _, path, hdrs, body = s.seen[0]
    assert hdrs["Authorization"] == "Bearer fake-secret"
    assert hdrs["Content-Type"].startswith("multipart/form-data; boundary=")
    for needle in (b'name="model"', b"whisper-x", b'name="language"', b'name="prompt"', b"Blitz", b"RIFFfake", b'filename="a.wav"'):
        assert needle in body


def test_transcribe_remote_custom_path_and_plain_text(srv, wav):
    s = srv({"/transcribe": (200, b"  plain words \n")})
    eng = STTEngine("r", "openai", s.url + "/transcribe")
    assert stt.transcribe(eng, wav) == "plain words"
    assert s.seen[0][1] == "/transcribe"
    s2 = srv({"/audio/transcriptions": (200, {"text": None})})
    assert stt.transcribe(STTEngine("r", "openai", s2.url), wav) == ""


def test_transcribe_remote_errors_do_not_leak_key(srv, wav, monkeypatch):
    monkeypatch.setenv("FAKE_STT_KEY", "fake-secret")
    s = srv({"/audio/transcriptions": (500, b"boom")})
    with pytest.raises(STTError, match="HTTP 500") as ei:
        stt.transcribe(STTEngine("r", "openai", s.url, api_key_env="FAKE_STT_KEY"), wav)
    assert "fake-secret" not in str(ei.value)
    with pytest.raises(STTError, match="Cannot reach") as ei:
        stt.transcribe(STTEngine("r", "openai", _closed_url(), api_key_env="FAKE_STT_KEY", timeout=1), wav)
    assert "fake-secret" not in str(ei.value)


def test_benchmark(srv, wav):
    s = srv({"/audio/transcriptions": (200, {"text": "ok"})})
    r = stt.benchmark(STTEngine("r", "openai", s.url), wav)
    assert r.ok and r.text == "ok" and r.seconds >= 0 and r.engine == "r"
    bad = stt.benchmark(STTEngine("l"), wav)
    assert not bad.ok and "isn't loaded" in bad.error and bad.text == ""

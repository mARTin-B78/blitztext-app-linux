"""Coverage tests for wwdownload: GitHub listing, download validation, install, docker restart."""
import io
import json
import subprocess
from types import SimpleNamespace
from unittest import mock

import pytest

from blitztext import wwdownload as w


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _urlopen(payload):
    data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return mock.patch.object(w.urllib.request, "urlopen", return_value=_Resp(data))


def test_list_languages_ok_fallback_and_empty():
    items = [{"name": "en", "type": "dir"}, {"name": ".github", "type": "dir"},
             {"name": "README.md", "type": "file"}, {"name": "dk", "type": "dir"}]
    with _urlopen(items):
        assert w.list_languages() == ["dk", "en"]
    with _urlopen([]):
        assert w.list_languages() == w.KNOWN_LANGUAGES
    with mock.patch.object(w.urllib.request, "urlopen", side_effect=OSError):
        assert w.list_languages() == w.KNOWN_LANGUAGES


def test_list_models_sorted_case_insensitive_dirs_only():
    items = [{"name": "b", "type": "dir"}, {"name": "A", "type": "dir"}, {"name": "x", "type": "file"}]
    with _urlopen(items):
        assert w.list_models("en") == ["A", "b"]


def test_list_variants_sorting_and_urls():
    items = [
        {"name": "w_v1.onnx", "size": 5, "download_url": "http://x/1"},
        {"name": "w_v1.tflite", "size": 7},
        {"name": "w_v3.tflite", "size": 9, "download_url": "http://x/3"},
        {"name": "README.md"},
        {"name": "w.onnx"},
    ]
    with _urlopen(items):
        v = w.list_variants("en", "my word")
    assert [x["file"] for x in v] == ["w_v3.tflite", "w_v1.tflite", "w_v1.onnx", "w.onnx"]
    assert v[0]["version"] == 3 and v[0]["url"] == "http://x/3"
    assert v[1]["url"].endswith("/en/my%20word/w_v1.tflite")  # fallback raw URL, quoted
    assert w.has_tflite(v) and not w.has_tflite([x for x in v if x["ext"] == ".onnx"])
    assert w.has_tflite([]) is False


def test_list_variants_empty_when_only_readme():
    with _urlopen([{"name": "README.md"}]):
        assert w.list_variants("en", "x") == []


def test_small_helpers():
    assert w.readme_url("en", "a b").endswith("/en/a%20b/README.md")
    assert w.phrase_from_name("hey_jarvis") == "Hey Jarvis"
    assert w.phrase_from_name("  ") == ""
    assert w.slug("Hey Lara!") == "hey_lara"
    assert w.slug("???") == "wakeword"
    assert w._port_of("tcp://h:10400 ") == "10400"
    assert w._port_of(None) == "" and w._port_of("tcp://h") == ""


def test_install_local(tmp_path):
    a = tmp_path / "My Model.TFLITE"
    a.write_bytes(b"A")
    b = tmp_path / "other.onnx"
    b.write_bytes(b"B")
    out = tmp_path / "out"
    out.mkdir()
    assert w.install_local([a, str(b)], out, word="Hey Lara") == ["hey_lara.tflite", "hey_lara.onnx"]
    assert (out / "hey_lara.onnx").read_bytes() == b"B"
    assert w.install_local([a], out) == ["my_model.tflite"]


def test_install_local_errors(tmp_path):
    with pytest.raises(ValueError, match="No file"):
        w.install_local([], tmp_path)
    with pytest.raises(FileNotFoundError):
        w.install_local([tmp_path / "a.onnx"], tmp_path / "missing")
    bad = tmp_path / "x.txt"
    bad.write_text("x")
    with pytest.raises(ValueError, match="Not a recognized"):
        w.install_local([bad], tmp_path)
    assert list(tmp_path.glob("x*")) == [bad]


def test_download_valid_and_invalid(tmp_path):
    d = tmp_path / "m.tflite"
    with _urlopen(b"\x00\x00\x00\x00TFL3rest"):
        assert w._download("http://x", d, ext=".tflite") == 12
    assert d.read_bytes().startswith(b"\x00\x00\x00\x00TFL3")
    bad = tmp_path / "bad.tflite"
    with _urlopen(b"<html>404</html>"), pytest.raises(ValueError, match="not a .tflite"):
        w._download("http://x", bad, ext=".tflite")
    assert not bad.exists()
    o = tmp_path / "m.onnx"
    with _urlopen(b"\x08\x07abc"):
        w._download("http://x", o, ext=".onnx")
    with _urlopen(b"..ONNX stuff"):
        w._download("http://x", o, ext=".onnx")
    ob = tmp_path / "bad.onnx"
    with _urlopen(b"<html>"), pytest.raises(ValueError, match="not an .onnx"):
        w._download("http://x", ob, ext=".onnx")
    assert not ob.exists()


def _vars():
    return [
        {"file": "a_v2.tflite", "ext": ".tflite", "version": 2, "url": "u/t"},
        {"file": "a_v1.tflite", "ext": ".tflite", "version": 1, "url": "u/t1"},
        {"file": "a_v1.onnx", "ext": ".onnx", "version": 1, "url": "u/o"},
    ]


def test_install_all_formats_and_single(tmp_path):
    calls = []
    with mock.patch.object(w, "_download", side_effect=lambda u, d, ext: calls.append((u, d.name))):
        r = w.install("en", "Hey Lara", tmp_path, variants=_vars())
        assert r == {"model_id": "hey_lara", "files": ["hey_lara.tflite", "hey_lara.onnx"], "tflite": True}
        assert calls == [("u/t", "hey_lara.tflite"), ("u/o", "hey_lara.onnx")]
        r = w.install("en", "x", tmp_path, variants=_vars()[2:], all_formats=False)
        assert r["files"] == ["x.onnx"] and r["tflite"] is False


def test_install_fetches_variants_and_errors(tmp_path):
    with mock.patch.object(w, "list_variants", return_value=[]):
        with pytest.raises(ValueError, match="No openWakeWord"):
            w.install("en", "x", tmp_path)
    with pytest.raises(FileNotFoundError):
        w.install("en", "x", tmp_path / "nope", variants=_vars())
    with mock.patch.object(w, "_download", side_effect=ValueError("bad")):
        with pytest.raises(ValueError):
            w.install("en", "x", tmp_path, variants=_vars())


def test_docker_ps_and_inspect_failures():
    with mock.patch.object(w.subprocess, "run", side_effect=subprocess.TimeoutExpired("d", 1)):
        assert w._docker_ps() is None
        assert w._docker_inspect("c") is None
        assert w.autodetect() == ("", [])
    with mock.patch.object(w.subprocess, "run", return_value=SimpleNamespace(stdout="o\n")):
        assert w._docker_ps() == "o\n"


def test_mount_source_and_framework():
    assert w._mount_source("/a\t/x\n/b\t/y", "/y") == "/b"
    assert w._mount_source("\t/y", "/y") == ""
    assert w._mount_source("", "/y") == ""
    assert w._framework_of("x microwakeword") == "micro"
    assert w._framework_of("openwakeword") == "openwakeword"
    assert w._framework_of("nginx") == ""


def test_inspect_servers_skips_failed_inspect():
    def run(argv, **kw):
        if argv[1] == "ps":
            return SimpleNamespace(stdout="oww\trhasspy/wyoming-openwakeword\n")
        raise OSError
    with mock.patch.object(w.subprocess, "run", side_effect=run):
        assert w._inspect_servers() == []
        assert w.autodetect() == ("", [])


def test_autodetect_no_dirs():
    def run(argv, **kw):
        if argv[1] == "ps":
            return SimpleNamespace(stdout="oww\trhasspy/wyoming-openwakeword\n")
        return SimpleNamespace(stdout="/s\t/d\n===\t--uri tcp://0:1\n")  # no custom-model-dir
    with mock.patch.object(w.subprocess, "run", side_effect=run):
        assert w.autodetect() == ("", [])
        r = w.autodetect_for_uri("")
        assert r["compatible"] is False and r["framework"] == ""


def test_restart_containers_paths():
    assert w.restart_containers([]) == (False, "No container configured.")
    ok = SimpleNamespace(returncode=0, stdout="", stderr="")
    with mock.patch.object(w.subprocess, "run", return_value=ok):
        assert w.restart_containers(["a", "b"]) == (True, "restarted a; restarted b")
    with mock.patch.object(w.subprocess, "run", side_effect=FileNotFoundError):
        assert w.restart_containers(["a"]) == (False, "docker not found on PATH.")
    seq = [subprocess.TimeoutExpired("d", 1),
           SimpleNamespace(returncode=1, stdout="", stderr=" boom \n"),
           SimpleNamespace(returncode=1, stdout="", stderr="")]
    with mock.patch.object(w.subprocess, "run", side_effect=seq):
        okk, msg = w.restart_containers(["a", "b", "c"])
    assert okk is False and msg == "a: timed out; b: boom; c: failed"

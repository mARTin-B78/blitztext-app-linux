"""Characterization tests for benchmark.run (stt network calls mocked)."""

from pathlib import Path
from unittest import mock

from blitztext import benchmark
from blitztext.stt import BenchResult, ModelMeta, STTEngine


def _patch(**kw):
    defaults = dict(
        list_models=mock.Mock(return_value=["m1", "m2"]),
        list_models_meta=mock.Mock(return_value=[ModelMeta("org/m2", ["de"]),
                                                 ModelMeta("m1", ["en", "fr"])]),
        probe_server_ram_mb=mock.Mock(side_effect=[100.0, 250.0, None, 5.0, None, None]),
        detect_remote_device=mock.Mock(return_value="CUDA"),
        benchmark=mock.Mock(side_effect=lambda e, *a, **k: (
            BenchResult(e.name, True, "Hallo Welt", 1.5) if e.model != "m2"
            else BenchResult(e.name, False, "", 0.2, "boom"))),
    )
    defaults.update(kw)
    return mock.patch.multiple(benchmark.stt, **defaults), defaults


class FakeTr:
    device = "cuda"


def test_run_expand_models_rows_and_progress():
    engines = [
        STTEngine("Local", "local"),
        STTEngine("Remote", "openai", url="http://srv:8000/v1", api_key_env="K"),
        STTEngine("Live", "riva_realtime", url="http://riva:1/v1"),
    ]
    p, mocks = _patch()
    seen = []
    with p, mock.patch.object(benchmark, "_rss_mb", side_effect=[10.0, 30.0, 0, 0, 0, 0, 5, 1]):
        rows = benchmark.run(engines, Path("x.wav"), "hallo welt", language="de",
                             get_local_transcriber=lambda e: FakeTr(), progress=seen.append,
                             expand_models=True)
    assert [r.engine for r in rows] == ["Local", "Remote [m1]", "Remote [m2]", "Live"]
    assert seen == rows
    mocks["list_models"].assert_called_once_with("http://srv:8000/v1", "K")
    loc, r1, r2, live = rows
    assert (loc.model, loc.device, loc.languages, loc.ram_mb, loc.srv_ram_mb) == \
        ("local", "CUDA", [], 20.0, None)
    assert loc.wer == 1.0 and loc.accuracy == 0.0  # case-sensitive default
    assert (r1.device, r1.languages, r1.srv_ram_mb, r1.best_for) == ("CUDA", ["en", "fr"], 250.0, "Short / medium")
    assert (r2.ok, r2.wer, r2.accuracy, r2.error, r2.languages, r2.srv_ram_mb) == \
        (False, 1.0, 0.0, "boom", ["de"], None)
    assert live.best_for == "Streaming" and live.srv_ram_mb is None and live.ram_mb == 0.0
    assert mocks["detect_remote_device"].call_count == 2  # cached per URL
    assert mocks["list_models_meta"].call_count == 2
    kw = mocks["benchmark"].call_args_list[0].kwargs
    assert kw["language"] == "de" and isinstance(kw["local_transcriber"], FakeTr)


def test_run_no_expand_case_insensitive_default_model_and_empty_meta():
    engines = [STTEngine("R", "openai", url="http://a/v1")]
    p, mocks = _patch(list_models_meta=mock.Mock(return_value=[]),
                      probe_server_ram_mb=mock.Mock(return_value=7.0))
    with p, mock.patch.object(benchmark, "_rss_mb", return_value=1.0):
        rows = benchmark.run(engines, Path("x.wav"), "hallo welt", case_sensitive=False)
    mocks["list_models"].assert_not_called()
    (r,) = rows
    assert (r.model, r.languages, r.wer, r.srv_ram_mb, r.ram_mb) == ("(default)", [], 0.0, 7.0, 0.0)


def test_run_single_model_not_expanded_and_meta_fallback():
    engines = [STTEngine("R", "openai", url="http://a/v1", model="zzz")]
    p, mocks = _patch(list_models=mock.Mock(return_value=["only"]),
                      list_models_meta=mock.Mock(return_value=[ModelMeta("x", ["it"])]),
                      probe_server_ram_mb=mock.Mock(return_value=None))
    with p, mock.patch.object(benchmark, "_rss_mb", return_value=1.0):
        rows = benchmark.run(engines, Path("x.wav"), "a", expand_models=True)
    assert [r.engine for r in rows] == ["R"]
    assert rows[0].languages == ["it"]  # falls back to first model's languages

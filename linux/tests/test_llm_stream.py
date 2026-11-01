"""Streaming the LLM rewrite into the overlay (so you watch the model write).

`llm.chat(..., on_token=cb)` must parse an OpenAI-style SSE stream, hand each
content delta to the callback, and still return the complete text.
"""

import io

import blitztext.llm as llm


def test_read_stream_accumulates_and_calls_back():
    sse = (
        'data: {"choices":[{"delta":{"content":"Hel"}}]}\n'
        "\n"  # keep-alive blank line
        'data: {"choices":[{"delta":{"content":"lo"}}]}\n'
        'data: {"choices":[{"delta":{}}]}\n'        # role-only / empty delta
        ": comment line\n"                           # SSE comment, ignored
        "data: [DONE]\n"
        'data: {"choices":[{"delta":{"content":"X"}}]}\n'  # after DONE -> ignored
    )
    tokens = []
    out = llm._read_stream(io.BytesIO(sse.encode("utf-8")), tokens.append)

    assert out == "Hello"
    assert tokens == ["Hel", "lo"]


def test_read_stream_survives_callback_errors():
    sse = (
        'data: {"choices":[{"delta":{"content":"a"}}]}\n'
        'data: {"choices":[{"delta":{"content":"b"}}]}\n'
        "data: [DONE]\n"
    )

    def boom(_delta):
        raise RuntimeError("UI exploded")

    # A failing UI callback must not break accumulation / delivery.
    out = llm._read_stream(io.BytesIO(sse.encode("utf-8")), boom)
    assert out == "ab"


def test_invalid_env_name_ignored_without_leak(monkeypatch):
    secret = "sk-synthetic-not-a-real-key"
    assert llm.LLMEngine("x", api_key_env=secret).api_key is None


def test_api_key_env_name_resolves_from_environment(monkeypatch):
    monkeypatch.setenv("SYN_LLM_KEY", "v")
    assert llm.LLMEngine("x", api_key_env="SYN_LLM_KEY").api_key == "v"
    assert llm.LLMEngine("x", api_key_env="").api_key is None


# --- session API key (same in-memory store as the TTS "API key (session only)" field) ---
SECRET = "sk-synthetic-not-a-real-key"
URL = "https://llm.example.invalid/v1"


def _fresh_session(monkeypatch):
    from blitztext import tts
    monkeypatch.setattr(tts, "_session_keys", {})
    return tts


def test_session_key_wins_over_env(monkeypatch):
    tts = _fresh_session(monkeypatch)
    monkeypatch.setenv("SYN_LLM_KEY", "from-env")
    tts.set_session_key(URL, SECRET)
    assert llm.LLMEngine("x", url=URL, api_key_env="SYN_LLM_KEY").api_key == SECRET
    assert llm.LLMEngine("x", url=URL + "/", api_key_env="").api_key == SECRET
    tts.set_session_key(URL, "")  # clearing the field falls back to env
    assert llm.LLMEngine("x", url=URL, api_key_env="SYN_LLM_KEY").api_key == "from-env"
    assert llm.LLMEngine("x", url=URL, api_key_env="").api_key is None


def test_pasted_key_in_env_field_ignored_with_session_key(monkeypatch):
    tts = _fresh_session(monkeypatch)
    tts.set_session_key(URL, "ok")
    assert llm.LLMEngine("x", url=URL, api_key_env=SECRET).api_key == "ok"


def test_invalid_session_key_rejected_without_echo(monkeypatch):
    import pytest
    tts = _fresh_session(monkeypatch)
    tts.set_session_key(URL, SECRET + " x")
    with pytest.raises(llm.LLMError) as exc:
        llm.LLMEngine("x", url=URL, api_key_env="").api_key
    assert SECRET not in str(exc.value)


def test_session_key_not_in_config_file(monkeypatch, tmp_path):
    from blitztext.config import Config, save
    tts = _fresh_session(monkeypatch)
    tts.set_session_key(URL, SECRET)
    cfg = Config()
    cfg.llm_engines = [llm.LLMEngine("x", url=URL, api_key_env="")]
    save(cfg, tmp_path / "config.toml")
    assert SECRET not in (tmp_path / "config.toml").read_text()

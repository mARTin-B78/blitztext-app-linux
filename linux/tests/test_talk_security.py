import subprocess
from unittest import mock

from blitztext import talk


def test_talk_command_injection_shell_true(monkeypatch):
    class DummyEngine:
        url = "http://localhost/v1; touch /tmp/pwned"
        model = "tts-1"
        extra_payload = ""

    class DummyCfg:
        active_talk = DummyEngine()
        talk_voice = "alloy"

    notified = []
    def mock_notify(title, msg, level):
        notified.append((title, msg))

    monkeypatch.setattr(talk, "get_selected_text", lambda: "Hello world")

    popen_args = []
    class MockPopen:
        def __init__(self, args, **kwargs):
            popen_args.append((args, kwargs))
            self.stdout = mock.MagicMock()

    monkeypatch.setattr(subprocess, "Popen", MockPopen)

    talk.play(DummyCfg(), mock_notify)

    assert len(popen_args) == 2, "Expected two Popen calls for curl and ffplay"

    curl_args, curl_kwargs = popen_args[0]
    assert curl_kwargs.get("shell") is not True
    assert isinstance(curl_args, list)
    assert "curl" in curl_args
    assert any("; touch /tmp/pwned" in arg for arg in curl_args)

    ffplay_args, ffplay_kwargs = popen_args[1]
    assert ffplay_kwargs.get("shell") is not True
    assert isinstance(ffplay_args, list)
    assert "ffplay" in ffplay_args

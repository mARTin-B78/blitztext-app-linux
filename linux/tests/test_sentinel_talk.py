import pytest
from unittest.mock import patch, MagicMock
from blitztext.talk import play

class DummyEngine:
    def __init__(self, url, model=None, extra_payload=None):
        self.url = url
        self.model = model
        self.extra_payload = extra_payload

class DummyCfg:
    def __init__(self, engine, voice="alloy"):
        self.active_talk = engine
        self.talk_voice = voice

@patch("blitztext.talk.subprocess.Popen")
@patch("blitztext.talk.subprocess.run")
@patch("blitztext.talk.get_selected_text")
def test_play_command_injection(mock_get_selected_text, mock_run, mock_popen):
    mock_get_selected_text.return_value = "Hello"
    notify = MagicMock()

    malicious_url = "http://localhost/v1; rm -rf /"
    engine = DummyEngine(url=malicious_url)
    cfg = DummyCfg(engine=engine)

    play(cfg, notify)

    assert mock_popen.called
    assert mock_run.called

    assert not mock_popen.call_args[1].get("shell", False), "Should not use shell=True"
    assert not mock_run.call_args[1].get("shell", False), "Should not use shell=True"

import json
import pytest
from unittest.mock import patch, MagicMock
from blitztext.talk import play

class MockEngine:
    def __init__(self, url):
        self.url = url
        self.model = "tts-1"
        self.extra_payload = ""

class MockCfg:
    def __init__(self, url):
        self.active_talk = MockEngine(url)
        self.talk_voice = "alloy"

@patch('blitztext.talk.get_selected_text')
@patch('subprocess.Popen')
def test_talk_play_no_shell(mock_popen, mock_get_text):
    mock_get_text.return_value = "Hello"
    cfg = MockCfg("http://example.com/audio/speech")

    notify_mock = MagicMock()
    play(cfg, notify_mock)

    # We want to verify it doesn't use shell=True and calls curl securely
    assert mock_popen.call_count == 2
    args1, kwargs1 = mock_popen.call_args_list[0]
    args2, kwargs2 = mock_popen.call_args_list[1]

    assert kwargs1.get('shell') is not True
    assert kwargs2.get('shell') is not True

    assert "curl" in args1[0]
    assert "ffplay" in args2[0]

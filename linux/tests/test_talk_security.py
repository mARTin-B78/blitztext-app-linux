import subprocess
from unittest.mock import patch, MagicMock

import blitztext.talk as talk

class DummyEngine:
    def __init__(self):
        self.url = "http://example.com/v1"
        self.model = "tts-1"
        self.extra_payload = ""

class DummyConfig:
    def __init__(self):
        self.active_talk = DummyEngine()
        self.talk_voice = "alloy"

@patch('blitztext.talk.get_selected_text')
@patch('subprocess.Popen')
def test_play_no_shell_true(mock_popen, mock_get_text):
    mock_get_text.return_value = "hello world; rm -rf /"
    cfg = DummyConfig()

    mock_p1 = MagicMock()
    mock_p2 = MagicMock()
    mock_popen.side_effect = [mock_p1, mock_p2]

    talk.play(cfg, lambda title, msg, level: None)

    # We want to make sure Popen is not called with shell=True
    for call in mock_popen.call_args_list:
        args, kwargs = call
        assert kwargs.get('shell') != True, "Popen was called with shell=True!"

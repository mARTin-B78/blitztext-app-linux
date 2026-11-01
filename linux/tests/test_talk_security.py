import subprocess
import json
from unittest import mock
import pytest
from blitztext import talk
from blitztext.config import Config, TTSEngine

@mock.patch("subprocess.Popen")
@mock.patch("blitztext.talk.get_selected_text")
def test_talk_does_not_use_shell(mock_get_text, mock_popen):
    mock_get_text.return_value = "Hello world"

    mock_curl = mock.MagicMock()
    mock_ffplay = mock.MagicMock()
    mock_popen.side_effect = [mock_curl, mock_ffplay]

    cfg = Config()
    cfg.talk_engines = [TTSEngine(name="malicious", url="http://malicious.com; touch /tmp/pwned", model="tts-1")]
    cfg.talk_active = "malicious"

    mock_notify = mock.MagicMock()
    talk.play(cfg, mock_notify)

    assert mock_popen.call_count == 2

    # Verify curl call
    curl_args, curl_kwargs = mock_popen.call_args_list[0]
    assert "shell" not in curl_kwargs or not curl_kwargs["shell"]
    assert curl_args[0][0] == "curl"
    assert curl_args[0][3] == "http://malicious.com; touch /tmp/pwned/v1/audio/speech"

    # Verify ffplay call
    ffplay_args, ffplay_kwargs = mock_popen.call_args_list[1]
    assert "shell" not in ffplay_kwargs or not ffplay_kwargs["shell"]
    assert ffplay_args[0][0] == "ffplay"
    assert ffplay_kwargs["stdin"] == mock_curl.stdout

from unittest.mock import MagicMock, patch

from blitztext.talk import play


class MockEngine:
    def __init__(self):
        self.url = "http://example.com/audio/speech"
        self.model = "tts-1"
        self.extra_payload = "{}"

class MockConfig:
    def __init__(self):
        self.active_talk = MockEngine()
        self.talk_voice = "default_voice"

@patch("blitztext.talk.get_selected_text")
@patch("blitztext.talk.subprocess.Popen")
def test_talk_play_no_shell(mock_popen, mock_get_selected_text):
    mock_get_selected_text.return_value = "Hello world"
    mock_notify = MagicMock()

    mock_curl_proc = MagicMock()
    mock_curl_proc.stdout = MagicMock()

    mock_ffplay_proc = MagicMock()

    # Return mock_curl_proc on the first call, mock_ffplay_proc on the second call
    mock_popen.side_effect = [mock_curl_proc, mock_ffplay_proc]

    play(MockConfig(), mock_notify)

    assert mock_popen.call_count == 2

    # First call: curl
    curl_args, curl_kwargs = mock_popen.call_args_list[0]
    assert isinstance(curl_args[0], list)
    assert curl_args[0][0] == "curl"
    assert "shell" not in curl_kwargs or curl_kwargs.get("shell") is False

    # Second call: ffplay
    ffplay_args, ffplay_kwargs = mock_popen.call_args_list[1]
    assert isinstance(ffplay_args[0], list)
    assert ffplay_args[0][0] == "ffplay"
    assert "shell" not in ffplay_kwargs or ffplay_kwargs.get("shell") is False
    assert ffplay_kwargs.get("stdin") == mock_curl_proc.stdout

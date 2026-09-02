import json
from unittest.mock import MagicMock, patch

from blitztext.talk import play
from blitztext.config import Config


@patch("blitztext.talk.subprocess.Popen")
@patch("blitztext.talk.get_selected_text")
def test_talk_play_shell_injection(mock_get_text, mock_popen):
    """Verify that playing audio calls subprocess.Popen safely without a shell."""
    # Given some selected text and a malicious URL
    mock_get_text.return_value = "Hello"

    cfg = Config()
    cfg.talk_voice = "alloy"
    engine = MagicMock()
    # Malicious URL attempting command injection
    engine.url = "http://example.com/v1; rm -rf /"
    engine.model = "tts-1"
    engine.extra_payload = ""
    cfg.talk_engines = [engine]
    cfg.talk_active = engine.name

    mock_notify = MagicMock()

    # Create mock processes to return for Popen
    mock_p1 = MagicMock()
    mock_p2 = MagicMock()
    mock_popen.side_effect = [mock_p1, mock_p2]

    # When
    play(cfg, mock_notify)

    # Then
    assert mock_popen.call_count == 2

    # Check that the first Popen call uses a list for curl and NO shell
    curl_call = mock_popen.call_args_list[0]
    curl_args = curl_call[0][0]
    curl_kwargs = curl_call[1]

    assert isinstance(curl_args, list)
    assert curl_args[0] == "curl"
    # Ensure the URL is passed safely as an argument and not evaluated by a shell
    assert "http://example.com/v1; rm -rf /v1/audio/speech" in curl_args
    assert "shell" not in curl_kwargs or curl_kwargs.get("shell") is False

    # Check that the second Popen call uses a list for ffplay and NO shell
    ffplay_call = mock_popen.call_args_list[1]
    ffplay_args = ffplay_call[0][0]
    ffplay_kwargs = ffplay_call[1]

    assert isinstance(ffplay_args, list)
    assert ffplay_args[0] == "ffplay"
    assert "shell" not in ffplay_kwargs or ffplay_kwargs.get("shell") is False

    # Check that standard out of first process was closed
    mock_p1.stdout.close.assert_called_once()

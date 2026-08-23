from unittest.mock import MagicMock, patch

from blitztext import talk


@patch('blitztext.talk.subprocess.Popen')
@patch('blitztext.talk.get_selected_text')
def test_talk_play_no_shell_injection(mock_get_text, mock_popen):
    mock_get_text.return_value = "hello world"

    cfg = MagicMock()
    engine = MagicMock()
    # A malicious URL that would execute commands if shell=True
    engine.url = "http://localhost:8000/v1; touch /tmp/pwned #"
    engine.model = "tts-1"
    engine.extra_payload = None
    cfg.active_talk = engine
    cfg.talk_voice = "alloy"

    notify_func = MagicMock()

    mock_p_curl = MagicMock()
    mock_p_curl.stdout = MagicMock()
    mock_popen.side_effect = [mock_p_curl, MagicMock()]

    # Run the function
    talk.play(cfg, notify_func)

    # Assert that subprocess.Popen was called twice (curl and ffplay)
    assert mock_popen.call_count == 2

    curl_args = mock_popen.call_args_list[0][0][0]
    ffplay_args = mock_popen.call_args_list[1][0][0]

    # Popen should be called with lists of arguments (shell=False)
    assert isinstance(curl_args, list)
    assert "curl" in curl_args
    # The URL shouldn't have been evaluated by a shell, meaning the
    # literal string should be present in the args
    assert any("http://localhost:8000/v1; touch /tmp/pwned #" in arg for arg in curl_args)
    # Ensure shell=True wasn't passed as a kwarg
    assert not any("shell" in str(kw) and kw.get("shell") == True for kw in [mock_popen.call_args_list[0][1]])

    assert isinstance(ffplay_args, list)
    assert "ffplay" in ffplay_args

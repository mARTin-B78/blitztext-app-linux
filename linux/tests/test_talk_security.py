from unittest.mock import MagicMock, patch

from blitztext import config, talk


@patch("blitztext.talk.subprocess.Popen")
@patch("blitztext.talk.get_selected_text")
def test_talk_play_no_shell_injection(mock_get_text, mock_popen):
    mock_get_text.return_value = "hello"

    cfg = config.Config()
    cfg.talk_engines = [config.TTSEngine("test", "http://fake.url/v1; rm -rf /", "tts-1")]
    cfg.talk_active = "test"

    mock_notify = MagicMock()

    talk.play(cfg, mock_notify)

    assert mock_popen.called, "subprocess.Popen should have been called"

    # Verify that none of the calls to Popen have shell=True
    for call_args in mock_popen.call_args_list:
        _, kwargs = call_args
        assert not kwargs.get("shell", False), "shell=True must not be used in talk.play"
        args = call_args[0][0]
        # In a list form (no shell), the malicious URL must just be an argument, not evaluated by bash.
        # But we also want to ensure "rm -rf /" doesn't somehow get evaluated.
        # If args is a list, the URL is passed safely as a single argument.
        assert isinstance(args, list), "subprocess.Popen must use a list of arguments, not a string"

import subprocess
from unittest.mock import MagicMock

from blitztext import talk


def test_talk_play_shell_injection(monkeypatch):
    class DummyConfig:
        class ActiveTalk:
            url = "http://evil.com/v1"
            model = "tts-1"
            extra_payload = ""
        active_talk = ActiveTalk()
        talk_voice = "echo"

    cfg = DummyConfig()

    # mock get_selected_text
    monkeypatch.setattr(talk, "get_selected_text", lambda: "Hello World")

    notifies = []
    def _notify_func(t, m, lvl):
        notifies.append((t, m, lvl))

    mock_popen = MagicMock()
    # Mocking standard out logic so p1.stdout.close() doesn't fail
    mock_p1 = MagicMock()
    mock_p1.stdout = MagicMock()
    mock_popen.return_value = mock_p1

    monkeypatch.setattr(subprocess, "Popen", mock_popen)

    talk.play(cfg, _notify_func)

    # Just need to check that no Popen call has shell=True
    for call in mock_popen.call_args_list:
        assert call[1].get("shell") is not True, "subprocess.Popen called with shell=True"

    # Also verify that the correct arguments (lists) were passed
    assert mock_popen.call_count == 2
    args1, kwargs1 = mock_popen.call_args_list[0]
    args2, kwargs2 = mock_popen.call_args_list[1]

    assert isinstance(args1[0], list), "First Popen should receive a list of arguments"
    assert args1[0][0] == "curl"
    assert isinstance(args2[0], list), "Second Popen should receive a list of arguments"
    assert args2[0][0] == "ffplay"

import subprocess
from unittest import mock
from blitztext import talk

class DummyConfig:
    class DummyEngine:
        url = "http://localhost:8080/v1"
        model = "tts-1"
        extra_payload = ""
    active_talk = DummyEngine()
    talk_voice = "nova"

def dummy_notify(title, msg, level):
    pass

@mock.patch("subprocess.Popen")
@mock.patch("blitztext.talk.get_selected_text", return_value="Hello World")
def test_talk_no_shell(mock_get_text, mock_popen):
    talk.play(DummyConfig(), dummy_notify)

    assert mock_popen.call_count == 2
    args, kwargs = mock_popen.call_args_list[0]
    assert "shell" not in kwargs or kwargs["shell"] is False
    assert isinstance(args[0], list)
    assert args[0][0] == "curl"
    assert "http://localhost:8080/v1/audio/speech" in args[0]

    args, kwargs = mock_popen.call_args_list[1]
    assert "shell" not in kwargs or kwargs["shell"] is False
    assert isinstance(args[0], list)
    assert args[0][0] == "ffplay"
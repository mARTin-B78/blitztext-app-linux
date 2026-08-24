import subprocess
from unittest.mock import patch
from blitztext.talk import play
from blitztext.config import Config, TTSEngine

def test_play_no_shell_true():
    class MockConfig:
        talk_voice = "test"
        active_talk = TTSEngine(name="test", url="http://test/v1/audio/speech", model="tts-1", api_key_env="")

    cfg = MockConfig()

    with patch("blitztext.talk.get_selected_text", return_value="hello"):
        with patch("subprocess.Popen") as mock_popen:
            play(cfg, lambda *args: None)

            assert mock_popen.call_count == 2, "Expected two Popen calls for curl and ffplay"

            curl_call = mock_popen.call_args_list[0]
            ffplay_call = mock_popen.call_args_list[1]

            curl_args, curl_kwargs = curl_call
            assert isinstance(curl_args[0], list), "First argument to curl Popen must be a list"
            assert curl_args[0][0] == "curl"
            assert curl_kwargs.get("shell") is not True, "play() must not use shell=True for curl"

            ffplay_args, ffplay_kwargs = ffplay_call
            assert isinstance(ffplay_args[0], list), "First argument to ffplay Popen must be a list"
            assert ffplay_args[0][0] == "ffplay"
            assert ffplay_kwargs.get("shell") is not True, "play() must not use shell=True for ffplay"

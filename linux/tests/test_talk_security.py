import sys
import unittest
from unittest.mock import patch, MagicMock, call

from blitztext.talk import play

class DummyEngine:
    def __init__(self, url):
        self.url = url
        self.model = "tts-1"
        self.extra_payload = "{}"

class DummyConfig:
    def __init__(self, url):
        self.active_talk = DummyEngine(url)
        self.talk_voice = "voice"

class TestTalkSecurity(unittest.TestCase):
    @patch("blitztext.talk.subprocess.Popen")
    @patch("blitztext.talk.get_selected_text")
    def test_play_no_shell_injection(self, mock_get_text, mock_popen):
        mock_get_text.return_value = "hello"
        cfg = DummyConfig("http://malicious.url; echo injected")
        notify_func = MagicMock()

        mock_p1 = MagicMock()
        mock_p1.stdout.close = MagicMock()
        mock_popen.return_value = mock_p1

        play(cfg, notify_func)

        mock_popen.assert_called()

        call_args_list = mock_popen.call_args_list
        self.assertEqual(len(call_args_list), 2)

        curl_args = call_args_list[0][0][0]
        ffplay_args = call_args_list[1][0][0]

        self.assertIsInstance(curl_args, list, "Popen must be called with a list to avoid shell injection")
        self.assertEqual(curl_args[0], "curl")
        # In shell=False list based calls, the presence of ; in the URL arg is passed directly to curl,
        # it won't be evaluated by bash.
        self.assertIn(";", curl_args[3])

        self.assertIsInstance(ffplay_args, list, "Popen must be called with a list to avoid shell injection")
        self.assertEqual(ffplay_args[0], "ffplay")

        # Verify shell is False or not in kwargs (defaulting to False)
        for _, kwargs in call_args_list:
            self.assertFalse(kwargs.get("shell", False))

"""TTS authentication, URL normalization, and streamed playback regression checks."""

import io
import ast
import json
import os
from pathlib import Path
import unittest
import urllib.error
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from blitztext import talk, tts, wakeword_bench


class TTSConnectionTests(unittest.TestCase):
    def test_about_prefers_bundled_changelog_before_install_fallback(self):
        tree = ast.parse((Path(tts.__file__).parent / "gtksettings.py").read_text())
        helper = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                      and node.name == "_app_paths")
        scope = {"Path": Path, "__file__": "/synthetic/install/blitztext/gtksettings.py"}
        exec(compile(ast.Module(body=[helper], type_ignores=[]), "gtksettings.py", "exec"), scope)
        self.assertEqual(scope["_app_paths"]()["changelog"], [
            Path("/synthetic/install/blitztext/CHANGELOG.md"),
            Path("/synthetic/install/CHANGELOG.md"), Path("/opt/blitztext/CHANGELOG.md")])

    def test_open_settings_normalizes_running_legacy_config_before_building_fields(self):
        from blitztext.config import Config, TTSEngine, _tts_fallback
        tree = ast.parse((Path(tts.__file__).parent / "gtksettings.py").read_text())
        dialog = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                      and node.name == "SettingsDialog")
        init = next(node for node in dialog.body if isinstance(node, ast.FunctionDef)
                    and node.name == "__init__")
        # Run the real initialization through self.cfg, before GTK construction.
        prefix = []
        for node in init.body:
            prefix.append(node)
            if isinstance(node, ast.Assign) and any(
                    isinstance(target, ast.Attribute) and target.attr == "cfg"
                    for target in node.targets):
                break
        cfg = Config(tts_api_key_env="synthetic-legacy-benchmark-key",
                     talk_engines=[TTSEngine("Legacy", api_key_env="synthetic-legacy-talk-key"),
                                   TTSEngine("Valid", api_key_env="VALID_TTS_KEY")])
        ui = SimpleNamespace()
        with self.assertLogs("blitztext.config", level="WARNING") as logs:
            exec(compile(ast.Module(body=prefix, type_ignores=[]), "gtksettings.py", "exec"),
                 {"self": ui, "cfg": cfg, "_tts_fallback": _tts_fallback})
        self.assertEqual(ui.cfg.tts_api_key_env, "")
        self.assertEqual([engine.api_key_env for engine in cfg.talk_engines], ["", "VALID_TTS_KEY"])
        self.assertNotIn("synthetic-", "".join(logs.output))
        with self.assertRaises(RuntimeError):
            tts.validate_env_name("synthetic-new-invalid-edit")

    def test_invalid_env_name_is_ignored_without_leak(self):
        secret = "synthetic-pasted-key"
        self.assertEqual(tts.auth_headers(secret), {})
        tts.set_session_key("http://localhost:4000", "synthetic-direct-key")
        self.assertEqual(tts.auth_headers(secret, "http://localhost:4000"),
                         {"Authorization": "Bearer synthetic-direct-key"})

    def test_save_clears_invalid_env_names_and_keeps_valid_ones(self):
        tree = ast.parse((Path(tts.__file__).parent / "gtksettings.py").read_text())
        dialog = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SettingsDialog")
        fn = next(n for n in dialog.body if isinstance(n, ast.FunctionDef)
                  and n.name == "_clear_invalid_env_names")
        scope = {"__name__": "blitztext.gtksettings", "__package__": "blitztext"}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "gtksettings.py", "exec"), scope)
        engines = lambda *v: [SimpleNamespace(api_key_env=x) for x in v]
        cfg = SimpleNamespace(tts_api_key_env="synthetic pasted", talk_engines=engines("sk-synthetic", "TTS_KEY"),
                              llm_engines=engines("sk-synthetic", "LLM_KEY", ""))
        scope["_clear_invalid_env_names"](SimpleNamespace(cfg=cfg))
        self.assertEqual(cfg.tts_api_key_env, "")
        self.assertEqual([e.api_key_env for e in cfg.talk_engines], ["", "TTS_KEY"])
        self.assertEqual([e.api_key_env for e in cfg.llm_engines], ["", "LLM_KEY", ""])

    def test_redirects_refuse_other_origins_before_forwarding_credentials(self):
        handler = tts._SameOriginRedirectHandler()
        request = tts.urllib.request.Request("https://example.invalid/v1/models",
                                             headers={"Authorization": "Bearer synthetic-secret"})
        for url in ("https://other.invalid/v1/models", "https://example.invalid:444/v1/models",
                    "http://example.invalid/v1/models"):
            with self.subTest(url=url), self.assertRaises(urllib.error.URLError) as error:
                handler.redirect_request(request, None, 302, "Found", {}, url)
            self.assertNotIn("synthetic-secret", str(error.exception))
        for url in ("https://example.invalid/other", "https://example.invalid:443/other"):
            redirected = handler.redirect_request(request, None, 302, "Found", {}, url)
            self.assertEqual(redirected.get_header("Authorization"), "Bearer synthetic-secret")

    def test_tts_opener_installs_origin_guard(self):
        request = tts.urllib.request.Request("https://example.invalid/v1/models")
        with patch.object(tts.urllib.request, "build_opener") as build:
            tts.urlopen(request, timeout=5)
        self.assertIsInstance(build.call_args.args[0], tts._SameOriginRedirectHandler)
        build.return_value.open.assert_called_once_with(request, timeout=5)

    def setUp(self):
        self.keys = patch.dict(tts._session_keys, {}, clear=True)
        self.keys.start()
        self.addCleanup(self.keys.stop)

    def test_session_key_overrides_env_only_for_same_endpoint_and_can_be_cleared(self):
        tts.set_session_key("http://localhost:4000/v1/voices", "synthetic-direct-key")
        self.assertEqual(tts.auth_headers("MISSING_KEY", "http://localhost:4000"),
                         {"Authorization": "Bearer synthetic-direct-key"})
        self.assertEqual(tts.auth_headers("", "http://localhost:5000"), {})
        tts.set_session_key("http://localhost:4000", "")
        with patch.dict(os.environ, {"TEST_ENV": "synthetic-env-key"}, clear=True):
            self.assertEqual(tts.auth_headers("TEST_ENV", "http://localhost:4000"),
                             {"Authorization": "Bearer synthetic-env-key"})

    def test_talk_engine_uses_session_key_without_env_and_errors_with_neither(self):
        url = "http://192.168.178.8:4000/v1"
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError) as error:
                tts.auth_headers("LITELLM_API_KEY", url)
            self.assertIn("No API key", str(error.exception))
            tts.set_session_key(url, "synthetic-direct-key")
            self.assertEqual(tts.auth_headers("LITELLM_API_KEY", url),
                             {"Authorization": "Bearer synthetic-direct-key"})

    def test_direct_key_authenticates_models_voices_and_probe(self):
        url = "http://localhost:4000/v1"
        tts.set_session_key(url, "synthetic-direct-key")
        response = MagicMock()
        response.__enter__.return_value.read.side_effect = [
            b'{"data":[{"id":"tts-1"}]}', b'{"voices":["default"]}', b"wav"]
        with patch("blitztext.tts.urlopen", return_value=response) as request, \
             patch.object(wakeword_bench, "_wav_to_pcm16k", return_value=b"pcm"):
            self.assertEqual(tts.list_models(url), ["tts-1"])
            self.assertEqual(wakeword_bench.list_voices(url), ["default"])
            self.assertTrue(wakeword_bench.probe(url, model="tts-1", voice="default")[0])
        self.assertEqual(len(request.call_args_list), 3)
        for call in request.call_args_list:
            self.assertEqual(call.args[0].get_header("Authorization"), "Bearer synthetic-direct-key")

    def test_direct_key_is_validated_and_server_errors_are_redacted(self):
        url = "http://localhost:4000/v1"
        tts.set_session_key(url, "synthetic-secret\n")
        with patch("blitztext.tts.urlopen") as request:
            with self.assertRaises(RuntimeError) as error:
                tts.list_models(url)
            request.assert_not_called()
        self.assertNotIn("synthetic-secret", str(error.exception))
        tts.set_session_key(url, "synthetic-secret")
        failure = urllib.error.HTTPError(url, 401, "synthetic-secret", {}, io.BytesIO(b"synthetic-secret"))
        with patch("blitztext.tts.urlopen", side_effect=failure):
            ok, message = wakeword_bench.probe(url, model="tts-1", voice="default")
        self.assertFalse(ok)
        self.assertIn("401", message)
        self.assertNotIn("synthetic-secret", message)

    def test_masked_ui_field_scopes_url_changes(self):
        # Load just the widget helper so this check runs without a GTK display.
        tree = ast.parse((Path(tts.__file__).parent / "gtksettings.py").read_text())
        helper = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                      and node.name == "_tts_session_key_field")

        class Entry:
            def __init__(self, text="", **kwargs):
                self.text, self.callbacks = text, []
            def get_text(self):
                return self.text
            def set_text(self, text):
                self.text = text
                for callback in self.callbacks:
                    callback(self)
            def connect(self, signal, callback):
                self.callbacks.append(callback)
            def set_visibility(self, value):
                self.visible = value
            def set_input_purpose(self, value):
                self.purpose = value
            def set_tooltip_text(self, value):
                pass
            def pack_start(self, *args):
                pass

        scope = {"__name__": "blitztext.gtksettings", "__package__": "blitztext", "_entry": Entry, "_labeled": MagicMock(),
                 "Gtk": SimpleNamespace(InputPurpose=SimpleNamespace(PASSWORD="password"),
                                        Button=lambda **kw: Entry(), Box=lambda **kw: Entry())}
        exec(compile(ast.Module(body=[helper], type_ignores=[]), "gtksettings.py", "exec"), scope)
        url = Entry("http://localhost:4000")
        field = scope["_tts_session_key_field"](None, url)
        self.assertFalse(field.visible)
        field.set_text("synthetic-direct-key")
        self.assertEqual(tts.session_key(url.get_text()), "synthetic-direct-key")
        url.set_text("http://localhost:5000")
        self.assertEqual(field.get_text(), "")
        self.assertEqual(tts.auth_headers("", url.get_text()), {})
        url.set_text("http://localhost:4000")
        self.assertEqual(field.get_text(), "synthetic-direct-key")
        field.set_text("")
        self.assertEqual(tts.auth_headers("", url.get_text()), {})

    def test_direct_key_reaches_actual_talk_playback_without_env(self):
        tts.set_session_key("http://localhost:4000", "synthetic-direct-key")
        response = MagicMock()
        response.__enter__.return_value = io.BytesIO(b"audio")
        player = MagicMock()
        player.stdin = io.BytesIO()
        player.stdin.close = MagicMock()
        player.wait.return_value = player.poll.return_value = 0
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(talk, "get_selected_text", return_value="test"), \
             patch("blitztext.tts.urlopen", return_value=response) as request, \
             patch.object(talk.subprocess, "Popen", return_value=player) as popen:
            talk.play(self.config(key="MISSING_KEY"), MagicMock())
        self.assertEqual(request.call_args.args[0].get_header("Authorization"), "Bearer synthetic-direct-key")
        self.assertNotIn("synthetic-direct-key", str(popen.call_args))

    def test_normalize_base_and_endpoint_urls(self):
        for suffix in ("", "/v1", "/v1/", "/v1/voices", "/v1/audio/voices", "/v1/models", "/v1/audio/speech"):
            with self.subTest(suffix=suffix):
                self.assertEqual(tts.base_url("http://localhost:4000" + suffix), "http://localhost:4000/v1")

    def test_auth_validation_does_not_expose_values(self):
        with patch.dict(os.environ, {"TTS_TEST_KEY": "synthetic-test-key"}, clear=True):
            self.assertEqual(tts.auth_headers(""), {})
            self.assertEqual(tts.auth_headers("TTS_TEST_KEY"), {"Authorization": "Bearer synthetic-test-key"})
            with self.assertRaises(RuntimeError) as error:
                tts.auth_headers("MISSING_KEY")
            self.assertNotIn("synthetic-test-key", str(error.exception))
            self.assertEqual(tts.auth_headers("synthetic-test-key"), {})  # invalid name ignored

    def test_discovery_and_synthesis_reject_missing_key_before_network(self):
        with patch.dict(os.environ, {}, clear=True), patch("blitztext.tts.urlopen") as request:
            with self.assertRaises(RuntimeError):
                wakeword_bench.list_voices("http://localhost/v1", api_key_env="MISSING_KEY")
            with self.assertRaises(RuntimeError):
                wakeword_bench.synthesize("http://localhost/v1", "test", model="tts-1", voice="default", api_key_env="MISSING_KEY")
            request.assert_not_called()

    def test_invalid_header_values_never_reach_network_or_notifications(self):
        for key in ("synthetic-secret\n", "synthetic-secret\r", "synthetic-secret\x00", "synthetic-secret\x7f", "synthetic-secretä", "synthetic-secret "):
            with self.subTest(key=repr(key)), patch.object(tts.os, "environ", {"TTS_TEST_KEY": key}), \
                 patch.object(talk, "get_selected_text", return_value="test"), \
                 patch("blitztext.tts.urlopen") as request:
                with self.assertRaises(RuntimeError) as error:
                    tts.auth_headers("TTS_TEST_KEY")
                self.assertNotIn("synthetic-secret", str(error.exception))
                notify = MagicMock()
                talk.play(self.config(), notify)
                request.assert_not_called()
                self.assertIn("invalid characters", notify.call_args.args[1])
                self.assertNotIn("synthetic-secret", str(notify.call_args))

    def test_benchmark_normalizes_discovery_url_and_authenticates(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b"wav audio"
        with patch.dict(os.environ, {"TTS_TEST_KEY": "synthetic-test-key"}), \
             patch("blitztext.tts.urlopen", return_value=response) as request, \
             patch.object(wakeword_bench, "_wav_to_pcm16k", return_value=b"pcm"):
            self.assertEqual(wakeword_bench.synthesize("http://localhost:4000/v1/voices", "test", model="tts-1", voice="default", api_key_env="TTS_TEST_KEY"), b"pcm")
        req = request.call_args.args[0]
        self.assertEqual(req.full_url, "http://localhost:4000/v1/audio/speech")
        self.assertEqual(req.get_header("Authorization"), "Bearer synthetic-test-key")

    def config(self, key="TTS_TEST_KEY"):
        return SimpleNamespace(
            active_talk=SimpleNamespace(url="http://localhost:4000/v1/voices", model="tts-1", api_key_env=key, extra_payload='{"app":"Blitztext"}'),
            talk_voice="default",
        )

    def test_talk_streams_authenticated_audio_without_shell_or_secret_arguments(self):
        response = MagicMock()
        response.__enter__.return_value = io.BytesIO(b"streamed audio")
        player = MagicMock()
        player.stdin = io.BytesIO()
        player.stdin.close = MagicMock()
        player.wait.return_value = 0
        player.poll.return_value = 0
        with patch.dict(os.environ, {"TTS_TEST_KEY": "synthetic-test-key"}), \
             patch.object(talk, "get_selected_text", return_value="Connection test."), \
             patch("blitztext.tts.urlopen", return_value=response) as request, \
             patch.object(talk.subprocess, "Popen", return_value=player) as popen:
            talk.play(self.config(), MagicMock())
        req = request.call_args.args[0]
        self.assertEqual(req.full_url, "http://localhost:4000/v1/audio/speech")
        self.assertEqual(req.get_header("Authorization"), "Bearer synthetic-test-key")
        self.assertEqual(json.loads(req.data), {"model": "tts-1", "voice": "default", "input": "Connection test.", "app": "Blitztext"})
        self.assertEqual(player.stdin.getvalue(), b"streamed audio")
        self.assertNotIn("synthetic-test-key", str(popen.call_args))
        self.assertNotIn("shell", popen.call_args.kwargs)

    def test_talk_reports_http_failure_without_starting_player(self):
        notify = MagicMock()
        error = urllib.error.HTTPError("http://localhost", 401, "Unauthorized", {}, None)
        with patch.object(talk, "get_selected_text", return_value="test"), \
             patch("blitztext.tts.urlopen", side_effect=error), \
             patch.object(talk.subprocess, "Popen") as popen:
            talk.play(self.config(key=""), notify)
        popen.assert_not_called()
        self.assertIn("401", notify.call_args.args[1])

    def test_talk_forwards_each_audio_chunk_before_reading_the_next(self):
        player = MagicMock()
        player.stdin = io.BytesIO()
        player.stdin.close = MagicMock()
        player.wait.return_value = 0
        player.poll.return_value = 0
        chunks = iter((b"first chunk", b"second chunk", b""))
        forwarded = bytearray()

        def read_chunk(size):
            self.assertGreater(size, 0)
            self.assertEqual(player.stdin.getvalue(), bytes(forwarded))
            chunk = next(chunks)
            forwarded.extend(chunk)
            return chunk

        response = MagicMock()
        response.__enter__.return_value.read.side_effect = read_chunk
        with patch.object(talk, "get_selected_text", return_value="test"), \
             patch("blitztext.tts.urlopen", return_value=response), \
             patch.object(talk.subprocess, "Popen", return_value=player):
            talk.play(self.config(key=""), MagicMock())
        self.assertEqual(player.stdin.getvalue(), b"first chunksecond chunk")

    def test_talk_stops_before_request_when_key_is_missing(self):
        notify = MagicMock()
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(talk, "get_selected_text", return_value="test"), \
             patch("blitztext.tts.urlopen") as request:
            talk.play(self.config(), notify)
        request.assert_not_called()
        self.assertIn("not set", notify.call_args.args[1])

    def test_player_is_reaped_when_stream_fails(self):
        response = MagicMock()
        response.__enter__.return_value.read.side_effect = OSError("stream failed")
        player = MagicMock()
        player.stdin = io.BytesIO()
        player.poll.return_value = None
        notify = MagicMock()
        with patch.object(talk, "get_selected_text", return_value="test"), \
             patch("blitztext.tts.urlopen", return_value=response), \
             patch.object(talk.subprocess, "Popen", return_value=player):
            talk.play(self.config(key=""), notify)
        player.kill.assert_called_once()
        player.wait.assert_called_once()
        self.assertIn("playback failed", notify.call_args.args[1])


if __name__ == "__main__":
    unittest.main()

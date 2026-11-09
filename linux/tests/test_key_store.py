"""Persistent API key store: survives a fresh process, removable, 0600, corrupt-safe. Uses temp dirs only."""

import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from blitztext import stt, tts
from blitztext.llm import LLMEngine

URL = "http://host:8023/v1"


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        p = patch.dict(os.environ, {"XDG_CONFIG_HOME": self.tmp.name})
        p.start(); self.addCleanup(p.stop); self.addCleanup(self.tmp.cleanup)
        tts._session_keys.clear(); self.addCleanup(tts._session_keys.clear)
        self.path = Path(self.tmp.name) / "blitztext" / "keys.json"
        q = patch.object(tts, "_keys_path", lambda: self.path)
        q.start(); self.addCleanup(q.stop)

    def _fresh_process_key(self):
        code = f"from blitztext import tts; print(tts.session_key({URL!r}), end='')"
        return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                              env=dict(os.environ)).stdout


class KeyStoreTests(_Base):
    def test_save_survives_new_process_with_0600(self):
        self.assertTrue(tts.set_session_key(URL, "sk-test-123"))
        self.assertEqual(self._fresh_process_key(), "sk-test-123")
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)

    def test_remove_deletes_stored_key(self):
        tts.set_session_key(URL, "sk-test-123")
        tts.set_session_key(URL, "")
        self.assertEqual(self._fresh_process_key(), "")

    def test_corrupt_store_is_ignored_and_recoverable(self):
        self.path.parent.mkdir(parents=True); self.path.write_text("{not json")
        self.assertEqual(tts.session_key(URL), "")
        self.assertTrue(tts.set_session_key(URL, "sk-new"))
        self.assertEqual(self._fresh_process_key(), "sk-new")

    def test_unwritable_store_keeps_key_in_memory_and_reports_false(self):
        self.path.parent.mkdir(parents=True); self.path.mkdir()  # a directory where the file should be
        self.assertFalse(tts.set_session_key(URL, "sk-mem"))
        self.assertEqual(tts.session_key(URL), "sk-mem")

    def test_stt_and_llm_use_stored_key(self):
        tts.set_session_key(URL, "sk-shared")
        self.assertEqual(LLMEngine("x", URL).api_key, "sk-shared")
        self.assertEqual(stt._stored_key(URL), "sk-shared")


class LiteralKeyInEnvFieldTests(_Base):
    def test_literal_key_in_env_field_moves_to_store(self):
        self.assertEqual(tts.adopt_literal_key(URL, "sk-literal-9"), "")
        self.assertEqual(self._fresh_process_key(), "sk-literal-9")

    def test_valid_env_name_untouched(self):
        self.assertEqual(tts.adopt_literal_key(URL, "GROQ_API_KEY"), "GROQ_API_KEY")
        self.assertFalse(self.path.exists())

    def test_config_load_migrates_and_scrubs_plaintext(self):
        from blitztext import config
        cfg = Path(self.tmp.name) / "c.toml"
        cfg.write_text('[[workflow]]\nname="w"\nkeyword="k"\nmode="dictate"\n'
                       '[[stt_engine]]\nname="s"\ntype="openai"\nurl="http://h:4000/v1"\nmodel="m"\n'
                       'api_key_env="sk-plain-1"\n')
        try:
            loaded = config.load(cfg)
        except ValueError:
            self.skipTest("minimal config rejected")
        self.assertEqual(loaded.stt_engines[0].api_key_env, "")
        self.assertEqual(stt._stored_key("http://h:4000/v1"), "sk-plain-1")

    def test_stt_http_error_never_echoes_key(self):
        import io, urllib.error
        from unittest.mock import patch
        tts.set_session_key("http://h:4000/v1", "sk-secret-7")
        err = urllib.error.HTTPError("u", 401, "x", {}, io.BytesIO(b"bad key sk-secret-7"))
        wav = Path(self.tmp.name) / "a.wav"; wav.write_bytes(b"RIFF")
        eng = stt.STTEngine("s", "openai", "http://h:4000/v1", "m")
        with patch("blitztext.tts.urlopen", side_effect=err):
            with self.assertRaises(stt.STTError) as ctx:
                stt._transcribe_remote(eng, wav, language="", prompt="", timeout=5)
        self.assertNotIn("sk-secret-7", str(ctx.exception))


class ReviewFixTests(_Base):
    def test_save_failure_keeps_env_value(self):
        self.path.parent.mkdir(parents=True); self.path.mkdir()
        self.assertEqual(tts.adopt_literal_key(URL, "sk-keepme"), "sk-keepme")

    def test_latest_literal_overwrites_stored_key(self):
        tts.set_session_key(URL, "sk-old")
        self.assertEqual(tts.adopt_literal_key(URL, "sk-new"), "")
        self.assertEqual(self._fresh_process_key(), "sk-new")

    def test_underscore_keys_are_literals_but_real_names_are_not(self):
        for lit in ("gsk_AbC123xyz", "xai-abc", "pk-abc", "a" * 41, "abc123def456"):
            self.assertNotEqual(tts.classify_env_value(lit), "env", lit)
        for name in ("MY_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY"):
            self.assertEqual(tts.classify_env_value(name), "env", name)
        with patch.dict(os.environ, {"abc123def456": "x"}):
            self.assertEqual(tts.classify_env_value("abc123def456"), "env")

    def test_store_dir_is_0700_and_file_0600(self):
        tts.set_session_key(URL, "sk-x")
        self.assertEqual(stat.S_IMODE(self.path.parent.stat().st_mode), 0o700)

    def test_config_load_rewrites_file_0600_without_plaintext(self):
        from blitztext import config
        cfg = Path(self.tmp.name) / "c.toml"
        cfg.write_text('[[workflow]]\nname="w"\nkeyword="k"\nmode="dictate"\n'
                       '[[stt_engine]]\nname="s"\ntype="openai"\nurl="http://h:4000/v1"\nmodel="m"\n'
                       'api_key_env="sk-plain-2"\n')
        os.chmod(cfg, 0o644)
        config.load(cfg)
        text = cfg.read_text()
        self.assertNotIn("sk-plain-2", text)
        self.assertEqual(stat.S_IMODE(cfg.stat().st_mode), 0o600)
        self.assertEqual(stt._stored_key("http://h:4000/v1"), "sk-plain-2")

    def test_config_not_rewritten_when_key_save_fails(self):
        from blitztext import config
        self.path.parent.mkdir(parents=True); self.path.mkdir()
        cfg = Path(self.tmp.name) / "c.toml"
        cfg.write_text('[[workflow]]\nname="w"\nkeyword="k"\nmode="dictate"\n'
                       '[[stt_engine]]\nname="s"\ntype="openai"\nurl="http://h:4000/v1"\nmodel="m"\n'
                       'api_key_env="sk-plain-3"\n')
        config.load(cfg)
        self.assertIn("sk-plain-3", cfg.read_text())

    def test_llm_http_error_redacts_key(self):
        import io, urllib.error
        tts.set_session_key(URL, "sk-secret-8")
        err = urllib.error.HTTPError("u", 401, "x", {}, io.BytesIO(b"bad sk-secret-8"))
        from blitztext import llm
        with patch("blitztext.tts.urlopen", side_effect=err):
            with self.assertRaises(llm.LLMError) as ctx:
                llm.chat(LLMEngine("x", URL), "s", "u")
        self.assertNotIn("sk-secret-8", str(ctx.exception))

    def test_cross_origin_redirect_refused_for_stt_and_llm(self):
        import http.server, threading, urllib.error
        hits = []
        class Target(http.server.BaseHTTPRequestHandler):
            def do_POST(self): hits.append(self.headers.get("Authorization")); self.send_response(200); self.end_headers(); self.wfile.write(b"{}")
            do_GET = do_POST
            def log_message(self, *a): pass
        target = http.server.HTTPServer(("127.0.0.1", 0), Target)
        class Redir(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                self.send_response(307); self.send_header("Location", f"http://127.0.0.1:{target.server_port}/x"); self.end_headers()
            do_GET = do_POST
            def log_message(self, *a): pass
        redir = http.server.HTTPServer(("127.0.0.1", 0), Redir)
        for srv in (target, redir):
            threading.Thread(target=srv.serve_forever, daemon=True).start(); self.addCleanup(srv.shutdown)
        url = f"http://127.0.0.1:{redir.server_port}/v1"
        tts.set_session_key(url, "sk-redir")
        from blitztext import llm
        wav = Path(self.tmp.name) / "a.wav"; wav.write_bytes(b"RIFF")
        with self.assertRaises(stt.STTError):
            stt._transcribe_remote(stt.STTEngine("s", "openai", url, "m"), wav, language="", prompt="", timeout=5)
        with self.assertRaises(llm.LLMError):
            llm.chat(LLMEngine("x", url), "s", "u")
        self.assertEqual(hits, [])


class PersistFlagTests(_Base):
    def test_memory_only_edit_not_written_until_persisted(self):
        self.assertTrue(tts.set_session_key(URL, "sk-partial", persist=False))
        self.assertFalse(self.path.exists())
        self.assertEqual(tts.session_key(URL), "sk-partial")
        tts.set_session_key(URL, "sk-partial")
        self.assertTrue(self.path.exists())

    def test_empty_url_does_not_report_success(self):
        self.assertFalse(tts.set_session_key("  ", "sk-x"))
        self.assertFalse(self.path.exists())

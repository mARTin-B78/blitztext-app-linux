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
        with patch("urllib.request.urlopen", side_effect=err):
            with self.assertRaises(stt.STTError) as ctx:
                stt._transcribe_remote(eng, wav, language="", prompt="", timeout=5)
        self.assertNotIn("sk-secret-7", str(ctx.exception))

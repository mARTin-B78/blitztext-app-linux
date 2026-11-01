import pytest
from unittest.mock import patch
import tempfile
import os
from pathlib import Path
from blitztext.config import load, save, Config, Workflow, STTEngine, LLMEngine

def test_load_default_config():
    with tempfile.TemporaryDirectory() as tempdir:
        config_path = Path(tempdir) / "config.toml"
        # Since file doesn't exist, it should create default
        cfg = load(config_path)
        
        assert config_path.exists()
        assert cfg.recorder == "auto"
        assert cfg.output == "type"
        assert cfg.language == "de"
        assert len(cfg.workflows) > 0
        assert cfg.workflows[0].name == "Transcribe"
        assert cfg.workflows[0].mode == "transcribe"
        assert cfg.routing_enabled == True
        assert cfg.stt_active == "Local faster-whisper"

def test_save_and_load_config():
    with tempfile.TemporaryDirectory() as tempdir:
        config_path = Path(tempdir) / "config.toml"
        
        # Create a config
        cfg = Config()
        cfg.recorder = "pw-record"
        cfg.output = "paste"
        cfg.language = "en"
        cfg.workflows = [
            Workflow(name="Test Workflow", hotkey="<ctrl>+t", mode="rewrite", prompt="Testing prompt")
        ]
        cfg.stt_engines = [STTEngine("TestSTT", "openai", "http://localhost", "model")]
        cfg.stt_active = "TestSTT"
        
        save(cfg, config_path)
        assert config_path.exists()
        
        # Load it back
        loaded_cfg = load(config_path)
        assert loaded_cfg.recorder == "pw-record"
        assert loaded_cfg.output == "paste"
        assert loaded_cfg.language == "en"
        assert len(loaded_cfg.workflows) == 1
        assert loaded_cfg.workflows[0].name == "Test Workflow"
        assert loaded_cfg.workflows[0].prompt == "Testing prompt"
        assert loaded_cfg.stt_engines[0].name == "TestSTT"
        assert loaded_cfg.stt_active == "TestSTT"

def test_properties():
    cfg = Config()
    cfg.stt_engines = [
        STTEngine("Engine1", "local"),
        STTEngine("Engine2", "openai")
    ]
    cfg.stt_active = "Engine2"
    assert cfg.active_stt.name == "Engine2"
    
    cfg.stt_active = "NonExistent"
    # Fallback to first engine if active is not found
    assert cfg.active_stt.name == "Engine1"
    
    cfg.workflows = [
        Workflow(name="WF1", hotkey="", mode="transcribe"),
        Workflow(name="WF2", hotkey="", mode="transcribe")
    ]
    assert cfg.preset_by_name("WF2").name == "WF2"
    assert cfg.preset_by_name("NonExistent") is None


def test_default_preset_prefers_transcribe_when_unset():
    """With no routing default, fall back to a transcribe preset, not whatever
    happens to be first (which could be an LLM rewrite)."""
    cfg = Config()
    cfg.routing_default = ""
    cfg.workflows = [
        Workflow(name="Improve text", hotkey="", mode="rewrite"),
        Workflow(name="Transcribe", hotkey="", mode="transcribe"),
    ]
    dp = cfg.default_preset
    assert dp is not None and dp.mode == "transcribe" and dp.name == "Transcribe"


def test_default_preset_honours_explicit_name():
    cfg = Config()
    cfg.workflows = [
        Workflow(name="Improve text", hotkey="", mode="rewrite"),
        Workflow(name="Transcribe", hotkey="", mode="transcribe"),
    ]
    cfg.routing_default = "Improve text"
    assert cfg.default_preset.name == "Improve text"


def test_legacy_tts_fallbacks_are_removed_without_persisting_keys(tmp_path, caplog):
    from blitztext import tts
    path = tmp_path / "config.toml"
    path.write_text('[[workflow]]\nname = "Test"\nmode = "transcribe"\nhotkey = ""\n'
                    '[tts]\napi_key_env = "synthetic-legacy-benchmark-key"\n'
                    '[[talk_engine]]\nname = "Old"\napi_key_env = "synthetic-legacy-talk-key"\n'
                    '[[talk_engine]]\nname = "Valid"\napi_key_env = "VALID_TTS_KEY"\n')
    url = "http://example.invalid:8023/v1"
    with patch.dict(tts._session_keys, {}, clear=True):
        tts.set_session_key(url, "synthetic-session-key")
        cfg = load(path)
        assert cfg.tts_api_key_env == ""
        assert [engine.api_key_env for engine in cfg.talk_engines] == ["", "VALID_TTS_KEY"]
        assert "masked API key field" in caplog.text
        assert "synthetic-" not in caplog.text
        save(cfg, path)
        assert "synthetic-" not in path.read_text()
        assert load(path).talk_engines[1].api_key_env == "VALID_TTS_KEY"
        assert tts.session_key(url) == "synthetic-session-key"
        # Saving an already-running legacy Config must also avoid reserializing keys.
        cfg.tts_api_key_env = "synthetic-old-key"
        cfg.talk_engines[0].api_key_env = "synthetic-old-key"
        save(cfg, path)
        assert "synthetic-" not in path.read_text()


def test_about_and_deb_use_current_version():
    from blitztext import __version__
    root = Path(__file__).parents[1]
    import tomllib
    assert __version__ == tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    assert 'pyproject.toml' in (root / "packaging/build-deb.sh").read_text()
    assert 'Version {__version__}' in (root / "blitztext/gtksettings.py").read_text()


def test_update_settings_roundtrip(tmp_path):
    path = tmp_path / "config.toml"
    cfg = load(path)
    assert cfg.update_check is True and cfg.update_last_check == 0.0 and cfg.update_skipped_version == ""
    cfg.update_check = False
    cfg.update_last_check = 1234.5
    cfg.update_skipped_version = "2.03.80"
    save(cfg, path)
    again = load(path)
    assert (again.update_check, again.update_last_check, again.update_skipped_version) == (False, 1234.5, "2.03.80")

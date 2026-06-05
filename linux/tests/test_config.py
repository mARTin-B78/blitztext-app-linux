import pytest
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

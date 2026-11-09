import pytest

from blitztext import tts


@pytest.fixture(autouse=True)
def _isolated_key_store(tmp_path, monkeypatch):
    """Never touch the real ~/.config/blitztext/keys.json from tests."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    tts._session_keys.clear()
    yield
    tts._session_keys.clear()

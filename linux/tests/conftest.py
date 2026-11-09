import pytest

from blitztext import tts


@pytest.fixture(autouse=True)
def _isolated_key_store(tmp_path, monkeypatch):
    """No test may touch the real key store, even with os.environ cleared."""
    path = tmp_path / "xdg" / "blitztext" / "keys.json"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr(tts, "_keys_path", lambda: path)
    tts._session_keys.clear()
    yield
    tts._session_keys.clear()

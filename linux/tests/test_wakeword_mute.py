"""Mute flag must live in a per-user dir, never a shared /tmp name."""
import importlib
import os
import stat

from blitztext import wakeword


def test_mute_file_not_in_shared_tmp():
    assert not wakeword.MUTE_FILE.startswith("/tmp/")


def test_mute_file_uses_xdg_runtime_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    try:
        assert importlib.reload(wakeword).MUTE_FILE == str(tmp_path / "blitztext-wake_muted")
    finally:
        monkeypatch.undo()
        importlib.reload(wakeword)


def test_set_muted_creates_private_dir_and_toggles(monkeypatch, tmp_path):
    flag = tmp_path / "cache" / "blitztext" / "blitztext-wake_muted"
    monkeypatch.setattr(wakeword, "MUTE_FILE", str(flag))
    wakeword.set_muted(True)
    assert wakeword.is_muted()
    assert stat.S_IMODE(os.stat(flag.parent).st_mode) == 0o700
    wakeword.set_muted(False)
    assert not wakeword.is_muted()

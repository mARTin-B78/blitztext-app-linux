"""Coverage tests for audio: pactl mic listing and LevelMeter (subprocess mocked, no hardware)."""
import io
import struct
import subprocess
from types import SimpleNamespace
from unittest import mock

import pytest

from blitztext import audio


def _pactl(out):
    return mock.patch.object(audio.subprocess, "run", return_value=SimpleNamespace(stdout=out))


def test_list_mics_no_pactl():
    with mock.patch.object(audio.shutil, "which", return_value=None):
        assert audio.list_mics() == [("", "Default device")]


def test_list_mics_filters_monitors_and_bad_lines():
    out = ("1\talsa_input.usb-Foo_Mic-00.mono\tmod\n"
           "2\talsa_output.x.monitor\tmod\n"
           "garbage\n"
           "3\tbluez_input.AA\tmod\n")
    with mock.patch.object(audio.shutil, "which", return_value="/usr/bin/pactl"), _pactl(out):
        mics = audio.list_mics()
    assert mics == [("", "Default device"),
                    ("alsa_input.usb-Foo_Mic-00.mono", "usb Foo_Mic 00.mono"),
                    ("bluez_input.AA", "bluez_input.AA")]


@pytest.mark.parametrize("exc", [OSError, subprocess.CalledProcessError(1, "pactl")])
def test_list_mics_pactl_failure(exc):
    with mock.patch.object(audio.shutil, "which", return_value="/x"), \
            mock.patch.object(audio.subprocess, "run", side_effect=exc):
        assert audio.list_mics() == [("", "Default device")]


def test_argv_device_flags():
    m = audio.LevelMeter(device="src1")
    assert m._argv("pw-record")[-2:] == ["--target", "src1"]
    assert m._argv("parecord")[-2:] == ["-d", "src1"]
    assert m._argv("arecord") == audio._METER_ARGV["arecord"]  # ALSA: stays default
    assert audio.LevelMeter(device=None)._argv("pw-record") == audio._METER_ARGV["pw-record"]


def test_start_no_recorder_or_unknown_or_popen_fails():
    m = audio.LevelMeter()
    with mock.patch.object(audio, "detect_recorder", side_effect=RuntimeError):
        assert m.start() is False
    with mock.patch.object(audio, "detect_recorder", return_value="sox"):
        assert m.start() is False
    with mock.patch.object(audio, "detect_recorder", return_value="arecord"), \
            mock.patch.object(audio.subprocess, "Popen", side_effect=OSError):
        assert m.start() is False and m._proc is None


class _Proc:
    def __init__(self, data):
        self.stdout = io.BytesIO(data)
        self.terminated = self.killed = False
        self._alive = True

    def poll(self):
        return None if self._alive else 0

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        raise subprocess.TimeoutExpired("x", timeout)

    def kill(self):
        self.killed = True


def _pcm(v, n=1600):
    return struct.pack(f"<{n}h", *([v] * n))


def test_loop_levels_and_chunks():
    loud, quiet, odd = _pcm(32767), _pcm(0), _pcm(100)[:-1]
    levels, chunks = [], []
    m = audio.LevelMeter(on_level=levels.append, on_chunk=chunks.append)
    m._proc = _Proc(loud + quiet + odd)
    m._loop()
    assert levels[0] == 1.0          # clipped to 1
    assert levels[1] == 0.0          # silence
    assert 0 < levels[2] < 0.1       # 100/32768*12
    assert len(chunks) == 3 and chunks[0] == loud[:audio._CHUNK_BYTES]


def test_loop_empty_chunk_stops_and_no_proc():
    levels = []
    m = audio.LevelMeter(on_level=levels.append)
    m._loop()  # no proc: returns quietly
    m._proc = _Proc(b"")
    m._loop()
    assert levels == []


def test_loop_swallows_callback_errors():
    def boom(_):
        raise RuntimeError
    m = audio.LevelMeter(on_level=boom)
    m._proc = _Proc(_pcm(1000))
    m._loop()  # must not raise


def test_loop_single_byte_chunk_gives_zero_level():
    levels = []
    m = audio.LevelMeter(on_level=levels.append)
    m._proc = _Proc(b"\x01")
    m._loop()
    assert levels == [0.0]


def test_start_stop_lifecycle_and_kill_on_hang():
    proc = _Proc(b"")
    m = audio.LevelMeter(device="d")
    with mock.patch.object(audio, "detect_recorder", return_value="pw-record"), \
            mock.patch.object(audio.subprocess, "Popen", return_value=proc) as popen:
        assert m.start() is True
        assert popen.call_args[0][0][-2:] == ["--target", "d"]
        m.stop()
    assert proc.terminated and proc.killed  # wait() timed out -> kill
    assert m._proc is None and m._thread is None
    m.stop()  # idempotent

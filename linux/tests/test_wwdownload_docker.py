"""Characterization tests for the docker auto-detection in wwdownload (docker mocked)."""

from types import SimpleNamespace
from unittest import mock

from blitztext import wwdownload

FMT = ("{{range .Mounts}}{{.Source}}\t{{.Destination}}\n{{end}}"
       "===\t{{join .Args \" \"}}")

PS = "\n".join([
    "oww-main\trhasspy/wyoming-openwakeword",
    "oww_preload\trhasspy/wyoming-openwakeword",
    "micro\trhasspy/wyoming-microwakeword",
    "web\tnginx",
    "broken-line",
    "oww-nodir\trhasspy/wyoming-openwakeword",
])
INSPECT = {
    "oww-main": "/srv/a\t/custom\n/x\t/data\n===\t--uri tcp://0.0.0.0:10400 --custom-model-dir /custom",
    "oww_preload": "/srv/a\t/custom\n===\t--uri=tcp://0.0.0.0:10401 --custom-model-dir=/custom",
    "micro": "/srv/m\t/models\n===\t--uri tcp://0.0.0.0:10500 --custom-model-dir '/models'",
    "oww-nodir": "===\t--uri tcp://0.0.0.0:10402",
}


def _run(argv, **kw):
    if argv[:2] == ["docker", "ps"]:
        return SimpleNamespace(stdout=PS)
    assert argv[:3] == ["docker", "inspect", "--format"] and argv[3] == FMT
    if argv[4] == "oww-nodir" and kw.get("fail"):
        raise OSError
    return SimpleNamespace(stdout=INSPECT[argv[4]])


def test_inspect_servers():
    with mock.patch.object(wwdownload.subprocess, "run", side_effect=_run):
        servers = wwdownload._inspect_servers()
    assert servers == [
        {"name": "oww-main", "port": "10400", "framework": "openwakeword", "model_dir": "/srv/a"},
        {"name": "oww_preload", "port": "10401", "framework": "openwakeword", "model_dir": "/srv/a"},
        {"name": "micro", "port": "10500", "framework": "micro", "model_dir": "/srv/m"},
        {"name": "oww-nodir", "port": "10402", "framework": "openwakeword", "model_dir": ""},
    ]


def test_autodetect_and_for_uri():
    with mock.patch.object(wwdownload.subprocess, "run", side_effect=_run):
        assert wwdownload.autodetect() == ("/srv/a", ["oww-main", "oww_preload"])
        assert wwdownload.autodetect_for_uri("tcp://h:10401") == {
            "framework": "openwakeword", "model_dir": "/srv/a",
            "containers": ["oww-main", "oww_preload"], "compatible": True}
        assert wwdownload.autodetect_for_uri("tcp://h:10500") == {
            "framework": "micro", "model_dir": "/srv/a",
            "containers": ["oww-main", "oww_preload"], "compatible": False}


def test_docker_missing():
    with mock.patch.object(wwdownload.subprocess, "run", side_effect=FileNotFoundError):
        assert wwdownload._inspect_servers() == []
        assert wwdownload.autodetect() == ("", [])


def test_inspect_failure_skips_container():
    def run(argv, **kw):
        if argv[:2] == ["docker", "inspect"] and argv[4] == "oww-main":
            raise OSError
        return _run(argv, **kw)

    with mock.patch.object(wwdownload.subprocess, "run", side_effect=run):
        assert [s["name"] for s in wwdownload._inspect_servers()] == ["oww_preload", "micro", "oww-nodir"]
        assert wwdownload.autodetect() == ("/srv/a", ["oww_preload"])

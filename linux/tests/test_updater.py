import hashlib
import io
import json
import os
import urllib.error
from unittest.mock import patch

import pytest

from blitztext import updater

DEB = "https://github.com/mARTin-B78/blitztext-app-linux/releases/download/v2.03.80/blitztext_2.03.80_arm64.deb"
SHA = DEB + ".sha256"


def _release(ver="2.03.80"):
    names = [f"blitztext_{ver}_amd64.deb", f"blitztext_{ver}_amd64.deb.sha256",
             f"blitztext_{ver}_arm64.deb", f"blitztext_{ver}_arm64.deb.sha256"]
    base = f"https://github.com/mARTin-B78/blitztext-app-linux/releases/download/v{ver}/"
    return {"tag_name": f"v{ver}", "body": "Notes <b>x</b>",
            "assets": [{"name": n, "browser_download_url": base + n} for n in names]}


@pytest.mark.parametrize("a,b,expected", [
    ("2.03.72", "2.03.71", True),
    ("2.03.71", "2.03.72", False),
    ("2.03.72", "2.03.72", False),
    ("2.10.0", "2.9.9", True),          # numeric, not lexicographic
    ("2.03.72.1", "2.03.72", True),
    ("3", "2.99.99", True),
    ("garbage", "2.03.72", False),
    ("2.03.72", "garbage", False),
])
def test_is_newer(a, b, expected):
    assert updater.is_newer(a, b) is expected


def test_pick_assets_by_arch():
    got = updater.pick_assets(_release(), "arm64")
    assert got[0] == "2.03.80"
    assert got[2].endswith("blitztext_2.03.80_arm64.deb")
    assert got[3].endswith("blitztext_2.03.80_arm64.deb.sha256")
    assert updater.pick_assets(_release(), "riscv64") is None


def test_pick_assets_rejects_untrusted_urls_and_bad_tags():
    rel = _release()
    for a in rel["assets"]:
        a["browser_download_url"] = a["browser_download_url"].replace("https://github.com", "https://evil.example")
    assert updater.pick_assets(rel, "arm64") is None
    bad = _release()
    bad["tag_name"] = "v2.03.80; rm -rf /"
    assert updater.pick_assets(bad, "arm64") is None


@pytest.mark.parametrize("url,ok", [
    (DEB, True),
    ("https://objects.githubusercontent.com/x/blitztext_1_arm64.deb", True),
    ("https://release-assets.githubusercontent.com/x", True),
    ("http://github.com/x", False),
    ("https://github.com.evil.com/x", False),
    ("https://evilgithubusercontent.com/x", False),
    ("https://example.com/x", False),
    ("file:///etc/passwd", False),
    ("https://user@github.com/x", False),
])
def test_download_url_ok(url, ok):
    assert updater.download_url_ok(url) is ok


def test_check_latest_network_error_returns_none():
    with patch.object(updater, "_open", side_effect=urllib.error.URLError("down")):
        assert updater.check_latest(arch="arm64") is None
    with patch.object(updater, "_open", side_effect=TimeoutError()):
        assert updater.check_latest(arch="arm64") is None


def test_check_latest_no_release_is_empty_not_error():
    err = urllib.error.HTTPError(updater.API_URL, 404, "Not Found", {}, None)
    with patch.object(updater, "_open", side_effect=err):
        assert updater.check_latest(arch="arm64") == ()
    err500 = urllib.error.HTTPError(updater.API_URL, 500, "x", {}, None)
    with patch.object(updater, "_open", side_effect=err500):
        assert updater.check_latest(arch="arm64") is None
    with patch.object(updater, "_open", return_value=io.BytesIO(json.dumps(_release()).encode())):
        assert updater.check_latest(arch="riscv64") == ()


def test_check_latest_bad_json_or_oversize_returns_none():
    with patch.object(updater, "_open", return_value=io.BytesIO(b"{not json")):
        assert updater.check_latest(arch="arm64") is None
    big = b" " * (updater.MAX_API_BYTES + 10)
    with patch.object(updater, "_open", return_value=io.BytesIO(big)):
        assert updater.check_latest(arch="arm64") is None


def test_check_latest_success():
    body = json.dumps(_release()).encode()
    with patch.object(updater, "_open", return_value=io.BytesIO(body)):
        ver, notes, deb, sha = updater.check_latest(arch="arm64")
    assert ver == "2.03.80" and "Notes" in notes and deb == DEB and sha == SHA


def _fake_open(payload: bytes, sha_text: str):
    def opener(url, timeout=None):
        return io.BytesIO(sha_text.encode() if url.endswith(".sha256") else payload)
    return opener


def test_sha_mismatch_aborts_before_install_and_removes_file():
    payload = b"deb-bytes"
    created = []
    real_mkdtemp = updater.tempfile.mkdtemp

    def track(**kw):
        d = real_mkdtemp(**kw)
        created.append(d)
        return d

    with patch.object(updater, "_open", _fake_open(payload, "0" * 64 + "  x.deb\n")), \
         patch.object(updater.tempfile, "mkdtemp", side_effect=track), \
         patch.object(updater.subprocess, "run") as run:
        with pytest.raises(updater.UpdateError, match="[Cc]hecksum"):
            updater.update(DEB, SHA)
    run.assert_not_called()
    assert created and not os.path.exists(created[0])


def test_success_calls_pkexec_with_exact_args():
    payload = b"deb-bytes"
    digest = hashlib.sha256(payload).hexdigest()
    seen = {}

    def fake_run(args, **kw):
        seen["args"] = args
        seen["kw"] = kw
        assert open(args[-1], "rb").read() == payload  # verified file still there
        return updater.subprocess.CompletedProcess(args, 0)

    with patch.object(updater, "_open", _fake_open(payload, digest + "  blitztext_2.03.80_arm64.deb\n")), \
         patch.object(updater.subprocess, "run", side_effect=fake_run):
        updater.update(DEB, SHA)
    args = seen["args"]
    assert args[:4] == ["pkexec", "apt", "install", "-y"]
    assert os.path.isabs(args[4]) and args[4].endswith("/blitztext_2.03.80_arm64.deb")
    assert seen["kw"].get("shell") in (None, False)
    assert not os.path.exists(args[4])  # temp dir cleaned after install


@pytest.mark.parametrize("rc", [126, 127])
def test_pkexec_cancelled(rc):
    payload = b"x"
    digest = hashlib.sha256(payload).hexdigest()
    with patch.object(updater, "_open", _fake_open(payload, digest)), \
         patch.object(updater.subprocess, "run",
                      return_value=updater.subprocess.CompletedProcess([], rc)):
        with pytest.raises(updater.UpdateError, match="not authori[sz]ed|cancel"):
            updater.update(DEB, SHA)


def test_install_rejects_paths_outside_update_tempdir(tmp_path):
    f = tmp_path / "blitztext_2.03.80_arm64.deb"
    f.write_bytes(b"x")
    with patch.object(updater.subprocess, "run") as run:
        with pytest.raises(updater.UpdateError):
            updater.install(str(f))
        with pytest.raises(updater.UpdateError):
            updater.install("blitztext_2.03.80_arm64.deb")
    run.assert_not_called()


def test_update_rejects_untrusted_url():
    with patch.object(updater, "_open") as op, patch.object(updater.subprocess, "run") as run:
        with pytest.raises(updater.UpdateError):
            updater.update("https://evil.example/blitztext_2.03.80_arm64.deb", SHA)
        with pytest.raises(updater.UpdateError):
            updater.update(DEB.replace("blitztext_2.03.80_arm64.deb", "evil;rm.deb"), SHA)
    op.assert_not_called()
    run.assert_not_called()


def test_throttle():
    day = 24 * 3600
    assert updater.should_check(True, 0.0, 1_000_000.0)
    assert not updater.should_check(True, 1_000_000.0, 1_000_000.0 + day - 1)
    assert updater.should_check(True, 1_000_000.0, 1_000_000.0 + day)
    assert not updater.should_check(False, 0.0, 1_000_000.0)
    assert updater.should_check(True, 2_000_000.0, 1_000_000.0)  # clock went backwards


def test_should_offer_respects_skip():
    assert updater.should_offer("2.03.80", "2.03.72", "")
    assert not updater.should_offer("2.03.80", "2.03.72", "2.03.80")
    assert updater.should_offer("2.03.81", "2.03.72", "2.03.80")
    assert not updater.should_offer("2.03.72", "2.03.72", "")


def test_parse_sha256():
    d = "a" * 64
    assert updater.parse_sha256(d) == d
    assert updater.parse_sha256(f"{d.upper()}  blitztext_1_arm64.deb\n") == d
    with pytest.raises(updater.UpdateError):
        updater.parse_sha256("nothex")


# ---- changelog ------------------------------------------------------------------
CL = """# Changelog
## [Unreleased]
### Added
- unreleased thing
## [2.03.73] - 2026-11-01
### Changed
- **Bump** `x`
## [2.03.72] - 2026-11-01
### Fixed
- fix <b>y</b>
## [2.03.71] - 2026-10-03
### Added
- old
"""


def test_changelog_between_range():
    out = updater.changelog_between(CL, "2.03.71", "2.03.73")
    assert out.index("2.03.73") < out.index("2.03.72")
    assert "Bump x" in out and "fix <b>y</b>" in out      # markup chars stay literal text
    assert "old" not in out and "unreleased" not in out


def test_changelog_between_none_newer_and_malformed():
    assert updater.changelog_between(CL, "2.03.73", "2.03.73") == ""
    assert updater.changelog_between("garbage ## [x] \n\x00", "2.03.1", "2.03.9") == ""
    assert updater.changelog_between(CL, "bad", "2.03.73") == ""


def test_changelog_capped():
    big = "## [2.0.1]\n" + "- a\n" * 5000
    assert len(updater.changelog_between(big, "2.0.0", "2.0.1")) <= updater.MAX_CHANGELOG_CHARS + 2


def test_fetch_changelog_ok_and_errors():
    class R(io.BytesIO):
        __enter__ = lambda s: s
        __exit__ = lambda s, *a: None
    with patch.object(updater, "_open", return_value=R(b"hello")) as o:
        assert updater.fetch_changelog("v2.03.73") == "hello"
        assert o.call_args[0][0].endswith("/v2.03.73/linux/CHANGELOG.md")
    with patch.object(updater, "_open", side_effect=urllib.error.URLError("x")):
        assert updater.fetch_changelog("v2.03.73") is None
    with patch.object(updater, "_open", return_value=R(b"x" * (updater.MAX_CHANGELOG_BYTES + 5))):
        assert updater.fetch_changelog("v2.03.73") is None


@pytest.mark.parametrize("tag", ["../x", "v1/../../a", "main", "", "v1.2.3?x=1", None])
def test_fetch_changelog_rejects_bad_tag(tag):
    with patch.object(updater, "_open") as o:
        assert updater.fetch_changelog(tag) is None
        o.assert_not_called()


def test_with_changelog_and_fallback():
    info = ("2.03.73", "release body", "d", "s")
    with patch.object(updater, "check_latest", return_value=info), \
         patch.object(updater, "fetch_changelog", return_value=CL):
        got = updater.check_latest_with_changelog("2.03.71")
        assert "2.03.72" in got[1] and got[2:] == ("d", "s")
    with patch.object(updater, "check_latest", return_value=info), \
         patch.object(updater, "fetch_changelog", return_value=None):
        assert updater.check_latest_with_changelog("2.03.71") == info
    with patch.object(updater, "check_latest", return_value=()):
        assert updater.check_latest_with_changelog("2.03.71") == ()

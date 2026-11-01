"""In-app updater: check GitHub releases, download + verify a .deb, install via pkexec.

GUI-free so it can be unit-tested; the dialogs live in gtksettings.py.
Release convention: tag ``v<ver>`` (or ``<ver>``), assets
``blitztext_<ver>_<arch>.deb`` plus ``blitztext_<ver>_<arch>.deb.sha256``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from . import logbuffer

API_URL = "https://api.github.com/repos/mARTin-B78/blitztext-app-linux/releases/latest"
TIMEOUT = 8
MAX_API_BYTES = 1 << 20          # release JSON
MAX_SHA_BYTES = 4096
MAX_DEB_BYTES = 2 << 30          # 2 GiB; the bundled venv is large but not that large
MAX_NOTES = 2000
CHECK_INTERVAL = 24 * 3600
_TMP_PREFIX = "blitztext-update-"

_VER_RE = re.compile(r"^\d+(?:\.\d+){0,3}$")
_ARCH_RE = re.compile(r"^[a-z0-9]+$")
_DEB_RE = re.compile(r"^blitztext_\d+(?:\.\d+){0,3}_[a-z0-9]+\.deb$")
_SHA_RE = re.compile(r"^([0-9a-fA-F]{64})(?:\s+\*?\S+)?\s*$")


class UpdateError(Exception):
    """User-presentable update failure (message contains no secrets/internals)."""


# ---- pure helpers -------------------------------------------------------------
def _vt(v: str) -> tuple[int, ...] | None:
    v = str(v).strip().lstrip("vV")
    return tuple(int(p) for p in v.split(".")) if _VER_RE.match(v) else None


def is_newer(a: str, b: str) -> bool:
    """True if version *a* is newer than *b* (dotted ints, e.g. 2.03.72)."""
    ta, tb = _vt(a), _vt(b)
    return ta is not None and tb is not None and ta > tb


def should_check(enabled: bool, last_check: float, now: float) -> bool:
    """Throttle: at most once per CHECK_INTERVAL (re-check if the clock went backwards)."""
    return bool(enabled) and (now - last_check >= CHECK_INTERVAL or now < last_check)


def should_offer(latest: str, current: str, skipped: str) -> bool:
    return is_newer(latest, current) and latest != skipped


def _host_ok(url: str) -> bool:
    try:
        p = urlsplit(url)
    except ValueError:
        return False
    host = p.hostname or ""
    return (p.scheme == "https" and not p.username and not p.password
            and (host in ("github.com", "api.github.com") or host.endswith(".githubusercontent.com")))


def download_url_ok(url: str) -> bool:
    """Assets may only come from https github.com / *.githubusercontent.com."""
    return _host_ok(url) and urlsplit(url).hostname != "api.github.com"


def pick_assets(release: dict, arch: str) -> tuple[str, str, str, str] | None:
    """(version, notes, deb_url, sha256_url) for *arch*, or None."""
    ver = str(release.get("tag_name") or "").strip().lstrip("vV")
    if not _VER_RE.match(ver) or not _ARCH_RE.match(arch or ""):
        return None
    urls = {a.get("name"): a.get("browser_download_url")
            for a in release.get("assets") or [] if isinstance(a, dict)}
    name = f"blitztext_{ver}_{arch}.deb"
    deb, sha = urls.get(name), urls.get(name + ".sha256")
    if not (isinstance(deb, str) and isinstance(sha, str)
            and download_url_ok(deb) and download_url_ok(sha)):
        return None
    notes = str(release.get("body") or "")[:MAX_NOTES]
    return ver, notes, deb, sha


def parse_sha256(text: str) -> str:
    """Accept `<hex>` or sha256sum output `<hex>  <file>`; return lowercase hex."""
    m = _SHA_RE.match(text.strip().splitlines()[0] if text.strip() else "")
    if not m:
        raise UpdateError("The release checksum file is malformed.")
    return m.group(1).lower()


# ---- network --------------------------------------------------------------------
class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _host_ok(newurl):
            raise urllib.error.URLError("redirect to untrusted host")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(url: str, timeout: float = TIMEOUT):
    if not _host_ok(url):
        raise urllib.error.URLError("untrusted URL")
    req = urllib.request.Request(url, headers={
        "User-Agent": "blitztext-updater", "Accept": "application/vnd.github+json, */*"})
    return urllib.request.build_opener(_SafeRedirect).open(req, timeout=timeout)


def _read_capped(resp, cap: int) -> bytes:
    data = resp.read(cap + 1)
    if len(data) > cap:
        raise ValueError("response too large")
    return data


def machine_arch() -> str | None:
    try:
        out = subprocess.run(["dpkg", "--print-architecture"], capture_output=True,
                             text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return out if _ARCH_RE.match(out) else None


def check_latest(arch: str | None = None) -> tuple[str, str, str, str] | tuple[()] | None:
    """Latest release info for this machine.

    Returns ``()`` when GitHub answered but has no usable release (404 / no asset for
    this arch), and None on network errors or bad responses (logged, silent).
    """
    try:
        arch = arch or machine_arch()
        if not arch:
            return None
        with _open(API_URL) as resp:
            release = json.loads(_read_capped(resp, MAX_API_BYTES))
        info = pick_assets(release, arch) if isinstance(release, dict) else None
        if info is None:
            logbuffer.log(f"[update] latest release has no {arch} .deb + .sha256", level="DEBUG")
        return info if info else ()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return ()
        logbuffer.log(f"[update] check failed (HTTP {exc.code})", level="WARNING")
        return None
    except Exception as exc:  # noqa: BLE001 - update check must never break the app
        logbuffer.log(f"[update] check failed ({type(exc).__name__})", level="WARNING")
        return None


def download(deb_url: str, sha_url: str, progress=None) -> str:
    """Download + sha256-verify the .deb into a fresh temp dir; return its path."""
    name = urlsplit(deb_url).path.rsplit("/", 1)[-1] if download_url_ok(deb_url) else ""
    if not (_DEB_RE.match(name) and download_url_ok(sha_url)):
        raise UpdateError("Refusing to download from an untrusted location.")
    try:
        with _open(sha_url) as resp:
            expected = parse_sha256(_read_capped(resp, MAX_SHA_BYTES).decode("ascii", "replace"))
    except (OSError, ValueError) as exc:
        logbuffer.log(f"[update] checksum download failed ({type(exc).__name__})", level="WARNING")
        raise UpdateError("Could not download the release checksum.") from None
    tmpdir = tempfile.mkdtemp(prefix=_TMP_PREFIX)
    path = os.path.join(tmpdir, name)
    h = hashlib.sha256()
    try:
        with _open(deb_url) as resp, open(path, "wb") as fh:
            total, length = 0, getattr(resp, "length", None)
            while chunk := resp.read(1 << 16):
                total += len(chunk)
                if total > MAX_DEB_BYTES:
                    raise UpdateError("The update file is unexpectedly large.")
                h.update(chunk)
                fh.write(chunk)
                if progress and length:
                    progress(min(total / length, 1.0))
        if not hmac.compare_digest(h.hexdigest(), expected):
            raise UpdateError("Checksum mismatch - the download was discarded.")
    except UpdateError:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise
    except Exception as exc:  # noqa: BLE001
        shutil.rmtree(tmpdir, ignore_errors=True)
        logbuffer.log(f"[update] download failed ({type(exc).__name__})", level="WARNING")
        raise UpdateError("Download failed. Check your network connection.") from None
    return path


def _is_update_file(path: str) -> bool:
    parent = os.path.dirname(path)
    return (os.path.isabs(path) and _DEB_RE.match(os.path.basename(path)) is not None
            and os.path.basename(parent).startswith(_TMP_PREFIX)
            and os.path.realpath(os.path.dirname(parent)) == os.path.realpath(tempfile.gettempdir())
            and os.path.isfile(path) and not os.path.islink(path))


def install(path: str) -> None:
    """`pkexec apt install -y <verified temp .deb>`; temp dir removed afterwards."""
    if not _is_update_file(path):
        raise UpdateError("Refusing to install a file that was not downloaded by the updater.")
    try:
        rc = subprocess.run(["pkexec", "apt", "install", "-y", path], timeout=1800).returncode
    except FileNotFoundError:
        raise UpdateError("pkexec is not installed (package: pkexec / policykit-1).") from None
    except subprocess.TimeoutExpired:
        raise UpdateError("The installation timed out.") from None
    finally:
        shutil.rmtree(os.path.dirname(path), ignore_errors=True)
    if rc in (126, 127):
        raise UpdateError("Authorization was cancelled or not authorized. "
                          "Blitztext was not updated.")
    if rc != 0:
        raise UpdateError(f"Installation failed (apt exit code {rc}). Blitztext was not updated.")


def update(deb_url: str, sha_url: str, progress=None) -> None:
    install(download(deb_url, sha_url, progress))

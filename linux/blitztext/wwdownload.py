"""Download community openWakeWord models into the server's model directory.

Pulls wake models from the community collection
https://github.com/fwartner/home-assistant-wakewords-collection and drops them
into a `wyoming-openwakeword` server's ``--custom-model-dir``.

That collection is explicitly an **openWakeWord** collection (see its README),
so the models belong next to a ``rhasspy/wyoming-openwakeword`` server — *not*
the microWakeWord server, whose ``.tflite`` files are a different, incompatible
format. openWakeWord custom models need no JSON manifest: the server scans its
``--custom-model-dir`` for model files and the wake-word id is the file stem
(e.g. ``computer.tflite`` → ``computer``). With the default tflite inference
framework the ``.tflite`` is what gets loaded; the ``.onnx`` is kept alongside
it (matching the existing convention in that dir) so the model also works if the
server is switched to the onnx framework.

Some collection folders ship only an ``.onnx`` (no ``.tflite``); those install
fine but will only be picked up by a server running ``--inference-framework
onnx``.

Everything is stdlib (urllib + subprocess) so no extra dependency is pulled in.
"""
from __future__ import annotations

import re
import json
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path


def _q(segment: str) -> str:
    """URL-encode a single path segment (folder names may contain spaces)."""
    return urllib.parse.quote(segment, safe="")

REPO = "fwartner/home-assistant-wakewords-collection"
API = f"https://api.github.com/repos/{REPO}/contents"
RAW = f"https://raw.githubusercontent.com/{REPO}/main"
_UA = {"User-Agent": "Blitztext-wakeword-downloader"}

# Fallback if the GitHub API is rate-limited when listing the repo root.
KNOWN_LANGUAGES = ["en", "dk", "fi", "ru", "zh"]

# Model file kinds openWakeWord can load, preferred first (tflite is the server
# default inference framework).
MODEL_EXTS = (".tflite", ".onnx")


def _get_json(url: str):
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def list_languages() -> list[str]:
    """Top-level language folders in the collection (en, dk, …)."""
    try:
        items = _get_json(API)
        langs = sorted(x["name"] for x in items
                       if x["type"] == "dir" and not x["name"].startswith("."))
        return langs or KNOWN_LANGUAGES
    except Exception:
        return KNOWN_LANGUAGES


def list_models(lang: str) -> list[str]:
    """Wakeword names available for a language (each is a sub-folder)."""
    items = _get_json(f"{API}/{_q(lang)}")
    return sorted((x["name"] for x in items if x["type"] == "dir"),
                  key=str.lower)


def list_variants(lang: str, name: str) -> list[dict]:
    """Downloadable model files in one wakeword folder.

    Returns dicts ``{file, ext, version, size, url}``, sorted so the preferred
    format (``.tflite``) and newest version come first. Empty if the folder has
    no usable model file (e.g. only a README).
    """
    items = _get_json(f"{API}/{_q(lang)}/{_q(name)}")
    out = []
    for x in items:
        fn = x["name"]
        ext = next((e for e in MODEL_EXTS if fn.endswith(e)), None)
        if not ext:
            continue
        m = re.search(r"_v(\d+)\." + ext.lstrip(".") + "$", fn)
        out.append({
            "file": fn,
            "ext": ext,
            "version": int(m.group(1)) if m else 0,
            "size": x.get("size", 0),
            "url": x.get("download_url")
            or f"{RAW}/{_q(lang)}/{_q(name)}/{_q(fn)}",
        })
    # tflite before onnx, then newest version first.
    out.sort(key=lambda v: (MODEL_EXTS.index(v["ext"]), -v["version"]))
    return out


def has_tflite(variants: list[dict]) -> bool:
    return any(v["ext"] == ".tflite" for v in variants)


def readme_url(lang: str, name: str) -> str:
    return f"{RAW}/{_q(lang)}/{_q(name)}/README.md"


def phrase_from_name(name: str) -> str:
    """Human spoken phrase from a folder name, e.g. 'hey_jarvis' → 'Hey Jarvis'."""
    words = re.split(r"[_\s]+", name.strip())
    return " ".join(w.capitalize() for w in words if w)


def slug(name: str) -> str:
    """Filesystem/identifier-safe wake-word id, e.g. 'Hey Lara' → 'hey_lara'."""
    s = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return s or "wakeword"


def _download(url: str, dest: Path, *, ext: str) -> int:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    if ext == ".tflite" and b"TFL3" not in data[:32]:
        # .tflite carries the "TFL3" flatbuffer id near the start; guard against
        # an HTML error page being saved as a model.
        raise ValueError(f"Downloaded file is not a .tflite model ({len(data)} bytes)")
    if ext == ".onnx" and not data[:8].startswith(b"\x08"):
        # ONNX is a protobuf; first field (ir_version) is tag 0x08. Loose guard.
        if b"onnx" not in data[:64].lower():
            raise ValueError(f"Downloaded file is not an .onnx model ({len(data)} bytes)")
    dest.write_bytes(data)
    return len(data)


def install(lang: str, name: str, model_dir: str | Path,
            *, variants: list[dict] | None = None,
            all_formats: bool = True) -> dict:
    """Download a wake model into ``model_dir`` for openWakeWord.

    Files are saved under the clean id ``<slug><ext>`` regardless of the
    upstream versioned filename. With ``all_formats`` both ``.tflite`` and
    ``.onnx`` are fetched when available (newest version of each); otherwise only
    the single preferred variant. No JSON manifest is written — openWakeWord
    discovers models by filename.

    Returns ``{"model_id", "files": [...], "tflite": bool}``.
    """
    model_dir = Path(model_dir)
    if not model_dir.is_dir():
        raise FileNotFoundError(f"Model directory does not exist: {model_dir}")

    if variants is None:
        variants = list_variants(lang, name)
    if not variants:
        raise ValueError(f"No openWakeWord model files found for '{name}' ({lang}).")

    # Pick newest version per extension; either both formats or just the best.
    chosen: dict[str, dict] = {}
    for v in variants:  # already sorted tflite-first, newest-first
        chosen.setdefault(v["ext"], v)
    picks = list(chosen.values()) if all_formats else [variants[0]]

    model_id = slug(name)
    files = []
    for v in picks:
        dest = model_dir / f"{model_id}{v['ext']}"
        _download(v["url"], dest, ext=v["ext"])
        files.append(dest.name)
    return {
        "model_id": model_id,
        "files": files,
        "tflite": any(f.endswith(".tflite") for f in files),
    }


# ── Docker helpers (auto-detect the server's model dir & restart it) ──────────

def _port_of(uri: str) -> str:
    """Extract the port from a ``tcp://host:port`` wakeword URI."""
    m = re.search(r":(\d+)\s*$", (uri or "").strip())
    return m.group(1) if m else ""


def _inspect_servers() -> list[dict]:
    """All running wakeword containers with their uri-port, framework & dir.

    Returns dicts ``{name, port, framework, model_dir}``. ``framework`` is
    ``"openwakeword"``, ``"micro"`` or ``""``; ``model_dir`` is the host source
    of the container's ``--custom-model-dir`` mount (empty if none).
    """
    try:
        out = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Image}}"],
            capture_output=True, text=True, timeout=10,
        ).stdout
    except Exception:
        return []

    fmt = ("{{range .Mounts}}{{.Source}}\t{{.Destination}}\n{{end}}"
           "===\t{{join .Args \" \"}}")
    servers = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 2:
            continue
        nm, img = parts
        hay = (nm + " " + img).lower().replace("-", "").replace("_", "")
        if "micro" in hay and "wakeword" in hay:
            framework = "micro"
        elif "openwakeword" in hay:
            framework = "openwakeword"
        else:
            continue
        try:
            info = subprocess.run(
                ["docker", "inspect", "--format", fmt, nm],
                capture_output=True, text=True, timeout=10,
            ).stdout
        except Exception:
            continue
        mounts, _, argline = info.partition("===")
        port_m = re.search(r"--uri[=\s]+\S*?:(\d+)", argline)
        dir_m = re.search(r"--custom-model-dir[=\s]+(\S+)", argline)
        model_dir = ""
        if dir_m:
            dest = dir_m.group(1).strip("[]'\" ")
            for ml in mounts.splitlines():
                src, _, d = ml.partition("\t")
                if d.strip() == dest and src.strip():
                    model_dir = src.strip()
                    break
        servers.append({
            "name": nm,
            "port": port_m.group(1) if port_m else "",
            "framework": framework,
            "model_dir": model_dir,
        })
    return servers


def autodetect_for_uri(uri: str) -> dict:
    """Resolve the model dir for the server a wakeword engine points at.

    Matches the engine's URI port against the running containers. Returns
    ``{framework, model_dir, containers, compatible}`` where ``framework`` is
    that server's type, ``compatible`` is True only for openWakeWord (the
    collection's format). If the matched server is microWakeWord (or unmatched),
    ``model_dir``/``containers`` fall back to the openWakeWord servers so the
    download still goes somewhere usable, and ``compatible`` flags the mismatch.
    """
    port = _port_of(uri)
    servers = _inspect_servers()
    match = next((s for s in servers if port and s["port"] == port), None)

    if match and match["framework"] == "openwakeword" and match["model_dir"]:
        # All openWakeWord containers sharing this dir need a restart together.
        cs = [s["name"] for s in servers
              if s["framework"] == "openwakeword" and s["model_dir"] == match["model_dir"]]
        return {"framework": "openwakeword", "model_dir": match["model_dir"],
                "containers": cs, "compatible": True}

    # Engine is microWakeWord (or no match): fall back to the openWakeWord dir.
    owdir, owc = autodetect()
    return {
        "framework": match["framework"] if match else "",
        "model_dir": owdir,
        "containers": owc,
        "compatible": False,
    }


def autodetect() -> tuple[str, list[str]]:
    """Find the running openWakeWord model dir and the containers using it.

    Returns ``(model_dir, [container, ...])`` or ``("", [])`` if not found.
    Several openWakeWord containers may share one ``--custom-model-dir`` host
    folder (detection + a preload server); all of them need a restart to pick up
    a new model, so they are returned together.
    """
    try:
        out = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Image}}"],
            capture_output=True, text=True, timeout=10,
        ).stdout
    except Exception:
        return "", []

    candidates = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 2:
            continue
        nm, img = parts
        hay = (nm + " " + img).lower().replace("-", "").replace("_", "")
        # openWakeWord, but NOT microwakeword (different, incompatible format).
        if "openwakeword" in hay and "micro" not in hay:
            candidates.append(nm)

    fmt = ("{{range .Mounts}}{{.Source}}\t{{.Destination}}\n{{end}}"
           "===\t{{join .Args \" \"}}")
    dirs: dict[str, list[str]] = {}
    for container in candidates:
        try:
            info = subprocess.run(
                ["docker", "inspect", "--format", fmt, container],
                capture_output=True, text=True, timeout=10,
            ).stdout
        except Exception:
            continue
        mounts, _, argline = info.partition("===")
        m = re.search(r"--custom-model-dir[=\s]+(\S+)", argline)
        if not m:
            continue
        dest = m.group(1).strip("[]'\" ")
        for line in mounts.splitlines():
            src, _, d = line.partition("\t")
            if d.strip() == dest and src.strip():
                dirs.setdefault(src.strip(), []).append(container)
                break
    if not dirs:
        return "", []
    # Most-shared dir wins (the one the real detection servers point at).
    best = max(dirs.items(), key=lambda kv: len(kv[1]))
    return best[0], best[1]


def restart_containers(containers: list[str]) -> tuple[bool, str]:
    """`docker restart` each container. Returns (all_ok, message)."""
    if not containers:
        return False, "No container configured."
    ok_all, msgs = True, []
    for c in containers:
        try:
            p = subprocess.run(["docker", "restart", c],
                               capture_output=True, text=True, timeout=60)
        except FileNotFoundError:
            return False, "docker not found on PATH."
        except subprocess.TimeoutExpired:
            ok_all = False
            msgs.append(f"{c}: timed out")
            continue
        if p.returncode == 0:
            msgs.append(f"restarted {c}")
        else:
            ok_all = False
            msgs.append(f"{c}: {(p.stderr or p.stdout or 'failed').strip()}")
    return ok_all, "; ".join(msgs)

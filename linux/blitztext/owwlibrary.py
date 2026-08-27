"""Search an openwakeword.com-compatible community model library.

Targets the accountless "agent" REST API documented at
https://openwakeword.com/api/agent/docs (the same API shape is used by
microwakeword.com). Searching is free and needs no auth. Downloading the
actual model file, however, requires either the small per-model fee that API
charges, or — more simply for a user who already has a free website account —
signing in at the site and clicking its own download button. This module only
covers the free search step; the browser handles the actual download, and
``wwdownload.install_local`` copies the result into place.

Everything is stdlib (urllib) so no extra dependency is pulled in.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

_UA = {"User-Agent": "Blitztext-wakeword-search"}


def search(base_url: str, query: str, language: str | None = None) -> list[dict]:
    """Free-text search over a library's public model catalog.

    ``base_url`` is the API root, e.g. ``https://openwakeword.com/api/agent``.
    Returns the raw ``results`` list (each has ``model_id``, ``wake_word``,
    ``languages``, ``recall_pct``, ``fa_per_hour``, ``human_test_url``, …).
    """
    params = {"q": query}
    if language:
        params["language"] = language
    url = f"{base_url.rstrip('/')}/library/search?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data.get("results") or []


def site_root(base_url: str) -> str:
    """Guess the human-facing website root from an ``.../api/agent`` base URL."""
    return base_url.rstrip("/").removesuffix("/api/agent")


def library_page_url(base_url: str, model_id) -> str:
    """The browser page for one model, e.g. https://openwakeword.com/library/48."""
    return f"{site_root(base_url)}/library/{model_id}"

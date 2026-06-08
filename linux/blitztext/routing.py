"""Voice-keyword routing.

Given a transcript, find a trigger keyword at the start or end that selects a
preset, strip it, and return the cleaned text. ASR-tolerant: normalizes text and
fuzzy-matches so "nicer e-mail." still routes to the "nicer email" preset.

Only the leading/trailing word-windows are scanned, so a keyword spoken inside
the body doesn't misfire. Returns the best match across all presets.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

# How similar a window has to be to a keyword phrase to count as a match.
DEFAULT_THRESHOLD = 0.82
# A keyword phrase of N words is matched against the first/last N words (+ a
# little slack) of the transcript.
EDGE_SLACK = 1


@dataclass
class RouteResult:
    preset_name: str | None      # None -> no keyword matched (use default)
    text: str                    # transcript with the keyword stripped
    keyword: str | None          # the configured keyword that matched
    position: str | None         # "start" | "end"
    score: float


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def normalize(text: str) -> list[str]:
    """Lowercase, drop accents/punctuation, return word tokens."""
    text = _strip_accents(text.lower())
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return text.split()


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _match_window(tokens: list[str], kw_tokens: list[str], threshold: float):
    """Try to match kw_tokens against the start and end of tokens.

    Tries span lengths of n-1..n+1 words at each edge so ASR token drift
    (e.g. "e-mail" -> "e mail") still matches. Returns (position, score,
    span_len) for the best edge match, or None.
    """
    n = len(kw_tokens)
    if not n or not tokens:
        return None
    kw = " ".join(kw_tokens)

    best = None
    for span in range(max(1, n - EDGE_SLACK), n + EDGE_SLACK + 1):
        if span > len(tokens):
            continue
        for pos, window in (("start", tokens[:span]), ("end", tokens[-span:])):
            score = _similar(" ".join(window), kw)
            if score >= threshold and (best is None or score > best[1]):
                best = (pos, score, span)
    return best


def route(
    transcript: str,
    presets,
    *,
    threshold: float = DEFAULT_THRESHOLD,
) -> RouteResult:
    """Pick the preset whose keyword best matches an edge of the transcript.

    `presets` is any iterable of objects with `.name` and `.keywords` (list[str]).
    """
    tokens = normalize(transcript)
    if not tokens:
        return RouteResult(None, transcript.strip(), None, None, 0.0)

    best = None  # (score, span_len, position, preset_name, keyword)
    for preset in presets:
        # The preset's own name is always an implicit trigger, so a preset is
        # speakable by name even when it has no keywords configured.
        candidates = list(getattr(preset, "keywords", None) or [])
        name = getattr(preset, "name", "")
        if name:
            candidates.append(name)
        for keyword in candidates:
            kw_tokens = normalize(keyword)
            m = _match_window(tokens, kw_tokens, threshold)
            if m is None:
                continue
            position, score, span = m
            # Prefer higher score, then longer (more specific) keyword phrase.
            key = (score, span)
            if best is None or key > (best[0], best[1]):
                best = (score, span, position, preset.name, keyword)

    if best is None:
        return RouteResult(None, transcript.strip(), None, None, 0.0)

    score, span, position, name, keyword = best
    cleaned = _strip_span(transcript, span, position)
    return RouteResult(name, cleaned, keyword, position, score)


def is_cancel(transcript: str, cancel_keywords, *, threshold: float = DEFAULT_THRESHOLD) -> str | None:
    """Return the cancel keyword that matches an edge of the transcript, else None.

    Lets a spoken word like "abbrechen" abort an (often accidentally triggered)
    dictation before it is routed, rewritten, or delivered. Matched the same
    edge-anchored, ASR-tolerant way as routing keywords, so the word appearing
    deep inside a sentence won't trigger it — only at the start or end.
    """
    if not cancel_keywords:
        return None
    tokens = normalize(transcript)
    if not tokens:
        return None
    for kw in cancel_keywords:
        kw_tokens = normalize(kw)
        if kw_tokens and _match_window(tokens, kw_tokens, threshold) is not None:
            return kw
    return None


def match_send(transcript: str, send_keywords, *, threshold: float = DEFAULT_THRESHOLD):
    """Detect a spoken 'send' keyword at an edge; return (keyword, cleaned_text).

    Like is_cancel, but the keyword is *stripped* and the remaining text is meant
    to be delivered and submitted with Enter — the spoken equivalent of
    stop+paste+Enter. Returns (None, transcript) when nothing matches. Matched the
    same edge-anchored, ASR-tolerant way as routing keywords, so the word deep
    inside a sentence won't trigger it — only at the start or end.
    """
    if not send_keywords:
        return None, transcript
    tokens = normalize(transcript)
    if not tokens:
        return None, transcript
    best = None  # (score, span, position, keyword)
    for kw in send_keywords:
        kw_tokens = normalize(kw)
        m = _match_window(tokens, kw_tokens, threshold)
        if m is None:
            continue
        position, score, span = m
        if best is None or (score, span) > (best[0], best[1]):
            best = (score, span, position, kw)
    if best is None:
        return None, transcript
    _score, span, position, kw = best
    return kw, _strip_span(transcript, span, position)


def _strip_span(transcript: str, span_words: int, position: str) -> str:
    """Remove the matched keyword from the given edge of the original transcript.

    `span_words` counts *normalized* tokens; a raw word like "e-mail." may
    normalize to two tokens, so we consume raw words until their cumulative
    normalized-token count reaches the span. Original casing/spacing is kept.
    """
    words = transcript.split()
    seq = words if position == "start" else list(reversed(words))

    consumed = 0
    ntok = 0
    for w in seq:
        ntok += len(normalize(w))
        consumed += 1
        if ntok >= span_words:
            break

    remaining = words[consumed:] if position == "start" else words[: len(words) - consumed]
    out = " ".join(remaining)
    # Trim leftover separators left where the keyword was removed.
    return out.strip(" \t\r\n,.;:!?-–—\"'").strip()

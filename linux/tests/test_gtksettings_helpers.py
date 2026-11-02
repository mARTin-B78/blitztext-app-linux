"""Characterization checks for pure helpers extracted from gtksettings.py.

Loaded via AST (like test_tts.py) so no GTK display is needed.
"""

import ast
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

_SRC = Path(__file__).resolve().parents[1] / "blitztext" / "gtksettings.py"
_NAMES = {"_grade_color", "_status_color", "_item_at", "_oww_result_row", "_emoji_keywords",
          "_emoji_matches", "_md_is_table_row", "_md_gather_table", "_md_col_widths",
          "_md_table_line", "_bench_engine_langs"}


@pytest.fixture(scope="module")
def h():
    tree = ast.parse(_SRC.read_text())
    keep = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in _NAMES]
    keep += [n for n in tree.body if isinstance(n, ast.Assign)
             and ast.unparse(n.targets[0]) in {"_MD_TBL_SEP_RE", "(GREEN, RED, GREY)"}]
    import unicodedata
    scope = {"re": re, "unicodedata": unicodedata, "stt": SimpleNamespace()}
    exec(compile(ast.Module(body=keep, type_ignores=[]), str(_SRC), "exec"), scope)
    assert _NAMES <= scope.keys()
    return SimpleNamespace(**scope)


def test_grade_and_status_colors(h):
    assert [h._grade_color(g, f) for g, f in ((True, True), (True, False), (False, True), (False, False))] \
        == [h.GREEN, h.GREEN, "#ff9f0a", h.RED]
    calls = []
    assert h._status_color(None, calls.append) == h.GREY and calls == []  # no probe without engine
    assert h._status_color("e", lambda e: True) == h.GREEN
    assert h._status_color("e", lambda e: False) == h.RED


def test_item_at_rejects_out_of_range_and_negative(h):
    assert h._item_at([1, 2], 1) == 2
    assert h._item_at([1, 2], 2) is None and h._item_at([1, 2], -1) is None


def test_oww_result_row(h):
    src = SimpleNamespace(name="Lib", url="https://x/api")
    m = {"wake_word": "Hey", "model_id": 3, "recall_pct": 87.6,
         "languages": [{"code": "en", "percentage": 91.4}, {"code": "de"}]}
    row = h._oww_result_row(m, src)
    assert row[:3] == ['"Hey"  —  en 91%, de 0%  —  recall 88%  —  Lib', "oww", "Lib"]
    assert row[3] == {**m, "base_url": "https://x/api", "wake_word": "Hey"} and "base_url" not in m
    assert h._oww_result_row({}, src)[0] == '"?"  —  Lib'


def test_markdown_table_helpers(h):
    lines = ["| a | **bold** |", "|---|:-:|", "| `c` | d | extra |", "after"]
    rows, i = h._md_gather_table(lines, 0)
    assert i == 3 and rows == [["a", "**bold**"], ["`c`", "d", "extra"]]
    widths = h._md_col_widths(rows, 3)
    assert widths == [1, 4, 5]
    assert h._md_table_line(rows[0], widths, 3) == "a  bold         "
    assert not h._md_is_table_row("a | b")


def test_emoji_matches(h):
    assert h._emoji_matches(["😀", "🐶"], "dog") == ["🐶"]
    assert h._emoji_matches(["😀", "🐶"], "😀") == ["😀"]


def test_bench_engine_langs_caches_per_url(h):
    calls = []
    M = lambda i, langs: SimpleNamespace(id=i, languages=langs)
    meta = [M("org/m1", ["de"]), M("org/m2", ["en"])]
    h.stt.list_models_meta = lambda url, key, timeout: (calls.append(url), meta)[1]
    E = lambda model: SimpleNamespace(url="u", api_key_env="", model=model)
    cache = {}
    assert h._bench_engine_langs(E("m2"), cache) == ["en"]
    assert h._bench_engine_langs(E("zz"), cache) == ["de"]   # no match → first model
    assert h._bench_engine_langs(E(""), cache) == ["de"]
    assert calls == ["u"]


def test_self_call_keywords_match_signatures():
    """Regression: _talk_commit(show_errors=...) was called after the parameter was removed."""
    bad = []
    for cls in (n for n in ast.walk(ast.parse(_SRC.read_text())) if isinstance(n, ast.ClassDef)):
        sigs = {f.name: f.args for f in cls.body if isinstance(f, ast.FunctionDef)}
        for c in (n for n in ast.walk(cls) if isinstance(n, ast.Call)):
            f = c.func
            if (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name)
                    and f.value.id == "self" and f.attr in sigs and not sigs[f.attr].kwarg):
                ok = {a.arg for a in sigs[f.attr].args + sigs[f.attr].kwonlyargs}
                bad += [f"{cls.name}.{f.attr}({k.arg}=) line {c.lineno}"
                        for k in c.keywords if k.arg and k.arg not in ok]
    assert not bad, bad

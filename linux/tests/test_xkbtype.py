import pytest

from blitztext import xkbtype

pytestmark = pytest.mark.skipif(not xkbtype.available(), reason="libxkbcommon not installed")

DE = ("de", "nodeadkeys", "")


def _keys(text, layout=DE):
    return xkbtype.keystrokes(text, *layout)


def test_umlauts_and_punctuation_on_german_layout():
    assert _keys("ö") == ["39:1", "39:0"]                      # KEY_SEMICOLON
    assert _keys("?") == ["42:1", "12:1", "12:0", "42:0"]      # Shift + KEY_MINUS
    assert _keys("z") == ["21:1", "21:0"]                      # KEY_Y on QWERTZ
    assert _keys("A") == ["42:1", "30:1", "30:0", "42:0"]
    assert _keys("@") == ["100:1", "16:1", "16:0", "100:0"]    # AltGr + KEY_Q


def test_us_layout():
    assert _keys("z", ("us", "", "")) == ["44:1", "44:0"]


def test_newline_is_shift_enter():
    assert _keys("\n") == ["42:1", "28:1", "28:0", "42:0"]


def test_char_not_on_layout_uses_unicode_entry():
    # Ctrl+Shift+U, release, "e9", Space (IBus/GTK unicode input)
    assert _keys("é") == [xkbtype.PAUSE, "29:1", "42:1", "22:1", "22:0", "42:0", "29:0",
                          "18:1", "18:0", "10:1", "10:0", "57:1", "57:0", xkbtype.PAUSE]


def test_unknown_layout_returns_none():
    assert _keys("a", ("no-such-layout", "", "")) is None


@pytest.mark.parametrize(("raw", "expected"), [
    ("[('xkb', 'de+nodeadkeys')]", ("de", "nodeadkeys")),
    ("[('xkb', 'us'), ('xkb', 'de')]", ("us", "")),
    ("[('ibus', 'mozc-jp')]", None),
    ("@a(ss) []", None),
])
def test_parse_sources(raw, expected):
    assert xkbtype._parse_source(raw) == expected

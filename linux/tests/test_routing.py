import pytest
from dataclasses import dataclass
from blitztext.routing import route, normalize, _strip_span

@dataclass
class DummyPreset:
    name: str
    keywords: list[str]

def test_normalize():
    assert normalize("Nicer E-Mail.") == ["nicer", "e", "mail"]
    assert normalize("calm down!") == ["calm", "down"]

def test_route_no_presets():
    res = route("Hello world", [])
    assert res.preset_name is None
    assert res.text == "Hello world"
    assert res.keyword is None

def test_route_match_start():
    presets = [
        DummyPreset("Email", ["nicer email", "bessere email"]),
        DummyPreset("Calm", ["calm down"]),
    ]
    res = route("Nicer e-mail can you send me the report", presets)
    assert res.preset_name == "Email"
    assert res.keyword == "nicer email"
    assert res.position == "start"
    assert res.text == "can you send me the report"

def test_route_match_end():
    presets = [
        DummyPreset("Email", ["nicer email"]),
        DummyPreset("Calm", ["calm down"]),
    ]
    res = route("Can you send me the report nicer email", presets)
    assert res.preset_name == "Email"
    assert res.keyword == "nicer email"
    assert res.position == "end"
    assert res.text == "Can you send me the report"

def test_route_no_match_middle():
    presets = [
        DummyPreset("Email", ["nicer email"]),
    ]
    res = route("Can you send me a nicer email please", presets)
    assert res.preset_name is None
    assert res.text == "Can you send me a nicer email please"

def test_strip_span():
    # 'nicer e-mail' normalizes to 3 tokens
    res = _strip_span("Nicer e-mail can you send me the report", 3, "start")
    assert res == "can you send me the report"

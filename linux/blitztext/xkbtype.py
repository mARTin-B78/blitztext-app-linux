"""Layout-aware typing for ydotool on Wayland, without the clipboard.

`ydotool type` sends US-layout keycodes, so umlauts are impossible and z/y and
punctuation come out wrong on other layouts. Instead, resolve each character to
keycode + Shift/AltGr in the active GNOME layout (libxkbcommon via ctypes) and
send the raw keycodes with `ydotool key`.
"""

from __future__ import annotations

import ast
import ctypes
import ctypes.util
import functools
import subprocess

_KEY_LEFTSHIFT = 42
_KEY_LEFTCTRL = 29
_KEY_U = 22
_KEY_ENTER = 28
_EVDEV_OFFSET = 8  # XKB keycode = evdev keycode + 8
_KEYSYM_RETURN = 0xFF0D
_KEYSYM_LEVEL3 = 0xFE03  # ISO_Level3_Shift (AltGr)
_KEY_RIGHTALT = 100
# Marks a split point in keystrokes(): IBus handles unicode entry asynchronously
# and reorders it when sent in one ydotool call with other keys; the gap between
# separate calls is enough.
PAUSE = "pause"


class _RuleNames(ctypes.Structure):
    _fields_ = [(n, ctypes.c_char_p) for n in ("rules", "model", "layout", "variant", "options")]


@functools.cache
def _lib():
    name = ctypes.util.find_library("xkbcommon")
    if not name:
        return None
    lib = ctypes.CDLL(name)
    p, u32, i = ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int
    sigs = {
        "xkb_context_new": (p, [i]),
        "xkb_keymap_new_from_names": (p, [p, ctypes.POINTER(_RuleNames), i]),
        "xkb_keymap_min_keycode": (u32, [p]),
        "xkb_keymap_max_keycode": (u32, [p]),
        "xkb_keymap_num_levels_for_key": (u32, [p, u32, u32]),
        "xkb_keymap_key_get_syms_by_level": (i, [p, u32, u32, u32, ctypes.POINTER(ctypes.POINTER(u32))]),
        "xkb_keymap_key_get_mods_for_level": (ctypes.c_size_t, [p, u32, u32, u32, ctypes.POINTER(u32), ctypes.c_size_t]),
        "xkb_keymap_mod_get_index": (u32, [p, ctypes.c_char_p]),
        "xkb_utf32_to_keysym": (u32, [u32]),
    }
    for fn, (res, args) in sigs.items():
        getattr(lib, fn).restype = res
        getattr(lib, fn).argtypes = args
    return lib


def available() -> bool:
    return _lib() is not None


@functools.cache
def _keysym_map(layout: str, variant: str, options: str) -> dict[int, tuple[int, bool, bool]] | None:
    """keysym -> (evdev keycode, shift, altgr), preferring the fewest modifiers."""
    lib = _lib()
    if lib is None:
        return None
    ctx = lib.xkb_context_new(0)
    names = _RuleNames(b"evdev", b"pc105", layout.encode(), variant.encode(), options.encode())
    keymap = lib.xkb_keymap_new_from_names(ctx, ctypes.byref(names), 0)
    if not keymap:
        return None

    def bit(name: bytes) -> int:
        idx = lib.xkb_keymap_mod_get_index(keymap, name)
        return 0 if idx == 0xFFFFFFFF else 1 << idx

    shift = bit(b"Shift")
    level3 = bit(b"Mod5") | bit(b"LevelThree")

    found: dict[int, tuple[int, int, bool, bool]] = {}  # keysym -> (cost, code, shift, altgr)
    level3_keys: set[int] = set()
    syms = ctypes.POINTER(ctypes.c_uint32)()
    masks = (ctypes.c_uint32 * 16)()
    for kc in range(lib.xkb_keymap_min_keycode(keymap), lib.xkb_keymap_max_keycode(keymap) + 1):
        for level in range(lib.xkb_keymap_num_levels_for_key(keymap, kc, 0)):
            n_syms = lib.xkb_keymap_key_get_syms_by_level(keymap, kc, 0, level, ctypes.byref(syms))
            if n_syms != 1:
                continue
            n_masks = lib.xkb_keymap_key_get_mods_for_level(keymap, kc, 0, level, masks, len(masks))
            for mask in masks[:n_masks]:
                if mask & ~(shift | level3):  # needs Lock/NumLock/...: skip
                    continue
                use_shift, use_l3 = bool(mask & shift), bool(mask & level3)
                if syms[0] == _KEYSYM_LEVEL3 and not mask:
                    level3_keys.add(kc - _EVDEV_OFFSET)
                cand = (use_shift + use_l3, kc - _EVDEV_OFFSET, use_shift, use_l3)
                if syms[0] not in found or cand < found[syms[0]]:
                    found[syms[0]] = cand
    # Several keys may map to Level3 (incl. XKB's virtual LVL3 key): prefer Right Alt.
    altgr = _KEY_RIGHTALT if _KEY_RIGHTALT in level3_keys else min(level3_keys, default=0)
    keysyms = {sym: (code, s, l3) for sym, (_c, code, s, l3) in found.items()}
    if not altgr:  # no AltGr key: drop everything that needs it
        keysyms = {sym: v for sym, v in keysyms.items() if not v[2]}
    keysyms[-1] = (altgr, False, False)  # stash AltGr keycode
    return keysyms


def keystrokes(text: str, layout: str, variant: str = "", options: str = "") -> list[str] | None:
    """ydotool key args typing *text*; None if the layout can't be loaded.

    Characters missing from the layout (é on de+nodeadkeys, emoji) go through
    IBus/GTK unicode entry: Ctrl+Shift+U, hex code, Space, wrapped in PAUSE.
    """
    keysyms = _keysym_map(layout, variant, options)
    if keysyms is None:
        return None
    lib = _lib()
    altgr_code = keysyms[-1][0]
    out: list[str] = []

    def press(code: int, use_shift: bool = False, use_l3: bool = False) -> None:
        mods = ([_KEY_LEFTSHIFT] if use_shift else []) + ([altgr_code] if use_l3 else [])
        out.extend([f"{m}:1" for m in mods] + [f"{code}:1", f"{code}:0"] + [f"{m}:0" for m in reversed(mods)])

    for ch in text:
        if ch == "\n":
            # Shift+Enter: a line break that doesn't send in chat apps.
            out += [f"{_KEY_LEFTSHIFT}:1", f"{_KEY_ENTER}:1", f"{_KEY_ENTER}:0", f"{_KEY_LEFTSHIFT}:0"]
            continue
        sym = _KEYSYM_RETURN if ch == "\r" else lib.xkb_utf32_to_keysym(ord(ch))
        entry = keysyms.get(sym) if sym else None
        if entry is not None:
            press(*entry)
            continue
        out += [PAUSE, f"{_KEY_LEFTCTRL}:1", f"{_KEY_LEFTSHIFT}:1", f"{_KEY_U}:1", f"{_KEY_U}:0",
                f"{_KEY_LEFTSHIFT}:0", f"{_KEY_LEFTCTRL}:0"]
        for digit in f"{ord(ch):x}":
            hex_entry = keysyms.get(lib.xkb_utf32_to_keysym(ord(digit)))
            if hex_entry is None:
                return None
            press(*hex_entry)
        press(*keysyms[lib.xkb_utf32_to_keysym(ord(" "))])
        out.append(PAUSE)
    return out


def _parse_source(raw: str) -> tuple[str, str] | None:
    """gsettings input-sources value -> (layout, variant) of the first xkb source."""
    raw = raw.strip()
    if raw.startswith("@"):
        raw = raw.split(" ", 1)[1]
    try:
        sources = ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        return None
    if not sources or sources[0][0] != "xkb":
        return None
    layout, _, variant = sources[0][1].partition("+")
    return layout, variant


def gnome_layout() -> tuple[str, str, str] | None:
    """Active GNOME keyboard layout as (layout, variant, options), or None."""
    def get(key: str) -> str:
        return subprocess.run(["gsettings", "get", "org.gnome.desktop.input-sources", key],
                              capture_output=True, text=True, check=True).stdout
    try:
        # mru-sources[0] is the active source once the user has switched; else sources[0].
        src = _parse_source(get("mru-sources")) or _parse_source(get("sources"))
        if src is None:
            return None
        opts = ast.literal_eval(get("xkb-options").strip().removeprefix("@as "))
    except (OSError, subprocess.CalledProcessError, ValueError, SyntaxError):
        return None
    return src[0], src[1], ",".join(opts)

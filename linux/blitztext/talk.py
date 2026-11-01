import json
import re
import subprocess
import time
import urllib.error
import urllib.request

import shutil
import os

from . import tts

def _read_clip(primary=False):
    if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
        cmd = ["wl-paste", "-p"] if primary else ["wl-paste"]
        if shutil.which(cmd[0]):
            try:
                return subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
            except Exception:
                pass
    if shutil.which("xclip"):
        cmd = ["xclip", "-o", "-selection", "primary" if primary else "clipboard"]
        try:
            return subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
        except Exception:
            pass
    if shutil.which("xsel"):
        cmd = ["xsel", "-o", "--primary" if primary else "--clipboard"]
        try:
            return subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
        except Exception:
            pass
    return b""

def _write_clip(data):
    if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
        if shutil.which("wl-copy"):
            try:
                subprocess.run(["wl-copy"], input=data, stderr=subprocess.DEVNULL)
                return
            except Exception:
                pass
    if shutil.which("xclip"):
        try:
            subprocess.run(["xclip", "-selection", "clipboard", "-i"], input=data, stderr=subprocess.DEVNULL)
            return
        except Exception:
            pass
    if shutil.which("xsel"):
        try:
            subprocess.run(["xsel", "--clipboard", "--input"], input=data, stderr=subprocess.DEVNULL)
            return
        except Exception:
            pass

def get_selected_text():
    # 1. Save old clipboard
    old_clip = _read_clip(primary=False)
    
    # 2. Clear clipboard to detect when ctrl+c succeeds
    _write_clip(b"")

    # 3. Wait for physical keys to be released
    time.sleep(0.4)
    
    # 4. Simulate Ctrl+C via xdotool/wtype (pynput crashes with BadRRModeError on some X11 configs).
    # Do not explicitly key up the global modifiers here: that changes the
    # desktop state without necessarily producing matching release events for
    # pynput's listeners. In particular, it can leave the Ctrl+Super modifier
    # scheme stuck after TTS runs. --clearmodifiers handles the synthetic copy
    # without desynchronizing the listeners.
    if shutil.which("xdotool"):
        subprocess.run(['xdotool', 'key', '--clearmodifiers', 'ctrl+c'], stderr=subprocess.DEVNULL)
    elif shutil.which("wtype"):
        subprocess.run(['wtype', '-M', 'ctrl', 'c', '-m', 'ctrl'], stderr=subprocess.DEVNULL)
    elif shutil.which("ydotool"):
        subprocess.run(['ydotool', 'key', 'ctrl+c'], stderr=subprocess.DEVNULL)
        
    # 5. Wait for clipboard to populate (poll every 0.05s up to 1 second)
    text = ""
    for _ in range(20):
        time.sleep(0.05)
        clip_data = _read_clip(primary=False)
        if clip_data:
            text = clip_data.decode('utf-8', errors='ignore').strip()
            break

    # 6. Fallback to primary selection if ctrl+c failed (e.g. terminals where ctrl+c is interrupt)
    if not text:
        text = _read_clip(primary=True).decode('utf-8', errors='ignore').strip()

    # 7. Restore old clipboard
    if old_clip:
        _write_clip(old_clip)
        
    return text

# ~1200 chars is ~80 s of speech: far below the server's max-seq-len cap (2048 tokens ~170 s).
MAX_CHUNK_CHARS = 1200

def split_text(text, limit=MAX_CHUNK_CHARS):
    """Split at paragraph/sentence ends only, packing up to `limit` chars.
    A single sentence longer than `limit` stays whole (never cut mid-sentence)."""
    chunks, cur = [], ""
    for para in re.split(r"\n\s*\n", text):
        for sent in re.split(r"(?<=[.!?…])\s+", para.strip()):
            if not sent:
                continue
            if cur and len(cur) + len(sent) + 1 > limit:
                chunks.append(cur)
                cur = ""
            cur = f"{cur} {sent}" if cur else sent
        # paragraph end: flush if the next paragraph would likely not fit anyway
        if len(cur) > limit * 0.7:
            chunks.append(cur)
            cur = ""
    if cur:
        chunks.append(cur)
    return chunks

def play(cfg, _notify_func):
    text = get_selected_text()
    if not text:
        _notify_func("Blitztalk", "No text selected!", "low")
        return

    preview = text[:40] + "..." if len(text) > 40 else text
    _notify_func("Reading", preview, "normal")

    engine = cfg.active_talk
    if not engine or not engine.url:
        _notify_func("Blitztalk Error", "No TTS engine configured.", "critical")
        return
        
    try:
        url = tts.base_url(engine.url) + "/audio/speech"
        headers = {"Content-Type": "application/json", **tts.auth_headers(engine.api_key_env, engine.url)}
    except RuntimeError as exc:
        _notify_func("Blitztalk Error", str(exc), "critical")
        return

    extra = {}
    if hasattr(engine, "extra_payload") and engine.extra_payload:
        try:
            extra = json.loads(engine.extra_payload)
            if not isinstance(extra, dict):
                extra = {}
        except Exception:
            extra = {}

    # play() already runs in its own thread, so chunks are played sequentially here
    for chunk in split_text(text):
        payload = {
            "model": engine.model or "tts-1",
            "voice": cfg.talk_voice,
            "input": chunk
        }
        payload.update(extra)
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        try:
            with tts.urlopen(req, timeout=60) as response:
                player = subprocess.Popen(
                    ["ffplay", "-nodisp", "-autoexit", "-hide_banner", "-i", "-"],
                    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                try:
                    with player.stdin:
                        shutil.copyfileobj(response, player.stdin)
                    if player.wait(timeout=120):
                        raise RuntimeError("Audio player failed.")
                finally:
                    if player.poll() is None:
                        player.kill()
                        player.wait()
        except urllib.error.HTTPError as exc:
            _notify_func("Blitztalk Error", f"TTS HTTP {exc.code}. Check the endpoint and API key.", "critical")
            return
        except Exception as e:
            _notify_func("Blitztalk Error", "Audio request or playback failed. Check the endpoint and audio player.", "critical")
            return

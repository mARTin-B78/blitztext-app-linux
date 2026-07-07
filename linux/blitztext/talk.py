import json
import shlex
import subprocess
import time

import shutil
import os

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
    text = _read_clip(primary=True).decode('utf-8').strip()
    if text:
        return text

    old_clip = _read_clip(primary=False)
    
    # Wait for user to release hotkey, otherwise xdotool/wtype might send Shift+Ctrl+C
    time.sleep(0.12)

    if shutil.which("xdotool"):
        subprocess.run(['xdotool', 'key', '--clearmodifiers', 'ctrl+c'], stderr=subprocess.DEVNULL)
    elif shutil.which("wtype"):
        subprocess.run(['wtype', '-M', 'ctrl', 'c', '-m', 'ctrl'], stderr=subprocess.DEVNULL)
    elif shutil.which("ydotool"):
        subprocess.run(['ydotool', 'key', 'ctrl+c'], stderr=subprocess.DEVNULL)
    
    time.sleep(0.15)

    text = _read_clip(primary=False).decode('utf-8').strip()

    if old_clip:
        _write_clip(old_clip)
        
    return text

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
        
    url = engine.url
    if not url.endswith("/audio/speech"):
        if url.endswith("/v1"):
            url = url + "/audio/speech"
        else:
            url = url.rstrip("/") + "/v1/audio/speech"

    payload = {
        "model": engine.model or "tts-1",
        "voice": cfg.talk_voice,
        "input": text
    }
    
    if hasattr(engine, "extra_payload") and engine.extra_payload:
        try:
            extra = json.loads(engine.extra_payload)
            if isinstance(extra, dict):
                payload.update(extra)
        except Exception:
            pass
    
    payload_json = json.dumps(payload)
    safe_payload = shlex.quote(payload_json)
    
    cmd = f"curl -s -N {url} -H 'Content-Type: application/json' -d {safe_payload} | ffplay -nodisp -autoexit -hide_banner -i - > /dev/null 2>&1"
    
    try:
        subprocess.Popen(cmd, shell=True)
    except Exception as e:
        _notify_func("Blitztalk Error", f"Error playing audio: {e}", "critical")

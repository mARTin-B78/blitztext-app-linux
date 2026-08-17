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
    # 1. Save old clipboard
    old_clip = _read_clip(primary=False)
    
    # 2. Clear clipboard to detect when ctrl+c succeeds
    _write_clip(b"")

    # 3. Wait for physical keys to be released
    time.sleep(0.4)
    
    # 4. Simulate Ctrl+C via xdotool/wtype (pynput crashes with BadRRModeError on some X11 configs)
    if shutil.which("xdotool"):
        subprocess.run(['xdotool', 'keyup', 'Control_L', 'Control_R', 'Alt_L', 'Alt_R', 'Shift_L', 'Shift_R', 'Super_L', 'Super_R'], stderr=subprocess.DEVNULL)
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
    
    curl_cmd = [
        "curl", "-s", "-N", url,
        "-H", "Content-Type: application/json",
        "-d", payload_json
    ]

    ffplay_cmd = [
        "ffplay", "-nodisp", "-autoexit", "-hide_banner", "-i", "-"
    ]
    
    try:
        curl_proc = subprocess.Popen(curl_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        subprocess.Popen(ffplay_cmd, stdin=curl_proc.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if curl_proc.stdout:
            curl_proc.stdout.close()
    except Exception as e:
        _notify_func("Blitztalk Error", f"Error playing audio: {e}", "critical")

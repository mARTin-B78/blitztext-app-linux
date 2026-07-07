import re

with open("linux/blitztext/gtksettings.py", "r") as f:
    content = f.read()

# 1. Update _build_talk components
talk_ui = """        self.talk_name = _labeled(card, "Name", _entry(placeholder="Local TTS"), tooltip="A short name for this TTS engine.")
        self.talk_url = _url_field_lb(card, "URL", "http://localhost:8023/v1",
                                      on_reload=self._talk_reload,
                                      tooltip="Base URL for the TTS engine. Click the refresh button to load models & voices.")
        self.talk_api_key_env = _labeled(card, "API Key Env", _entry(placeholder="OPENAI_API_KEY"), tooltip="Environment variable holding the API key.")
        self.talk_model = _labeled(card, "Model", _model_combo("tts-1"), tooltip="TTS model ID.")

        # Voice & Trigger Card
        vcard = _card_section(page, "Playback", icon="audio-speakers-symbolic")
        self.talk_voice = _labeled(vcard, "Voice", _model_combo("DE_M_Privat_mARTin"), tooltip="The ID of the voice to use.")
        self.talk_hotkey = self._key_field_lb(vcard, "Hotkey", "", placeholder="click Set, or e.g. <ctrl>+<alt>+t")"""

content = re.sub(
    r'        self\.talk_name = _labeled\(card, "Name", _entry\(placeholder="Local TTS"\).*?'
    r'self\.talk_hotkey = self\._key_field_lb\(vcard, "Hotkey", "", placeholder="click Set, or e\.g\. <ctrl>\+<alt>\+t"\)',
    talk_ui, content, flags=re.DOTALL
)

# 2. Update _talk_load and _talk_commit
load_commit = """    def _talk_load(self, idx: int) -> None:
        if not (0 <= idx < len(self.cfg.talk_engines)):
            return
        e = self.cfg.talk_engines[idx]
        self.talk_name.set_text(e.name)
        self.talk_url.set_text(e.url)
        self.talk_api_key_env.set_text(e.api_key_env)
        _fill_combo(self.talk_model, [], e.model)
        _fill_combo(self.talk_voice, [], self.cfg.talk_voice)
        self.talk_hotkey.set_text(self.cfg.talk_hotkey)
        self.talk_active_btn.set_sensitive(self.cfg.talk_active != e.name)
        self.talk_active_btn.set_label("Default Engine" if self.cfg.talk_active == e.name else "Make Default")
        self._talk_idx = idx

        # optionally prepopulate combos in background
        if e.url:
            self._talk_populate_combos(e.url, e.api_key_env, e.model, self.cfg.talk_voice)

    def _talk_commit(self) -> None:
        idx = self._talk_idx
        if not (0 <= idx < len(self.cfg.talk_engines)):
            return
        e = self.cfg.talk_engines[idx]
        old_name = e.name
        e.name = self.talk_name.get_text().strip() or e.name
        e.url = self.talk_url.get_text().strip()
        e.api_key_env = self.talk_api_key_env.get_text().strip()
        e.model = _combo_text(self.talk_model)
        self.cfg.talk_voice = _combo_text(self.talk_voice)
        self.cfg.talk_hotkey = self.talk_hotkey.get_text().strip()
        if self.cfg.talk_active == old_name:
            self.cfg.talk_active = e.name
        self.talk_combo.remove(idx)
        self.talk_combo.insert_text(idx, e.name)
        self.talk_combo.set_active(idx)

    def _talk_reload(self) -> None:
        url = self.talk_url.get_text().strip().rstrip("/")
        key = self.talk_api_key_env.get_text().strip()
        if not url:
            self._error("Enter a URL first.")
            return
        self._talk_populate_combos(url, key, _combo_text(self.talk_model), _combo_text(self.talk_voice))

    def _talk_populate_combos(self, url: str, key_env: str, current_model: str, current_voice: str) -> None:
        def work():
            try:
                from . import stt, wakeword_bench
                models = stt.list_models(url, key_env)
                voices = wakeword_bench.list_voices(url, api_key_env=key_env)
                voices_set = set(voices)
                real_models = [m for m in models if m not in voices_set]
                def apply():
                    if real_models:
                        _fill_combo(self.talk_model, real_models, current_model)
                    if voices:
                        _fill_combo(self.talk_voice, voices, current_voice)
                GLib.idle_add(apply)
            except Exception as e:
                pass
        import threading
        threading.Thread(target=work, daemon=True).start()"""

content = re.sub(
    r'    def _talk_load\(self, idx: int\) -> None:.*?'
    r'        self\.talk_combo\.set_active\(idx\)',
    load_commit, content, flags=re.DOTALL
)

with open("linux/blitztext/gtksettings.py", "w") as f:
    f.write(content)

print("Patched talk UI components")

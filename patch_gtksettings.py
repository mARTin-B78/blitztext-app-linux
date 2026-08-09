import re

with open("linux/blitztext/gtksettings.py", "r") as f:
    content = f.read()

# 1. Register the tab in __init__
reg_talk = """        _reg("Engines",     "STT Engines",          "network-server-symbolic",           self._build_stt_engines)
        _reg(None,          "LLM Engines",          "applications-science-symbolic",     self._build_llm_engines)
        _reg(None,          "TTS Engines (Talk)",   "audio-speakers-symbolic",           self._build_talk)"""
content = re.sub(r'        _reg\("Engines",     "STT Engines".*\n        _reg\(None,          "LLM Engines".*', reg_talk, content)

# 2. Add _build_talk
build_talk = """
    # ===== TTS Engines (Talk) ===============================================
    def _build_talk(self, page: Gtk.Box) -> None:
        _infobox(page, "Configure Text-To-Speech (TTS) engines for reading selected text aloud. "
                       "Highlight text in any application and press your hotkey to hear it read.")

        self._talk_idx = 0

        # Selector bar
        bar = Gtk.Box(spacing=8)
        bar.set_margin_bottom(6)
        self.talk_combo = _block_scroll(Gtk.ComboBoxText())
        for e in self.cfg.talk_engines:
            self.talk_combo.append_text(e.name)
        self.talk_combo.set_active(0)
        self.talk_combo.connect("changed", self._talk_changed)
        bar.pack_start(self.talk_combo, True, True, 0)

        add = Gtk.Button(label="+ Add")
        add.connect("clicked", self._talk_add)
        rm = Gtk.Button(label="Delete")
        rm.connect("clicked", self._talk_delete)
        bar.pack_start(add, False, False, 0)
        bar.pack_start(rm, False, False, 0)
        page.pack_start(bar, False, False, 0)

        # Engine Card
        card = _card_section(page, "Engine config", margin_top=4, icon="network-server-symbolic")
        self.talk_name = _labeled(card, "Name", _entry(placeholder="Local TTS"), tooltip="A short name for this TTS engine.")
        self.talk_url = _labeled(card, "URL", _entry(placeholder="http://localhost:8023/v1"), tooltip="Base URL for the TTS engine. e.g. http://localhost:8023/v1")
        self.talk_api_key_env = _labeled(card, "API Key Env", _entry(placeholder="OPENAI_API_KEY"), tooltip="Environment variable holding the API key.")
        self.talk_model = _labeled(card, "Model", _entry(placeholder="tts-1"), tooltip="TTS model ID.")

        # Voice & Trigger Card
        vcard = _card_section(page, "Playback", icon="audio-speakers-symbolic")
        self.talk_voice = _labeled(vcard, "Voice", _entry(placeholder="DE_M_Privat_mARTin"), tooltip="The ID of the voice to use.")
        self.talk_hotkey = self._key_field_lb(vcard, "Hotkey", "", placeholder="click Set, or e.g. <ctrl>+<alt>+t")

        self.talk_active_btn = Gtk.Button(label="Make Default")
        self.talk_active_btn.get_style_context().add_class("suggested-action")
        self.talk_active_btn.connect("clicked", self._talk_make_active)
        vcard.pack_start(self.talk_active_btn, False, False, 10)

        self._talk_load(0)

    def _talk_load(self, idx: int) -> None:
        if not (0 <= idx < len(self.cfg.talk_engines)):
            return
        e = self.cfg.talk_engines[idx]
        self.talk_name.set_text(e.name)
        self.talk_url.set_text(e.url)
        self.talk_api_key_env.set_text(e.api_key_env)
        self.talk_model.set_text(e.model)
        self.talk_voice.set_text(self.cfg.talk_voice)
        self.talk_hotkey.set_text(self.cfg.talk_hotkey)
        self.talk_active_btn.set_sensitive(self.cfg.talk_active != e.name)
        self.talk_active_btn.set_label("Default Engine" if self.cfg.talk_active == e.name else "Make Default")
        self._talk_idx = idx

    def _talk_commit(self) -> None:
        idx = self._talk_idx
        if not (0 <= idx < len(self.cfg.talk_engines)):
            return
        e = self.cfg.talk_engines[idx]
        old_name = e.name
        e.name = self.talk_name.get_text().strip() or e.name
        e.url = self.talk_url.get_text().strip()
        e.api_key_env = self.talk_api_key_env.get_text().strip()
        e.model = self.talk_model.get_text().strip()
        self.cfg.talk_voice = self.talk_voice.get_text().strip()
        self.cfg.talk_hotkey = self.talk_hotkey.get_text().strip()
        if self.cfg.talk_active == old_name:
            self.cfg.talk_active = e.name
        self.talk_combo.remove(idx)
        self.talk_combo.insert_text(idx, e.name)
        self.talk_combo.set_active(idx)

    def _talk_changed(self, combo) -> None:
        new = combo.get_active()
        if new < 0 or new == self._talk_idx:
            return
        self._talk_commit()
        self._talk_load(new)

    def _talk_add(self, _b) -> None:
        self._talk_commit()
        from .config import TTSEngine
        e = TTSEngine(name="New TTS")
        self.cfg.talk_engines.append(e)
        self.talk_combo.append_text(e.name)
        self.talk_combo.set_active(len(self.cfg.talk_engines) - 1)
        self._talk_load(len(self.cfg.talk_engines) - 1)

    def _talk_delete(self, _b) -> None:
        if len(self.cfg.talk_engines) <= 1:
            return
        idx = self._talk_idx
        name = self.cfg.talk_engines[idx].name
        del self.cfg.talk_engines[idx]
        if self.cfg.talk_active == name:
            self.cfg.talk_active = self.cfg.talk_engines[0].name
        self.talk_combo.remove(idx)
        self._talk_idx = -1
        self.talk_combo.set_active(0)
        self._talk_load(0)

    def _talk_make_active(self, _b) -> None:
        idx = self._talk_idx
        if 0 <= idx < len(self.cfg.talk_engines):
            self.cfg.talk_active = self.cfg.talk_engines[idx].name
            self.talk_active_btn.set_sensitive(False)
            self.talk_active_btn.set_label("Default Engine")

    # ===== LLM Engines ======================================================
"""
content = re.sub(r'    # ===== LLM Engines ======================================================', build_talk, content)

# 3. Add to _collect()
collect_talk = """        self._force_build_tabs()
        if getattr(self, "_talk_idx", -1) >= 0:
            self._talk_commit()"""
content = re.sub(r'        self._force_build_tabs\(\)', collect_talk, content)

with open("linux/blitztext/gtksettings.py", "w") as f:
    f.write(content)

print("Patched gtksettings.py")

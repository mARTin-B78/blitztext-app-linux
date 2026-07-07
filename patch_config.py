import sys
import re

with open("linux/blitztext/config.py", "r") as f:
    content = f.read()

# 1. Add TTSEngine after LLMEngine
tts_engine_class = """
@dataclass
class TTSEngine:
    name: str
    url: str = "http://localhost:8023/v1"
    model: str = "tts-1"
    api_key_env: str = ""
"""
content = re.sub(r'(@dataclass\nclass WakewordEngine:)', r'@dataclass\nclass TTSEngine:\n    name: str\n    url: str = "http://localhost:8023/v1"\n    model: str = "tts-1"\n    api_key_env: str = ""\n\n\1', content)

# 2. Add Config fields
config_fields = """    # workflows
    workflows: list[Workflow] = field(default_factory=list)
    # blitztalk
    talk_engines: list[TTSEngine] = field(default_factory=list)
    talk_active: str = ""
    talk_voice: str = "DE_M_Privat_mARTin"
    talk_hotkey: str = "<ctrl>+<alt>+t"

    @property
    def active_talk(self) -> TTSEngine:
        e = next((x for x in self.talk_engines if x.name == self.talk_active), None)
        if e:
            return e
        if self.talk_engines:
            return self.talk_engines[0]
        return TTSEngine("Default", "http://localhost:8023/v1", "tts-1")"""
content = re.sub(r'    # workflows\n    workflows: list\[Workflow\] = field\(default_factory=list\)', config_fields, content)

# 3. Add to load()
load_init = """        bench_expand_models=bool(data.get("benchmark", {}).get("expand_models", False)),
        bench_last=dict(data.get("benchmark", {}).get("last", {})),
        talk_voice=data.get("talk", {}).get("voice", "DE_M_Privat_mARTin"),
        talk_hotkey=data.get("talk", {}).get("hotkey", "<ctrl>+<alt>+t"),"""
content = re.sub(r'        bench_expand_models=bool\(data\.get\("benchmark", \{\}\)\.get\("expand_models", False\)\),\n        bench_last=dict\(data\.get\("benchmark", \{\}\)\.get\("last", \{\}\)\),', load_init, content)

load_engines = """    cfg.llm_active = data.get("llm", {}).get("active", cfg.llm_engines[0].name)

    cfg.talk_engines = [
        TTSEngine(
            name=e["name"],
            url=e.get("url", "http://localhost:8023/v1").rstrip("/"),
            model=e.get("model", "tts-1"),
            api_key_env=e.get("api_key_env", ""),
        )
        for e in data.get("talk_engine", [])
    ] or [TTSEngine("Local TTS", "http://localhost:8023/v1", "tts-1")]
    cfg.talk_active = data.get("talk", {}).get("active", cfg.talk_engines[0].name)"""
content = re.sub(r'    cfg\.llm_active = data\.get\("llm", \{\}\)\.get\("active", cfg\.llm_engines\[0\]\.name\)', load_engines, content)

# 4. Add to save()
save_dict = """        "llm_engine": [
            {"name": e.name, "type": e.type, "url": e.url, "model": e.model,
             "api_key_env": e.api_key_env, "temperature": e.temperature}
            for e in cfg.llm_engines
        ],
        "talk": {
            "active": cfg.talk_active,
            "voice": cfg.talk_voice,
            "hotkey": cfg.talk_hotkey,
        },
        "talk_engine": [
            {"name": e.name, "url": e.url, "model": e.model, "api_key_env": e.api_key_env}
            for e in cfg.talk_engines
        ],"""
content = re.sub(r'        "llm_engine": \[\n            \{"name": e\.name, "type": e\.type, "url": e\.url, "model": e\.model,\n             "api_key_env": e\.api_key_env, "temperature": e\.temperature\}\n            for e in cfg\.llm_engines\n        \],', save_dict, content)

with open("linux/blitztext/config.py", "w") as f:
    f.write(content)

print("Patched config.py")

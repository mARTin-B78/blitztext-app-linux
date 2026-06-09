"""Blitztext for Linux — native dictation daemon.

Press a global hotkey, speak, and the transcribed (optionally LLM-rewritten)
text is typed into whatever text field currently has focus. This is the Linux
counterpart to the macOS Blitztext menu bar app: it runs natively on the host
(not in a container) so it can type into any application via xdotool.
"""

__version__ = "2.1.2"

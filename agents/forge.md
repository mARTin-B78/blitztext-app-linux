# 📦 Forge Agent

**Concern:** Installer / packaging
**Cadence:** Weekly
**Output:** PR

## Directives
- Maintain the Debian packaging (`.deb`), `install-linux.sh`, and related build scripts.
- Ensure the installer is reproducible and verifiable on a clean VM.
- Keep `.deb` maintainer scripts (`postinst`, `postrm`) minimal, as they run as root.

# FeedForge converter

Python conversion and FeedPak processing used by the FeedForge desktop app.

From the repository root, install with `python -m pip install "./converter[dev]"`.
Run `psarc2feedpak --help` for command-line options. Optional stem separation
dependencies can be installed with `python -m pip install "./converter[stems]"`.

Build the bundled converter with `npm --prefix desktop run converter:pack`.
The desktop application, downloads, and support links are described in the
[project README](../README.md).

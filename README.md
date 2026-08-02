<p align="center">
  <img src="assets/feedforge.png" alt="FeedForge" width="96" />
</p>

<h1 align="center">FeedForge</h1>

<p align="center">
  FeedBack song toolkit for Windows, macOS, and Linux.
</p>

<p align="center">
  <a href="https://github.com/balki97/FeedForge/releases/latest"><strong>Download</strong></a>
  &nbsp;|&nbsp;
  <a href="https://feedforge.org">Website</a>
  &nbsp;|&nbsp;
  <a href="https://discord.gg/9cUe6cacQN">Discord</a>
</p>

---

## Download

Download the Windows x64 portable EXE, macOS Apple Silicon DMG/ZIP, or Linux
x64 AppImage from the latest release:

https://github.com/balki97/FeedForge/releases/latest

## macOS / Linux desktop apps

The desktop build workflow produces all three releases. They bundle the
converter, native WEM decoder, OGG encoder, and DDS cover decoder, so normal
PSARC-to-FeedPak conversion does not require Python, Homebrew, FFmpeg, or other
system tools.

The macOS build is not notarized yet. On first launch, right-click FeedForge,
choose **Open**, then confirm. Linux users may need to run
`chmod +x FeedForge-*.AppImage` before the first launch.

Local stem splitting remains optional and installs its own environment from a
system Python 3.11 or newer. Remote stem servers work without local Python.

Maintainers can run the cross-platform build from GitHub Actions, or build on the
target operating system with `npm run release:mac` or `npm run release:linux`.

## macOS / Linux CLI

The Python CLI runs on Python 3.11 or newer. WEM audio conversion also needs
`vgmstream-cli` available on `PATH`; FeedForge handles OGG encoding itself.

On macOS, or Linux with Homebrew, install the required decoder with:

```bash
brew install vgmstream
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
psarc2feedpak song.psarc
```

On other Linux systems, get `vgmstream-cli` from
[vgmstream](https://vgmstream.org), then follow the same Python commands above.

## Support

For bug reports, include the debug log:

```text
Windows: %APPDATA%\FeedForge\logs\feedforge-debug.log
macOS:   ~/Library/Application Support/FeedForge/logs/feedforge-debug.log
Linux:   ~/.config/FeedForge/logs/feedforge-debug.log
```

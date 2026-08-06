<p align="center">
  <img src="assets/feedforge.png" alt="FeedForge" width="96" />
</p>

<h1 align="center">FeedForge</h1>

<p align="center">
  A desktop toolkit for FeedPak files for the FeedBack game.
</p>

<p align="center">
  <a href="https://github.com/balki97/FeedForge/releases/latest"><strong>Download</strong></a>
  &nbsp;|&nbsp;
  <a href="https://feedforge.org">Website</a>
  &nbsp;|&nbsp;
  <a href="https://discord.gg/9cUe6cacQN">Discord</a>
</p>

---

## FeedPak toolkit

FeedForge helps you inspect, validate, edit, organize, and maintain FeedPak
song libraries. It includes package details, metadata and stem tools, library
auditing, duplicate checks, and optional local stem separation.

### Reliable song previews

Converted songs keep Rocksmith's authored preview audio for FeedBack's song
browser. When a source has no usable preview, FeedForge creates a short preview
from the full mix instead. Preview creation is optional, so it cannot prevent an
otherwise playable song from converting.

## Windows, macOS, and Linux

Download the latest Windows x64 portable app, macOS Apple Silicon DMG/ZIP, or
Linux x64 AppImage from the [latest release](https://github.com/balki97/FeedForge/releases/latest).

- **Windows:** Run the portable EXE.
- **macOS:** Open the DMG or ZIP. If macOS blocks the first launch, try opening
  FeedForge once, then use **System Settings → Privacy & Security → Open Anyway**.
  For an official FeedForge download that still reports damage, run
  `xattr -dr com.apple.quarantine "/Applications/FeedForge.app"`.
- **Linux:** Make the AppImage executable with `chmod +x FeedForge-*.AppImage`,
  then run it.

Optional local stem separation requires Python 3.11 or newer.

## Support

For bug reports, include the debug log:

```text
Windows: %APPDATA%\FeedForge\logs\feedforge-debug.log
macOS:   ~/Library/Application Support/FeedForge/logs/feedforge-debug.log
Linux:   ~/.config/FeedForge/logs/feedforge-debug.log
```

## License

FeedForge is available under the [MIT License](LICENSE).

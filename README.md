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

Create FeedPaks from either **Songsterr** links or **Rocksmith / PSARC** files.
Both workflows feed the same Library & editor, package validator, and output folder.
Home provides the source actions and files opened during the current session.

### Songsterr creation

1. Open **From Songsterr**, paste one or more HTTPS tab links, and choose **Read links**.
   Links for different parts of the same song are grouped together.
2. Select guitar, bass, or drum arrangements; edit their names and roles, release
   details, cover art, and synchronized lyrics. You can import an LRC file or use
   **Search again** to retry lyric providers. Advanced options include chart offset.
3. Choose local audio or use the linked video, select an output folder, then create
   one package or the batch. Existing filenames receive a numbered suffix.
4. Review per-song results or open the new packages in **Library & editor** to
   inspect, edit, organize, or manage stems. Batch stop finishes the current song.

Online metadata, artwork, lyrics, and video downloads depend on their providers.
Local audio is available when video downloading fails. Only chartable instrument
types can be selected. Songsterr drafts survive navigation within the session.

See [integration and feature parity](docs/songsterr-integration.md) and
[desktop design](docs/ui-redesign.md) for architecture, verification, and known limits.

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

## Development and packaging

Source lives in `src/` (converter), `electron/` (desktop shell), and `ui/`.
Regression tests live in `tests/`; maintenance and launch scripts live in `tools/`.

Install dependencies with `python -m pip install -e ".[dev]"` and `npm ci`.
Run `npm test` and `npm run build` before packaging.
Use `npm run release:win`, `release:mac`, or `release:linux` for a local release.
Finished downloads are written to `release/`. Successful packaging removes
superseded FeedForge downloads of the same artifact type; failed builds retain
the previous release. `build/`, `dist/`, `desktop-dist/`, and `release/` are
generated and ignored by Git. Keep conversion results in `outputs/` or outside
the repository.

Run `npm run clean -- --dry-run` to preview cleanup, then `npm run clean`
to remove generated build folders, unpacked releases, and Python caches.
Release downloads and `SHA256SUMS.txt` are retained, as are source files,
dependencies, local decoder tools, and conversion outputs.

## License

FeedForge is available under the [MIT License](LICENSE).

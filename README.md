# FeedForge

![FeedForge icon](assets/feedforge.png)

FeedForge is a Windows utility for managing FeedBack-ready `.feedpak` packages
and preparing them from CDLC source files.

It can process one file or a full folder of CDLC files in a batch. It also opens
existing `.feedpak` packages so metadata, cover art, stems, and package details
can be reviewed or updated without going back to the source file.

## Download

Download the portable EXE from the latest GitHub release.

FeedForge checks GitHub releases for newer versions from inside the app.

## Community

Join the FeedForge Discord server for announcements, support, bug reports, and
feature requests:

https://discord.gg/9cUe6cacQN

## Usage

1. Open FeedForge.
2. Add `.psarc` files by browsing, dragging them in, or choosing a folder.
3. Choose an output folder.
4. Choose an output layout: one folder, preserve source folders, or artist folders.
5. Choose output file names: source filename, artist-song, song-artist, or a custom template.
6. Select the number of queue workers.
7. Optional: enable stem separation or B-standard remapping.
8. Start the queue.

The app writes `.feedpak` files that can be added to FeedBack.

Every generated or edited package is checked against the bundled official
FeedPak schemas before FeedForge reports success. Invalid packages are rejected
with validation details instead of being written as completed output. The
validator is included in the portable app and works offline; users do not need
to install Python or any validation tools.

## FeedPak tools

FeedForge can open existing `.feedpak` files to inspect package contents, song
metadata, cover art, arrangements, stems, and tones. Metadata and cover art can
be edited and saved back into the package.

Existing FeedPaks can also be sent through stem separation without using a
source package again.

For troubleshooting or release checks, the packaged CLI can validate an existing
package directly:

```powershell
psarc2feedpak.exe --validate-feedpak "song.feedpak"
```

## Stem splitting

Stem splitting can run locally after FeedForge installs a local Demucs
environment and downloads the selected model. A custom or remote Demucs server
URL can also be used.

The selected model is downloaded once and reused from the chosen stem server
folder. Users can choose which separated stems to include, and FeedForge keeps
the full mix in `stems/full.ogg` for FeedBack compatibility.

## Notes

- Use fewer workers if the PC becomes slow during a large batch.
- `Stop after current` pauses the queue after active files finish.
- Existing output files are skipped unless `Overwrite` is enabled.
- The local stem server install folder stores its Python environment, cache, and
  downloaded Demucs models. Choose a folder on a drive with enough free space.
- Very large libraries are supported through folder import and a limited queue view.
- If processing fails, send `%APPDATA%\FeedForge\logs\feedforge-debug.log`
  with the bug report.

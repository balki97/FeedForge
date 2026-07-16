# FeedForge

![FeedForge icon](assets/feedforge.png)

FeedForge is a Windows tool for converting `.psarc` CDLC packages into
`.feedpak` packages for FeedBack.

It can convert one file or a full folder of CDLC files in a batch. It also opens
existing `.feedpak` packages so metadata, cover art, stems, and package details
can be reviewed or updated without reconverting from source.

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
6. Select the number of conversion workers.
7. Optional: enable stem separation or B-standard remapping.
8. Click `Convert queue`.

The app writes `.feedpak` files that can be added to FeedBack.

## FeedPak tools

FeedForge can open existing `.feedpak` files to inspect package contents, song
metadata, cover art, arrangements, stems, and tones. Metadata and cover art can
be edited and saved back into the package.

Existing FeedPaks can also be sent through stem separation without converting a
`.psarc` again.

## Stem splitting

Stem splitting can run locally after FeedForge installs a local Demucs
environment and downloads the selected model. A custom or remote Demucs server
URL can also be used.

The selected model is downloaded once and reused from the chosen stem server
folder. Users can choose which separated stems to include, and FeedForge keeps
the full mix in `stems/full.ogg` for FeedBack compatibility.

## Notes

- Use fewer workers if the PC becomes slow during a large batch.
- `Stop after current` pauses the queue after active conversions finish.
- Existing output files are skipped unless `Overwrite` is enabled.
- The local stem server install folder stores its Python environment, cache, and
  downloaded Demucs models. Choose a folder on a drive with enough free space.
- Very large libraries are supported through folder import and a limited queue view.
- If a conversion fails, send `%APPDATA%\FeedForge\logs\feedforge-debug.log`
  with the bug report.

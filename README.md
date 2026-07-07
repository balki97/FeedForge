# FeedForge

![FeedForge icon](assets/feedforge.png)

FeedForge is a Windows tool for converting `.psarc` CDLC packages into
`.feedpak` packages for FeedBack.

It can convert one file or a full folder of CDLC files in a batch. During import
it reads song metadata, cover art, arrangements, lyrics, and duration so the
files can be checked before export.

## Download

Download the installer for normal use. The portable EXE is still available, but
it starts slower because Windows has to unpack it before launch.

## Community

Join the FeedForge Discord server for announcements, support, bug reports, and
feature requests:

https://discord.gg/9cUe6cacQN

## Usage

1. Open FeedForge.
2. Add `.psarc` files by browsing, dragging them in, or choosing a folder.
3. Choose an output folder.
4. Select the number of conversion workers.
5. Optional: enable tone export, stem separation, or B-standard remapping.
6. Click `Convert queue`.

The app writes `.feedpak` files that can be added to FeedBack.

## Notes

- Use fewer workers if the PC becomes slow during a large batch.
- `Stop after current` pauses the queue after active conversions finish.
- Existing output files are skipped unless `Overwrite` is enabled.
- Stem separation can use the in-app `Install/start local stem server` button,
  FeedBack's Demucs server setting, or a custom Demucs server URL.
- The local stem server install folder stores its Python environment, cache, and
  downloaded Demucs models. Choose a folder on a drive with enough free space.
- Already downloaded Demucs models are detected in the selected install folder
  and reused on later starts.
- Very large libraries are supported through folder import and a limited queue view.
- If a conversion fails, send `%APPDATA%\FeedForge\logs\feedforge-debug.log`
  with the bug report.

# FeedForge

![FeedForge icon](assets/feedforge.png)

FeedForge is a Windows tool for converting `.psarc` CDLC packages into
`.feedpak` packages for FeedBack.

It can convert one file or a full folder of CDLC files in a batch. During import
it reads song metadata, cover art, arrangements, lyrics, and duration so the
files can be checked before export.

## Download

Download `FeedForge 0.1.0.exe` from the latest GitHub release.

## Community

Join the FeedForge Discord server for announcements, support, bug reports, and
feature requests:

https://discord.gg/9cUe6cacQN

## Usage

1. Open FeedForge.
2. Add `.psarc` files by browsing, dragging them in, or choosing a folder.
3. Choose an output folder.
4. Select the number of conversion workers.
5. Click `Convert queue`.

The app writes `.feedpak` files that can be added to FeedBack.

## Notes

- Use fewer workers if the PC becomes slow during a large batch.
- `Stop after current` pauses the queue after active conversions finish.
- Existing output files are skipped unless `Overwrite` is enabled.
- Very large libraries are supported through folder import and a limited queue view.

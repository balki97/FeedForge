<p align="center">
  <img src="desktop/assets/feedforge.png" alt="FeedForge" width="96" />
</p>

<h1 align="center">FeedForge</h1>

<p align="center">Create and edit songs for FeedBack.</p>

<p align="center">
  <a href="https://github.com/balki97/FeedForge/releases/latest"><strong>Download</strong></a>
  &nbsp;|&nbsp;
  <a href="https://feedforge.org">Website</a>
  &nbsp;|&nbsp;
  <a href="https://discord.gg/9cUe6cacQN">Discord</a>
</p>

## What it does

- Convert PSARC files into FeedPaks.
- Create songs from Songsterr links, with guitar, bass, and drum parts.
- Add difficulty levels to guitar and bass charts that don't have them. Existing DD is preserved.
- Split audio into instrument stems.
- Edit song details, artwork, and lyrics. Check your library for issues and duplicates.

## Getting started

Download your version from [Releases](https://github.com/balki97/FeedForge/releases/latest):

- **Windows:** Run the portable EXE.
- **macOS (Apple Silicon):** Open the DMG and drag FeedForge into Applications.
- **Linux:** Make the AppImage executable, then open it.

Open a PSARC file or paste a Songsterr link, choose an output folder, and convert.
You can also open existing FeedPaks in **Library & editor**.

For separate instrument stems, set up the local server in **Tools > Stems**, then
turn on stem splitting in **Settings**. Local stem splitting requires Python 3.11
or newer. You can convert without it using the full mix.

## Help

Join [Discord](https://discord.gg/9cUe6cacQN) or
[report an issue](https://github.com/balki97/FeedForge/issues).
Include your FeedForge version, operating system, and the error message.
Debug logs are available from **Diagnostics** in the app.

## License

[MIT](LICENSE)

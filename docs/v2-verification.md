# 2.0.0 release checks

## Local Windows checks, September 18, 2026

- 120 Python tests, seven Node test entries and lyric checks pass.
- The production UI builds; Electron main/preload syntax and scoped diff checks pass.
- Real PSARC: Dire Straits / Walk of Life, 252.22 seconds, valid package with audio,
  cover, arrangements, tones and lyrics. Full-mix-only conversion passes.
- Real Songsterr: Deftones / Root, freshly fetched chart and video audio, three
  arrangements and 32 timed lyric lines. Download fallback recovered from initial
  HTTP 403 responses. The resulting 220.83-second audio is non-silent.
- The Windows stem launcher refreshed the existing environment and loaded
  htdemucs_6s on an RTX 4060 Ti. Full-song PSARC conversion through the native UI
  and Songsterr creation through the shared backend both produced guitar, bass,
  drums, vocals and other, plus the retained full mix. No separation warnings.
- Every produced stem was decoded and checked for duration and nonzero RMS.
  Full mix defaults off in separated packages; split stems default on.
- Real package copy editing preserves every non-manifest archive member byte for
  byte. Metadata, author editing, audio export and stem removal pass.
- The 2.0.0 PyInstaller backend reports the correct version and creates a valid
  Songsterr package through the desktop JSON contract.
- Native UI checks: simple Home, aligned version, no-stems warning, setup routing,
  ready-server confirmation, and completed PSARC conversion. Test source files
  are copies and the desktop uses an isolated QA profile.

Raw local evidence is in ignored `outputs/v2-verification/` and `outputs/v2-qa/logs/`.
The previous backend and portable app remain available as recovery artifacts.

## Scope

Automated tests cover additional editor, validator, output naming, RS1, multi-song,
batch cancellation, temporary-file cleanup and conversion scheduler paths.
This is not a claim that every possible community song or online provider works.
The Windows environment and model cache existed before this run; this verifies
upgrade/startup and real inference, not a fresh operating-system installation.
FeedBack gameplay and native macOS/Linux interaction require those environments.

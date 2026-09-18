# Unified FeedForge integration

## Baseline and safety gate (2026-09-18)

Confirmed the primary checkout by its origin (`balki97/FeedForge`), version
0.1.44 and clean Git status. Work branch: `feature/unified-songsterr-feedforge`.
The reference is Songsterr Creator 0.3.2; its untracked source must remain untouched.
No UI or backend implementation changes preceded this inventory.

| Baseline command | Result |
| --- | --- |
| FeedForge `npm test` | 87 Python tests; 2 Node tests passed |
| FeedForge `npm run build` | Vite production build passed |
| Creator `python -B -m pytest -q -p no:cacheprovider` | 86 passed (23 application tests + 63 local specification tests) |
| Creator `node test_core_response.cjs` and `node test_lyrics.mjs` | Passed |
| Creator Vite build with external output directory | Passed; reference output untouched |

Neither project has a separate type checker or real lint configuration. FeedForge
`lint:ui` is another Vite build. Packaging and interactive verification are recorded below.

## Architecture inventory

Both desktops use Electron 43, React 19, Vite 6, Lucide, JavaScript and Python 3.
Both isolate the renderer and use named preload methods and subprocess JSON.
FeedForge owns a PSARC/FeedPak CLI, schema validator, batch planner, output naming,
tone/equipment catalogs, and optional FastAPI Demucs service. Its large React App
owns queue/settings state; localStorage key `feedforge:desktop-settings` must survive.
Electron owns native dialogs, inspection cache, process management, library audit,
logging/redaction, update checks, and temporary JSON requests. Python owns conversion.
Native decoders include vgmstream, ww2ogg, oggenc and topng with portable fallbacks.
Optional stems use PyTorch/Demucs, local installation scripts or a remote HTTP service.
Environment: VITE_DEV_SERVER_URL, FEEDFORGE_DEMUCS_URL, DEMUCS_SERVER_URL,
CONFIG_DIR, APPDATA and platform home/program paths. API keys are session-only.
PyInstaller produces psarc2feedpak; electron-builder produces portable Windows,
macOS DMG/ZIP and Linux AppImage. Generated build/dist/release/cache paths are ignored.

Creator has one conversion module, creator_cli JSON bridge, a React editor, and an
older Tk application. React state is transient; neither UI persists user preferences.
Desktop defaults choose the desktop output directory. No credentials are embedded.
Dependencies unique to Creator: yt-dlp, yt-dlp-getpot-wpc, imageio-ffmpeg;
Pillow/PyYAML and every Node runtime dependency already exist in FeedForge.
Creator downloads HTML state, revision-specific track JSON from three CDN mirrors,
and video-points JSON. It uses MusicBrainz/Cover Art Archive for release metadata,
LRCLIB then video captions/secondary catalog for lyrics. Network requests have 30s
timeouts; audio has format/client fallbacks and retries. SONGSTERR_NODE_PATH locates
the JS runtime. Audio is local or YouTube, transcoded to Vorbis by bundled FFmpeg.
Its temp dirs are independent; cleanup is currently silent. There is no search API,
dynamic difficulty generation, piano chart or vocal-note conversion. Lyrics are supported.

## Feature parity / integration matrix

Final status distinguishes preserved implementation/regression coverage from live checks.
Retained means no feature was removed; it does not imply every external service or OS
was exercised. Migrated means the feature is available inside FeedForge.
FF frontend is ui/src/main.jsx unless specified; backend names are source files.

| Capability | FeedForge evidence / boundary | Creator evidence / boundary | Target / strategy | Status |
| --- | --- | --- | --- | --- |
| PSARC single/multisong and RS1 shared audio | converter.py, psarc_format, converter:convert | — | Preserve parser/options | Retained; 87 baseline tests + live PSARC output |
| Batch planning, collision names, layouts, templates | batch.py, output_naming.py, converter:planConversions | filename helper | Preserve FF; safe Creator names | Retained; naming/planning regression tests; collision tests |
| Queue concurrency, stop-after-current, planning cancel | conversion-scheduler.mjs; converter IPC | sequential batch continues on failure | Preserve both policies | Retained; scheduler regressions + batch stop test |
| Drag/drop, files/folders, recursive imports | preload, files:expandPaths, dialogs | pasted links | Common shell | Retained; packaged recursive folder import verified |
| Inspection, schemas, validation reports | inspector.py, feedpak.py, feedpak_validator.py | writer only; tests validate wire | Shared canonical validator | Shared; synthetic + live PSARC/Songsterr validation |
| Metadata, authors, language, cover replace/remove | feedpak:update | editable release/year/charter; cover restore/remove | Creation + shared editor | Migrated/shared; roundtrip tests + live Save copy |
| Audio export, fallback WAV/OGG | converter:exportAudio | local audio or synced YouTube | Preserve both | Retained/migrated; real PSARC decode + local WAV conversion; video fallback mocks |
| Stem replace/remove, full-mix protection, batch reprocess | feedpak:update | full Vorbis stem | Shared editor | Retained; editor tests; UI reachable |
| Local/remote stems, models/devices/concurrency, install/Python/port tools | stemServer:*; demucs_server.py | — | Preserve Tools | Retained; launcher tests; full model inference not rerun |
| Library artist organization | feedpak:organize | — | Preserve | Retained; original organization service and controls |
| Audit criteria, duplicates/scoring, JSON/CSV reports | audit:* | — | Library + diagnostics | Retained; packaged audit verified (see log) |
| Queue status/artist/album/tuning filters | React Queue | sorted songs/grouped links | Preserve + library search | Retained; shared filtering + original queue controls |
| Delete/reveal files, output selection | files:* and dialog:* | reveal/output dialogs | Shared native services | Retained; native folder/output dialogs verified |
| Rigs, equipment images/knobs, timeline, B-standard seven-string | converter.py; ToneInspector | no generated rigs | Preserve PSARC semantics | Retained; existing conversion/tone regressions |
| Logs, renderer failures, version/update/support links | app:*, updates:* | website/Discord/support | One shell | Retained; packaged diagnostics/logs verified |
| Settings persistence | desktop-settings localStorage | no persisted settings | Keep key and fields | Retained; restart verified with isolated QA profile |
| Link parsing, duplicate grouping, multisong batch | — | inspect/load_songsterr; analyze/create/batch | Source workflow | Migrated; link/part tests + live analysis |
| Revision/CDN retrieval, video points and metadata | — | _page_state/_download_part/_main_video | Preserve requests/fallbacks | Migrated; source logic preserved + live retrieval |
| Arrangement selection, names, lead/rhythm/combo/bass/drums | — | load_songsterr_selection, roles | Source editor | Migrated; 3-part live output + name/role tests |
| Tuning/capo, MIDI/string orientation | PSARC tuning | _tuning/part_to_arrangement | Preserve source mappings | Migrated; original conversion logic and regressions |
| Repeats, fractions, meter/tempo ramps, partial sync, sections | PSARC timeline | build_timeline | Preserve separate normalizers | Migrated; repeat/sync/tempo/section regressions |
| Bends/curves/intent, vibrato, ties, HO/PO, mute, harmonic, tap, slap/pop, slides | PSARC techniques | _note_techniques/_merge_techniques/_resolve_slides | Regression fixtures | Migrated; bend/vibrato/tie regression + byte-preserving edit |
| Chord names/templates, arpeggios, anchors/handshapes | PSARC charts | part_to_arrangement | Preserve exact pitches | Migrated; original chord/handshape tests |
| Drum kit/hits, velocities, rolls, flams, ghost/choke/stack | package validator supports drums | part_to_drum_tab | Preserve native drum_tab | Migrated; articulation/roll/velocity tests + live drum inspection |
| Lyrics fetch/retry/edit/enable and word timing | inspect lyrics | lyrics.mjs + fetch_synced_lyrics | Source editor | Migrated; provider/lyric tests + live timed lyrics |
| LRC file import | — | Tk choose_lyrics / parse_lrc | Bring into desktop workflow | Migrated from Tk; shared parse_lrc exposed through native dialog |
| Chart/timeline offset | — | Python CLI --offset | Advanced creation option | Migrated from CLI; synthetic offset assertion |
| Artwork canonical release, custom/restore/remove | cover editor | prepare_cover/_release_artwork | Preserve | Migrated; metadata/artwork tests + live cover |
| Single archive, stable role IDs, provenance, genres/authors | PSARC manifest | write_feedpak v1.19 | Shared archive/validator | Shared archive/validator; synthetic and real outputs pass |
| CLI and developer utilities | CLI; backfill/reconvert tools | CLI analyze/create/batch/lyrics; raw URL CLI | Preserve callable functions | Retained; existing CLI + songsterr JSON bridge; Python module CLIs |
| Windows/macOS/Linux packaging | supported targets | Windows standalone | One FeedForge executable | Windows built/launched; macOS/Linux targets retained, not executed |

Inputs are native file paths/typed JSON in FF, links and edited JSON in Creator.
Outputs are FeedPak ZIPs/directories, audio files, previews and audit reports.
FF validates output schemas and returns structured errors/warnings; Creator currently
throws errors through its JSON subprocess and continues independent batch failures.
Missing optional artwork/lyrics can return empty results; missing audio is fatal.

## Decisions and sequencing

1. Migrate the source converter unchanged first, with its regression suite.
2. Add a Songsterr command to the existing packaged Python entrypoint and a bounded
   Electron service with explicit preload contract, progress, cancellation and input checks.
3. Prove synthetic end-to-end generation through FeedForge's validator/inspector/editor.
4. Share archive writing and validation; retain source-specific manifest fields and
   chart normalization. The compatible wire dictionaries are the internal model;
   do not invent a lossy common chart class.
5. Integrate into one shell with Home, Create sources, Library/editor, Tools and Settings.
   Keep the Songsterr draft mounted when navigating, and add outputs to the same library.
6. Refactor by responsibility, then production build/package and interactive verification.

Known source limitations to retain honestly: alternate repeat endings are not fully
interpreted; slide-in-from-below has no faithful FeedPak field; unsupported instruments
remain visible but disabled. Network providers can reject requests. No fake search.
Offset was CLI-only and LRC import Tk-only: migration must preserve these capabilities.

## Verification log

Inventory checkpoint completed before migration. Subsequent verification:

- Migrated all 23 Creator application regression tests; the other 63 baseline tests
  belong to its local `tmp/feedpak-spec` checkout, not application source.
- Canonical validator accepts migrated guitar and drum outputs.
- Added end-to-end synthetic generation/inspection/editing/byte-preservation checks,
  invalid-output protection, URL boundary tests and IPC batch-stop/cleanup tests.
- Found and fixed existing inspector omissions: native drum hits were counted as zero,
  and transcriber credits were normalized to contributor. Fixed editor overwrite
  unlinking an original before archive writing succeeded.
- Source-specific manifest normalization remains deliberate; common manifest YAML and
  atomic archive output are centralized in package_io.py. No second packaged backend.
- Existing settings key survives; defaults do not change merely by opening Songsterr.
- Live desktop Songsterr analysis succeeded with three selectable arrangements,
  canonical artwork and synchronized lyrics. Synthetic local audio is used for QA.
- Packaged backend converted a real PSARC and validated the result.
- `npm test`: 119 Python tests passed in 8.73s; five Node test entries and the
  lyric-event script passed. `npm run build`: 1,586 modules, successful production bundle.
- `npm run converter:pack`: PyInstaller succeeded, including FFmpeg, yt-dlp EJS
  and the optional token plugin in the existing backend executable.
- `npm run electron:pack`: Windows x64 portable succeeded and launched from its
  extracted app.asar with the packaged backend. No second application is launched.
- A real PSARC produced a valid 4.9 MB package. Live Songsterr analysis/creation
  produced three arrangements (lead, bass, drums), artwork and 32 timed lyric lines.
  Audio for that check was a generated silent WAV, not downloaded media.
- Both sources and an edited Songsterr copy were imported together through the
  packaged app's folder picker. Save-copy validation succeeded. Automated roundtrip
  assertions compare every non-manifest archive member byte for byte.
- The original localStorage key remains. The chosen output folder survived restart
  in an isolated QA profile; the personal app profile was not changed.
- Packaged library audit scanned all three QA packages, detected the expected
  original/copy duplicate pair, and wrote CSV and JSON reports. The PSARC package
  passed all enabled criteria; the two Songsterr entries were flagged only as duplicates.
- Static Babel scope checks found no unresolved symbols in extracted React modules.
  `git diff --check` passed. `npm audit --omit=dev` reported zero vulnerabilities.
- Found a pre-existing stem installer bug: it copied the entire source checkout,
  including build outputs and locked QA profile files. It now copies only runtime
  source, package metadata and documentation; launcher tests verify exclusions.
- Verification artifacts and detailed logs are in ignored
  `outputs/integration-verification/`; no downloaded charts/audio are committed.

## Final architecture and files

- `src/feedback_converter/songsterr.py`: source chart, timeline, drum, audio,
  artwork and lyric adapters, preserving the Creator algorithms.
- `songsterr_cli.py` and `cli.py`: structured operations through the one packaged
  converter, with explicit stages and errors.
- `package_io.py`: common manifest serialization and atomic ZIP writing.
- `electron/services/songsterr.cjs`: named IPC, input checks, numbered collisions,
  per-job temporary directories, sequential batch results, stop-after-current,
  timeout/process cleanup, stale-job cleanup and log integration.
- `ui/src/features/songsterr/`: source editor; `features/Home.jsx`: common entry.
  `WorkspacePanels.jsx`, `workspace-utils.jsx`, and `settings.mjs` extract existing
  responsibilities from the large App without changing the native contracts.
- `workbench.css`: shared desktop typography, controls, navigation, tables and focus.
- Existing main-process services remain intact; only the new source service is
  modularized to avoid a risky broad main-process rewrite.

## Remaining verification limits

Windows was built and exercised. macOS/Linux need their respective platform builds.
FeedBack game playback, fresh Demucs model downloads/inference, and a live YouTube
fallback/token browser were not exercised; source logic and regression tests remain.
Online providers can change independently. Alternate repeat endings and unsupported
instrument/slide semantics retain the reference converter's documented limitations.
There is no cross-session Songsterr draft persistence or song search because neither
existed in the source app; the UI labels link analysis accurately.

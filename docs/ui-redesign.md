# FeedForge desktop UI specification

One persistent shell, one accent and one native-file service. No embedded second app.

- Home: source actions, open packages/folders, recent session files and their status.
- Create / Songsterr: link input and batch list alongside an editable song workspace.
  Release, arrangement table, artwork/audio and lyrics are visible together; advanced
  chart offset remains available. Completed outputs enter the existing FeedPak library.
- Convertor: existing queue, filters, authoritative output planning, progress,
  stop-after-current, and source inspector. Conversion defaults live in Settings;
  the unused B-standard-to-seven-string desktop option was removed at user request.
- Library: package selection and editor, metadata/cover, stems, organization and audit.
- Tools: local/remote stem setup and existing model/device/Python/port diagnostics.
- Settings: output/naming/performance defaults and diagnostics/logs.

Tokens: charcoal background #111315, surface #181b1e, raised #202428, separator
#343a40; text #edf0f2, secondary #a9b0b7; restrained FeedForge cyan #39b6d5;
positive #72cc9c, warning #e1b866, destructive #f08080, focus cyan.
Segoe UI/system sans; body 13px, small 11–12px, section 15px, page 22px.
Spacing 4/8/12/16/24; radii 3/5px. Use flat separators and compact toolbars.

Forms have visible labels, icon actions have accessible names, focus rings remain
visible. Busy operations expose real stages and results, with no fabricated percent.
Songsterr batches stop after the current song; drafts survive navigation. Errors have
retry/local-audio guidance, diagnostics retain details. Empty states offer real actions.
Tables overflow horizontally; editors collapse to one column at narrow desktop widths.
Sidebar remains compact. No decorative metrics, gradients or animated backgrounds.

Keep source-specific editors because their inputs differ, but use the same controls,
navigation, package inspector, output paths, validator and archive implementation.

## September 18 visual polish

The sidebar uses the existing `assets/feedforge.png` logo with the app name and
version. Convertor precedes Songsterr. Home's library-folder action explicitly opens
Library & editor, including mixed-source folders and folders already in the session.
Cancellation leaves the current view unchanged; imports still deduplicate paths.

Legacy layout CSS is imported into a cascade layer. The shared workbench stylesheet
owns control appearance without escalating selector specificity: charcoal fields,
four-pixel corners, restrained selected states, visible keyboard focus, consistent
checkboxes, and reduced-motion support. Metadata fields have internal padding and
aligned labels; stem setup uses muted status surfaces and consistent selection rows.
An empty inspector presents guidance instead of missing-package errors.

Design references reviewed: [Impeccable](https://impeccable.style/),
[interface details](https://jakub.kr/writing/details-that-make-interfaces-feel-better),
[the companion skill](https://github.com/jakubkrehel/make-interfaces-feel-better),
[Taste](https://www.tasteskill.dev/), and
[Hallmark](https://github.com/nutlope/hallmark). They informed consistency, spacing,
typography, explicit transition properties, and restrained surfaces; the existing
sidebar remains the visual reference. No runtime dependency was added.

Validation: 119 Python tests, six Node test entries, lyrics checks and Vite build
passed. Native Windows smoke checks confirmed mixed-folder navigation, reopening
the same folder without duplicates, and metadata layout. Packaging and UI checks
use isolated QA profiles and copies of song files.

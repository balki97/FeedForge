# FeedForge desktop UI specification

One persistent shell, one accent and one native-file service. No embedded second app.

- Home: source actions, open packages/folders, recent session files and their status.
- Create / Songsterr: link input and batch list alongside an editable song workspace.
  Release, arrangement table, artwork/audio and lyrics are visible together; advanced
  chart offset remains available. Completed outputs enter the existing FeedPak library.
- Create / Rocksmith: existing queue, filters, authoritative output planning, progress,
  stop-after-current, and source inspector. All conversion options survive in Settings.
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

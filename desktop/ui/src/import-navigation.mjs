// Choose the destination before deduplication: reopening a loaded folder is
// still a navigation request. An explicit library action wins for mixed folders.
export function importDestination(paths, intent = true) {
  if (!intent) return null;
  if (typeof intent === "string") return intent;
  const packages = paths.filter(path => /\.(feedpak|psarc)$/i.test(path));
  if (!packages.length) return null;
  return packages.some(path => /\.feedpak$/i.test(path)) ? "feedpak" : "workspace";
}

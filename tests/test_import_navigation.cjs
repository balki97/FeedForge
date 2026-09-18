const test = require('node:test');
const assert = require('node:assert/strict');

test('imports route by source and preserve explicit library intent before deduplication', async () => {
  const { importDestination } = await import('../ui/src/import-navigation.mjs');
  assert.equal(importDestination(['song.PSARC']), 'workspace');
  assert.equal(importDestination(['song.feedpak', 'source.psarc']), 'feedpak');
  assert.equal(importDestination(['source.psarc'], 'feedpak'), 'feedpak');
  assert.equal(importDestination([], 'feedpak'), 'feedpak');
  assert.equal(importDestination([]), null); // cancelled/unsupported import
  assert.equal(importDestination(['song.feedpak'], false), null); // background creation
  assert.equal(importDestination(['song.feedpak']), 'feedpak');
});

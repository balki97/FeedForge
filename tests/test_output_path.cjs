const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

test('output folder joins follow POSIX, drive, and UNC path conventions', async () => {
  const { joinPath } = await import('../ui/src/output-path.mjs');
  for (const folder of ['/home/zeiko/Documents/Rocksmith/feedpack-reprocessed/test/', '/', '/Users/player/Songs/']) {
    const actual = joinPath(folder, 'Song.edited.feedpak');
    assert.equal(actual, path.posix.join(folder, 'Song.edited.feedpak'));
    assert.equal(path.posix.dirname(actual), path.posix.normalize(folder).replace(/\/$/, '') || '/');
  }
  for (const folder of ['C:\\Songs\\test\\', 'C:\\', '\\\\server\\share\\test']) {
    assert.equal(joinPath(folder, 'Song.feedpak'), path.win32.join(folder, 'Song.feedpak'));
  }
  assert.equal(joinPath('/library', 'Artist\\Album', 'song.feedpak'), '/library/Artist/Album/song.feedpak');
});

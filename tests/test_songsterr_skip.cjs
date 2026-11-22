const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const { registerSongsterr, outputPayload } = require('../desktop/electron/services/songsterr.cjs');

test('Songsterr skips existing output before running converter; mixed batches count correctly', async t => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'feedforge-skip-test-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const existing = path.join(dir, 'Existing.feedpak');
  fs.writeFileSync(existing, 'keep');
  const payload = { url: 'https://www.songsterr.com/a/wsa/song-tab-s19',
    selected_parts: [0], output_dir: dir, output_name: 'Existing.feedpak', skip_existing: true };
  assert.equal(outputPayload(payload).skipped, true);
  assert.equal(path.basename(outputPayload({...payload, skip_existing: false}).output_path), 'Existing (2).feedpak');
  const handlers = new Map();
  let calls = 0;
  registerSongsterr({ app: { getPath: () => dir }, ipcMain: { handle: (name, fn) => handlers.set(name, fn) },
    logDebug() {}, removeTemporaryDirectory: p => fs.rmSync(p, { recursive: true, force: true }),
    runConverter: async args => {
      calls++;
      const value = JSON.parse(fs.readFileSync(args[1], 'utf8')).payload;
      fs.writeFileSync(value.output_path, 'created');
      return { code: 0, stdout: JSON.stringify({ok: true, result: {output_path: value.output_path}}) };
    }
  });
  const event = {sender: {isDestroyed: () => false, send() {}}};
  assert.equal(handlers.get('songsterr:checkOutput')(event, payload).skipped, true);
  assert.equal((await handlers.get('songsterr:create')(event, payload)).skipped, true);
  assert.equal(calls, 0);
  const result = await handlers.get('songsterr:batch')(event, [payload, {...payload, output_name: 'New.feedpak'}]);
  assert.equal(calls, 1);
  assert.equal(result.created, 1);
  assert.equal(result.existing, 1);
  assert.equal(result.failed, 0);
  assert.equal(result.skipped, 0); // Cancellation is distinct from an existing file.
  assert.equal(fs.readFileSync(existing, 'utf8'), 'keep');
  assert.equal(fs.existsSync(path.join(dir, 'Existing (2).feedpak')), false);
});

test('PSARC desktop bridge passes skip flag and distinguishes skipped from converted', async () => {
  const source = fs.readFileSync(path.join(__dirname, '../desktop/electron/main.cjs'), 'utf8');
  const start = source.indexOf('ipcMain.handle("converter:convert"');
  const end = source.indexOf('\nipcMain.handle(', start + 1);
  for (const mixed of [false, true]) {
    let handler, args;
    vm.runInNewContext(source.slice(start, end), {
      ipcMain: {handle: (_, fn) => { handler = fn; }},
      logDebug() {}, tail: value => value,
      runConverter: async value => {
        args = value;
        return {code: 0, stderr: '', stdout: 'skipped /out/Existing.feedpak\n' +
          (mixed ? 'wrote /out/New.feedpak\nvalidated /out/New.feedpak\n' : '')};
      }
    });
    const result = await handler({}, {inputPath: '/source.psarc', skipExisting: true});
    assert.ok(args.includes('--skip-existing'));
    assert.equal(result.ok, true);
    assert.equal(result.skipped, !mixed);
    assert.equal(result.skippedPaths.length, 1);
    assert.equal(result.outputPaths.length, mixed ? 1 : 0);
  }
});

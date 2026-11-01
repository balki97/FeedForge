const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function setup(selected, code = 0) {
  const source = fs.readFileSync(path.join(__dirname, '../desktop/electron/main.cjs'), 'utf8');
  const handlerSource = source.slice(source.indexOf('ipcMain.handle("feedpak:exportGp5"'), source.indexOf('ipcMain.handle("dialog:pickCoverImage"'));
  let handler, args, options;
  vm.runInNewContext(handlerSource, {
    ipcMain: {handle: (_name, fn) => { handler = fn; }}, mainWindow: {}, path: path.posix,
    dialog: {showSaveDialog: async (_window, value) => { options = value; return selected; }},
    runConverter: async value => { args = value; return {code, stdout: 'wrote /chosen/all.gp5\n', stderr: code ? 'invalid chart' : 'warning: Quantized\n'}; },
    logDebug: () => {},
  });
  return {call: () => handler({}, {inputPath: '/music/song.feedpak', outputDir: '/exports'}),
    args: () => args, options: () => options};
}

test('GP5 save dialog cancellation does not run the converter', async () => {
  const app = setup({canceled: true});
  assert.equal((await app.call()).cancelled, true);
  assert.equal(app.args(), undefined);
});

test('GP5 IPC uses one file, propagates warnings and converter errors', async () => {
  for (const code of [0, 1]) {
    const app = setup({filePath: '/chosen/all.gp5', canceled: false}, code);
    const result = await app.call();
    assert.deepEqual(Array.from(app.args()), ['/music/song.feedpak', '--export-gp5', '-o', '/chosen/all.gp5', '--overwrite']);
    assert.equal(app.options().defaultPath, '/exports/song.gp5');
    assert.equal(result.ok, code === 0);
    assert.equal(result.outputPath, code ? null : '/chosen/all.gp5');
    assert.equal(code ? result.error : result.warnings[0], code ? 'invalid chart' : 'Quantized');
  }
});

test('adding a missing extension does not bypass overwrite protection', async () => {
  const app = setup({filePath: '/chosen/all', canceled: false});
  await app.call();
  assert.deepEqual(Array.from(app.args()), ['/music/song.feedpak', '--export-gp5', '-o', '/chosen/all.gp5']);
});

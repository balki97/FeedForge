const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

test('audit reports actual completed package counts, including empty libraries', async () => {
  const source = fs.readFileSync(path.join(__dirname, '../electron/main.cjs'), 'utf8');
  const handlerSource = source.slice(source.indexOf('ipcMain.handle("audit:feedpakLibrary"'), source.indexOf('ipcMain.handle("audit:openReport"'));
  for (const count of [0, 3]) {
    let handler;
    const updates = [];
    vm.runInNewContext(handlerSource, {
      ipcMain: { handle: (_name, fn) => { handler = fn; } },
      fs: { existsSync: () => true }, path: path.posix,
      normalizeAuditCriteria: value => value, logDebug: () => {},
      findFeedpakFiles: async () => Array.from({length: count}, (_, i) => `/songs/${i}.feedpak`),
      inspectFeedpakForAudit: async (_root, file) => ({ relativePath: file, status: 'pass' }),
      writeAuditReports: () => ({ csvPath: '/report.csv', jsonPath: '/report.json' }),
    });
    const result = await handler({ sender: { isDestroyed: () => false, send: (channel, value) => {
      assert.equal(channel, 'audit:progress'); updates.push(value);
    } } }, { root: '/songs', workers: 3 });
    assert.equal(result.total, count);
    assert.equal(updates[0].phase, 'discovering');
    assert.deepEqual(updates.filter(p => p.phase === 'checking').map(p => p.completed), Array.from({length: count + 1}, (_, i) => i));
    assert.equal(updates.at(-1).phase, 'report');
    assert.equal(updates.at(-1).total, count);
  }
});

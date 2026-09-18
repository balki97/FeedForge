const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');
const { execFileSync } = require('node:child_process');

test('release cleanup preserves current artifacts and other platforms', async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'feedforge-release-test-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const release = path.join(root, 'release');
  fs.mkdirSync(release);
  const names = ['FeedForge 0.1.42.exe', 'FeedForge 0.1.44.exe', 'FeedForge-0.1.42.dmg', 'notes.txt'];
  for (const name of names) fs.writeFileSync(path.join(release, name), 'artifact');
  const context = { module: { exports: {} }, require, console, __dirname: path.join(root, 'tools') };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../tools/clean-release.cjs'), 'utf8'), context);
  const cleanup = context.module.exports;
  await cleanup({ artifactPaths: [] });
  assert.equal(fs.readdirSync(release).length, 4);
  await cleanup({ artifactPaths: [path.join(release, 'FeedForge 0.1.44.exe')] });
  assert.deepEqual(fs.readdirSync(release).sort(), names.slice(1).sort());
});

test('build cleanup dry run preserves files and real cleanup keeps deliverables', (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'feedforge-clean-test-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  execFileSync('git', ['init', '-q', root]);
  const kept = ['release/FeedForge 0.1.44.exe', 'release/SHA256SUMS.txt', 'src/main.py', 'outputs/song.feedpak'];
  const removed = ['release/win-unpacked/runtime.txt', 'build/cache.txt'];
  for (const name of [...kept, ...removed]) {
    fs.mkdirSync(path.dirname(path.join(root, name)), { recursive: true });
    fs.writeFileSync(path.join(root, name), 'keep or clean');
  }
  const source = fs.readFileSync(path.join(__dirname, '../tools/clean-build.cjs'), 'utf8');
  for (const dryRun of [true, false]) {
    const context = {
      require, __dirname: path.join(root, 'tools'),
      process: { argv: dryRun ? ['--dry-run'] : [], exitCode: null },
    };
    vm.runInNewContext(source, context);
    assert.equal(context.process.exitCode, 0);
    for (const name of kept) assert.ok(fs.existsSync(path.join(root, name)), name);
    for (const name of removed) assert.equal(fs.existsSync(path.join(root, name)), dryRun, name);
  }
});

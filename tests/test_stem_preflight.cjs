const test = require('node:test');
const assert = require('node:assert/strict');
const { checkStemServer } = require('../electron/services/stem-preflight.cjs');

test('stem preflight handles ready, unavailable, wrong-model and authenticated remote servers', async () => {
  const ready = async () => ({ ok: true, body: { ok: true, model: 'htdemucs_6s' } });
  assert.equal((await checkStemServer({ model: 'htdemucs_6s' }, ready)).ready, true);
  assert.equal((await checkStemServer({ model: 'htdemucs' }, ready)).ready, false);
  assert.equal((await checkStemServer({}, async () => ({ ok: false }))).ready, false);
  assert.equal((await checkStemServer({}, async () => { throw Error('offline'); })).ready, false);
  assert.equal((await checkStemServer({ url: 'file:///x' }, ready)).ready, false);
  await checkStemServer({ url: 'https://example.com/stems/', apiKey: 'test-key' }, async (url, timeout, headers) => {
    assert.equal(url, 'https://example.com/stems/health');
    assert.equal(timeout, 5000);
    assert.equal(headers.Authorization, 'Bearer test-key');
    assert.equal(headers['X-API-Key'], 'test-key');
    return { ok: true, body: { ok: true } };
  });
});

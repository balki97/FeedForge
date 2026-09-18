const test = require('node:test');
const assert = require('node:assert/strict');

test('visible Home files bypass a large library backlog without duplicating active work', async () => {
  const { prioritizeInspections } = await import('../ui/src/inspection-queue.mjs');
  const queue = Array.from({ length: 3558 }, (_, i) => `file-${i}`);
  const visible = queue.slice(-8).reverse();
  const result = prioritizeInspections(queue, [...visible, visible[0], 'already-running']);
  assert.deepEqual(result.slice(0, 8), visible);
  assert.deepEqual(result.slice(8), queue.slice(0, -8));
  assert.equal(new Set(result).size, queue.length);
  assert.deepEqual(prioritizeInspections(result, ['file-42']).slice(0, 2), ['file-42', visible[0]]);
  assert.deepEqual(prioritizeInspections(result, []), result);
});

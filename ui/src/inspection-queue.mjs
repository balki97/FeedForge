export function prioritizeInspections(queue, visibleIds) {
  const pending = new Set(queue);
  const first = [...new Set(visibleIds)].filter(id => pending.has(id));
  const priority = new Set(first);
  return [...first, ...queue.filter(id => !priority.has(id))];
}

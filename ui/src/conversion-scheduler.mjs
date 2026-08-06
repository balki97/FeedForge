function normalizedWorkerLimit(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return 1;
  return Math.max(1, Math.floor(parsed));
}

function archiveName(filePath) {
  return String(filePath || "").replace(/\\/g, "/").split("/").pop().toLowerCase();
}

/** Return true only for RS1 archives that share the large songs.psarc payload. */
export function usesSharedRs1SongsAudio(filePath) {
  const name = archiveName(filePath);
  if (name === "songs.psarc") return true;
  if (!name.endsWith(".psarc") || !name.includes("rs1compatibility")) return false;
  return !/^rs1compatibilitydisc(?:[_\-.]|$)/.test(name);
}

async function consumeQueue(queue, cursor, runItem, shouldStop) {
  while (!shouldStop()) {
    const index = cursor.value;
    cursor.value += 1;
    if (index >= queue.length) return;
    await runItem(queue[index]);
  }
}

/**
 * Run ordinary conversions at the selected concurrency while keeping linked
 * RS1 archives serialized. Once the linked queue is empty, its worker joins
 * the ordinary queue so reserved capacity never remains idle.
 */
export async function runConversionQueues({
  linkedItems = [],
  regularItems = [],
  workerLimit = 1,
  runItem,
  shouldStop = () => false
}) {
  if (typeof runItem !== "function") {
    throw new TypeError("runConversionQueues requires a runItem function.");
  }

  const linkedQueue = Array.isArray(linkedItems) ? linkedItems : [];
  const regularQueue = Array.isArray(regularItems) ? regularItems : [];
  const limit = normalizedWorkerLimit(workerLimit);

  if (linkedQueue.length && regularQueue.length && limit > 1) {
    const linkedCursor = { value: 0 };
    const regularCursor = { value: 0 };
    const regularWorkerCount = Math.min(limit - 1, regularQueue.length);
    const linkedThenRegular = async () => {
      await consumeQueue(linkedQueue, linkedCursor, runItem, shouldStop);
      if (!shouldStop()) {
        await consumeQueue(regularQueue, regularCursor, runItem, shouldStop);
      }
    };
    await Promise.all([
      linkedThenRegular(),
      ...Array.from(
        { length: regularWorkerCount },
        () => consumeQueue(regularQueue, regularCursor, runItem, shouldStop)
      )
    ]);
    return;
  }

  const queue = [...linkedQueue, ...regularQueue];
  if (!queue.length) return;
  const cursor = { value: 0 };
  const workerCount = linkedQueue.length ? 1 : Math.min(limit, queue.length);
  await Promise.all(
    Array.from({ length: workerCount }, () => consumeQueue(queue, cursor, runItem, shouldStop))
  );
}

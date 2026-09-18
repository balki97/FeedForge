import assert from "node:assert/strict";
import { exportLyricEvents, lyricRows } from "../ui/src/features/songsterr/lyrics.mjs";

const rows = lyricRows([{
  t: 10, d: 2, w: "never ends+",
  words: [{ t: 10, d: .8, w: "never" }, { t: 10.8, d: .7, w: "ends+" }]
}]);
assert.equal(rows[0].text, "never ends");
assert.deepEqual(exportLyricEvents(rows).map((word) => word.w), ["never", "ends+"]);

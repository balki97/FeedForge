const assert = require("node:assert/strict");
const { parseCoreResponse } = require("../electron/services/core-response.cjs");

assert.deepEqual(
  parseCoreResponse('[download] 85.5%\r[download] 100% {"output_path":"Bob Dylan – test.feedpak","arrangements":4}\n'),
  { output_path: "Bob Dylan – test.feedpak", arrangements: 4 }
);

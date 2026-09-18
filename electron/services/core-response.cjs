function parseCoreResponse(stdout) {
  for (const line of stdout.trim().split(/\r?\n/).reverse()) {
    try { return JSON.parse(line); } catch {}
  }
  for (let index = stdout.lastIndexOf("{"); index >= 0; index = stdout.lastIndexOf("{", index - 1)) {
    try { return JSON.parse(stdout.slice(index).trim()); } catch {}
  }
  throw new Error("No JSON response found.");
}

module.exports = { parseCoreResponse };

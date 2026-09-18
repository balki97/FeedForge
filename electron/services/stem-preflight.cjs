async function checkStemServer(options, requestJson) {
  try {
    const url = new URL(options.url || "http://127.0.0.1:7865");
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) {
      throw new Error("Use an HTTP or HTTPS stem server URL.");
    }
    url.pathname = url.pathname.replace(/\/$/, "") + "/health";
    url.search = "";
    url.hash = "";
    const result = await requestJson(url.toString(), 5000, options.apiKey ? { Authorization: `Bearer ${options.apiKey}`, "X-API-Key": options.apiKey } : {});
    if (!result.ok || !result.body?.ok) return { ready: false, error: "The stem server isn’t ready. Open Tools · stems to install or start it." };
    if (result.body.model && options.model && result.body.model !== options.model) {
      return { ready: false, error: "The server is running a different model. Open Tools · stems to apply your selection." };
    }
    return { ready: true };
  } catch (error) { return { ready: false, error: error.message }; }
}

module.exports = { checkStemServer };

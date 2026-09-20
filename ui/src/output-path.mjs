// The selected folder comes from the native picker; keep its path convention.
export function joinPath(...parts) {
  const values = parts.filter(part => part !== null && part !== undefined && String(part).length).map(String);
  if (!values.length) return "";
  const separator = values[0].startsWith("/") ? "/" : /\\|^[a-z]:/i.test(values[0]) ? "\\" : "/";
  return values.map((value, index) => {
    const normalized = value.replace(/[\\/]+/g, separator);
    if (index === 0) {
      // Preserve the UNC prefix and root when removing trailing separators.
      const root = separator === "\\" && value.startsWith("\\\\") ? "\\" : "";
      return root + normalized.replace(/[\\/]+$/, "");
    }
    return normalized.replace(/^[\\/]+|[\\/]+$/g, "");
  }).join(separator) || separator;
}

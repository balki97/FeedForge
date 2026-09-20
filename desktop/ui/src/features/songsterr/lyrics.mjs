export function lyricRows(events) {
  return (events || []).map((event) => {
    const text = String(event.w || "").replace(/\+$/, "");
    return { ...event, text, originalText: text };
  });
}

export function exportLyricEvents(lines) {
  const clean = lines.filter((line) => line.text.trim()).sort((a, b) => Number(a.t) - Number(b.t));
  return clean.flatMap((line, index) => {
    const start = Number(line.t);
    const text = line.text.trim().replace(/\+$/, "");
    if (line.words?.length && text === line.originalText) {
      const shift = start - Number(line.words[0].t);
      return line.words.map((word) => ({ ...word, t: Number(word.t) + shift }));
    }
    const words = text.split(/\s+/);
    const available = Math.max(.05, Number(clean[index + 1]?.t ?? start + Number(line.d || 2)) - start);
    const slice = Math.min(available, Math.max(1, words.length * .65)) / words.length;
    return words.map((word, wordIndex) => ({
      t: start + wordIndex * slice, d: slice,
      w: `${word}${wordIndex === words.length - 1 ? "+" : ""}`
    }));
  });
}

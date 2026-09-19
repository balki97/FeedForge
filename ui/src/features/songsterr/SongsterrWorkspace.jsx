import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Download, FileAudio, FolderOpen, ImageIcon, LoaderCircle, Music2, RefreshCw, Search, Trash2, Upload, XCircle } from "lucide-react";
import { exportLyricEvents, lyricRows } from "./lyrics.mjs";

const api = window.feedbackConverter?.songsterr;

function roleOptions(track) {
  if (track.isDrums) return ["drums"];
  if (track.isBassGuitar) return ["bass"];
  return ["lead", "rhythm", "combo"];
}

function safeName(value) {
  return String(value || "").replace(/[<>:"/\\|?*\x00-\x1f]/g, "_").replace(/[ .]+$/, "");
}

function outputName(form) {
  const base = [form.artist, form.title, form.album].filter(Boolean).join(" - ");
  return `${safeName(base) || "Songsterr Chart"}.feedpak`;
}

function songEditor(result, selectedParts = [result.selected_part_id]) {
  const selected = new Set(selectedParts);
  const fetchedCover = {
    url: result.cover_url || "", path: "", preview: "",
    source: result.cover_source || "No release artwork found"
  };
  return {
    song: result,
    form: {
      title: result.title, artist: result.artist, album: result.album,
      year: result.year || "", author: result.author || ""
    },
    tracks: result.tracks.map((track) => ({
      ...track,
      selected: track.supported && selected.has(track.partId),
      role: track.role || roleOptions(track)[0],
      name: track.title || track.instrument || roleOptions(track)[0]
    })),
    lyrics: lyricRows(result.lyrics?.events),
    lyricsEnabled: Boolean(result.lyrics?.events?.length),
    cover: fetchedCover,
    fetchedCover,
    audioPath: ""
  };
}

export default function SongsterrWorkspace({ outputDir: sharedOutputDir, setOutputDir, onCreated, requestConversion }) {
  const [defaultOutput, setDefaultOutput] = useState("");
  const outputDir = sharedOutputDir || defaultOutput;
  const [url, setUrl] = useState("");
  const [song, setSong] = useState(null);
  const [form, setForm] = useState({ title: "", artist: "", album: "", year: "", author: "" });
  const [tracks, setTracks] = useState([]);
  const [lyrics, setLyrics] = useState([]);
  const [lyricsEnabled, setLyricsEnabled] = useState(true);
  const [cover, setCover] = useState({ url: "", path: "", preview: "", source: "" });
  const [fetchedCover, setFetchedCover] = useState(null);
  const [audioPath, setAudioPath] = useState("");
  const [videoUrl, setVideoUrl] = useState("");
  const [timingMode, setTimingMode] = useState("songsterr");
  const [audioPreview, setAudioPreview] = useState(null);
  const [measureIndex, setMeasureIndex] = useState(0);
  const audioRef = useRef(null);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState(null);
  const [batch, setBatch] = useState([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const [offset, setOffset] = useState(0);
  const [progress, setProgress] = useState(null);
  const [results, setResults] = useState([]);
  const [stopping, setStopping] = useState(false);
  useEffect(() => api.onProgress(setProgress), []);

  useEffect(() => { if (!sharedOutputDir) api.defaults().then((value) => setDefaultOutput(value.output_dir)).catch(error => setNotice({ type: "error", text: error.message })); }, []);

  const selectedTracks = useMemo(() => tracks.filter((track) => track.selected), [tracks]);
  const coverPreview = cover.preview || cover.url;



  function loadEditor(entry) {
    setSong(entry.song);
    setForm(entry.form);
    setTracks(entry.tracks);
    setLyrics(entry.lyrics);
    setLyricsEnabled(entry.lyricsEnabled);
    setCover(entry.cover);
    setFetchedCover(entry.fetchedCover);
    setAudioPath(entry.audioPath);
    setVideoUrl(entry.videoUrl || "");
    setTimingMode(entry.timingMode || "songsterr");
    setAudioPreview(entry.audioPreview || null);
    setMeasureIndex(0);
    setOffset(entry.offset || 0);
  }

  function currentEditor() {
    return { song, form, tracks, lyrics, lyricsEnabled, cover, fetchedCover, audioPath, videoUrl, timingMode, audioPreview, offset };
  }

  function selectSong(index) {
    if (index === activeIndex) return;
    const saved = currentEditor();
    setBatch((current) => current.map((entry, position) => position === activeIndex ? saved : entry));
    loadEditor(batch[index]);
    setActiveIndex(index);
  }

  async function analyze() {
    const urls = [...new Set(url.split(/\s+/).map((value) => value.trim()).filter(Boolean))];
    if (!urls.length) return setNotice({ type: "error", text: "Paste at least one Songsterr tab link." });
    if (busy) return;
    setBusy("analyze");
    setProgress(null);
    setNotice({ type: "info", text: `Reading ${urls.length} Songsterr link${urls.length === 1 ? "" : "s"}, release artwork, and synchronized lyrics…` });
    try {
      const results = [];
      for (const value of urls) results.push(await api.analyze(value));
      const grouped = new Map();
      results.forEach((result) => {
        const key = String(result.song_id || `${result.artist}\0${result.title}`).toLowerCase();
        const existing = grouped.get(key);
        if (existing) existing.selectedParts.add(result.selected_part_id);
        else grouped.set(key, { result, selectedParts: new Set([result.selected_part_id]) });
      });
      const editors = [...grouped.values()]
        .sort((left, right) => `${left.result.artist}\0${left.result.title}`.localeCompare(`${right.result.artist}\0${right.result.title}`))
        .map(({ result, selectedParts }) => songEditor(result, [...selectedParts]));
      setBatch(editors);
      setActiveIndex(0);
      loadEditor(editors[0]);
      setNotice({
        type: "success",
        text: editors.length === 1
          ? `Found ${editors[0].tracks.filter((item) => item.supported).length} chartable arrangements and ${editors[0].lyrics.length} timed lyric lines.`
          : `Sorted ${urls.length} links into ${editors.length} songs. Review each song, then export them together.`
      });
    } catch (error) {
      setSong(null);
      setNotice({ type: "error", text: error.message });
    } finally {
      setBusy("");
    }
  }

  function updateTrack(partId, values) {
    setAudioPreview(null);
    setTracks((current) => current.map((track) => track.partId === partId ? { ...track, ...values } : track));
  }

  function updateLyric(index, values) {
    setLyrics((current) => current.map((line, lineIndex) => lineIndex === index ? { ...line, ...values } : line));
  }

  async function retryLyrics() {
    setBusy("lyrics");
    setNotice({ type: "info", text: "Trying exact matches, broader lyric search, and video captions…" });
    try {
      const result = await api.findLyrics({
        artist: form.artist, title: form.title, album: form.album,
        duration: song.duration, video_url: videoUrl || song.video_url
      });
      setSong((current) => ({ ...current, lyrics: result }));
      const lines = lyricRows(result.events);
      setLyrics(lines);
      setLyricsEnabled(Boolean(lines.length));
      setNotice(lines.length
        ? { type: "success", text: `Found ${lines.length} timed lyric lines from ${result.provider} (${result.match_method} match).` }
        : { type: "error", text: result.message || "No reliable timed lyrics were found." });
    } catch (error) {
      setNotice({ type: "error", text: error.message });
    } finally {
      setBusy("");
    }
  }

  async function replaceCover() {
    const selected = await api.pickCover();
    if (selected) setCover({ url: "", path: selected.path, preview: selected.preview, source: "Custom artwork" });
  }

  async function chooseAudio() {
    const selected = await api.pickAudio();
    if (selected) { setAudioPath(selected); setAudioPreview(null); setOffset(0); }
  }

  async function preparePreview() {
    setBusy("preview");
    setAudioPreview(null);
    try {
      const result = await api.preview({ url: song.url, selected_parts: selectedTracks.map(track => track.partId),
        audio_path: audioPath, video_url: videoUrl, timing_mode: timingMode });
      setAudioPreview(result);
      setMeasureIndex(0);
      setNotice(null);
    } catch (error) { setNotice({ type: "error", text: error.message }); }
    finally { setBusy(""); }
  }

  async function chooseOutput() {
    const selected = await api.pickOutput();
    if (selected) setOutputDir(selected);
  }

  async function createFeedPak() {
    if (!selectedTracks.length) return setNotice({ type: "error", text: "Select at least one arrangement." });
    if (!outputDir) return setNotice({ type: "error", text: "Choose an output folder." });
    const stemOptions = await requestConversion();
    if (!stemOptions) return;
    setBusy("create");
    setStopping(false);
    setResults([]);
    setProgress(null);
    setNotice({ type: "info", text: "Preparing charts and audio…" });
    try {
      const live = currentEditor();
      const jobs = batch.map((entry, index) => index === activeIndex ? live : entry);
      const payloads = jobs.map((entry) => {
        const chosen = entry.tracks.filter((track) => track.selected);
        return {
          ...stemOptions,
          url: entry.song.url,
          offset: Number(entry.offset || 0),
          video_url: entry.videoUrl || "",
          timing_mode: entry.timingMode || "songsterr",
          title: entry.form.title,
          artist: entry.form.artist,
          album: entry.form.album,
          year: entry.form.year ? Number(entry.form.year) : null,
          author: entry.form.author,
          genres: entry.song.genres,
          selected_parts: chosen.map((track) => track.partId),
          roles: Object.fromEntries(chosen.map((track) => [track.partId, track.role])),
          names: Object.fromEntries(chosen.map((track) => [track.partId, track.name])),
          cover_url: entry.cover.url,
          cover_path: entry.cover.path,
          lyrics: entry.lyricsEnabled ? exportLyricEvents(entry.lyrics) : [],
          audio_path: entry.audioPreview?.audio_path || entry.audioPath,
          output_dir: outputDir,
          output_name: outputName(entry.form)
        };
      });
      const empty = payloads.findIndex((payload) => !payload.selected_parts.length);
      if (empty >= 0) throw new Error(`${jobs[empty].form.artist} — ${jobs[empty].form.title} has no selected arrangements.`);
      const result = payloads.length === 1
        ? await api.create(payloads[0])
        : await api.createBatch(payloads);
      setBatch(jobs);
      const completed = payloads.length === 1 ? [{ok: true, ...result}] : result.results;
      setResults(completed);
      onCreated(completed.filter(row => row.ok).map(row => row.output_path));
      if (payloads.length === 1) {
        setNotice({ type: "success", text: `FeedPak created with ${result.arrangements} arrangements and ${result.lyrics} timed lyric lines.` });
      } else {
        const failures = result.results.filter((item) => !item.ok);
        setNotice(failures.length
          ? { type: "error", text: `Created ${result.created} of ${payloads.length} FeedPaks. ${failures.map((item) => `${item.title}: ${item.error}`).join(" · ")}` }
          : { type: "success", text: `Created ${result.created} FeedPaks${result.skipped ? `; ${result.skipped} stopped before starting` : ""} in ${outputDir}.` });
      }
    } catch (error) {
      setNotice({ type: "error", text: error.message });
    } finally {
      setBusy("");
    }
  }

  async function guarded(action) {
    try { await action(); } catch (error) { setNotice({type: "error", text: error.message}); }
  }
  async function importLyrics() {
    const events = await api.importLrc();
    if (!events) return;
    setLyrics(lyricRows(events));
    setLyricsEnabled(Boolean(events.length));
    setSong(current => ({...current, lyrics: {provider: "LRC file", events}}));
  }
  return <section className="songsterr-workspace" aria-label="Create from Songsterr">
    <div className="source-entry">
      <label>Songsterr tab links<textarea aria-label="Songsterr tab links" value={url} disabled={Boolean(busy)} onChange={event => setUrl(event.target.value)} onKeyDown={event => {if (event.ctrlKey && event.key === 'Enter' && !busy) analyze();}} placeholder="Paste one or more Songsterr tab links, one per line" /></label>
      <button className="primary" onClick={analyze} disabled={Boolean(busy)}><Search size={16}/> {busy === 'analyze' ? 'Reading links…' : 'Read links'}</button>
    </div>
    {notice && <div role={notice.type === 'error' ? 'alert' : 'status'} className={`workflow-notice ${notice.type}`}>{notice.type === 'error' ? <XCircle size={17}/> : <InfoIcon/>}<span>{notice.text}</span></div>}
    {busy && <div role="status" className="job-stage"><LoaderCircle size={16} className="spin"/><span>{progress?.stage || 'Working…'}{progress?.total > 1 ? ` · Song ${progress.index} of ${progress.total}` : ''}</span>{busy === 'create' && batch.length > 1 && <button disabled={stopping} onClick={() => guarded(async () => {await api.cancel(); setStopping(true);})}>{stopping ? 'Stopping after current song' : 'Stop after current song'}</button>}</div>}
    {!song ? <div className="workflow-empty"><Music2 size={30}/><p>Paste a Songsterr link to begin.</p></div> : <>
      {batch.length > 1 && <div className="song-batch" aria-label="Songs in this batch">{batch.map((entry,index) => <button key={entry.song.song_id || index} className={index === activeIndex ? 'active' : ''} disabled={Boolean(busy)} onClick={() => selectSong(index)}><span>{index + 1}</span><strong>{entry.form.title}</strong><small>{entry.form.artist}</small></button>)}</div>}
      <fieldset className="song-editor" disabled={Boolean(busy)}>
        <section className="editor-section release-editor"><h2>Release & credits</h2><div className="release-fields"><div className="artwork-editor"><div className="artwork-preview">{coverPreview ? <img src={coverPreview} alt="Album artwork"/> : <ImageIcon size={32}/>}</div><div className="compact-actions"><button title="Replace artwork" aria-label="Replace artwork" onClick={() => guarded(replaceCover)}><Upload size={15}/></button><button title="Restore release artwork" aria-label="Restore release artwork" disabled={!fetchedCover?.url} onClick={() => setCover(fetchedCover)}><RefreshCw size={15}/></button><button title="Remove artwork" aria-label="Remove artwork" onClick={() => setCover({url:'',path:'',preview:'',source:'No cover'})}><Trash2 size={15}/></button></div><small>{cover.source}</small></div><div className="form-grid">{[['title','Song title'],['artist','Artist'],['album','Album'],['year','Year'],['author','Charter / author']].map(([key,label]) => <label key={key}>{label}<input value={form[key]} onChange={event => setForm({...form,[key]:event.target.value})}/></label>)}</div></div></section>
        <section className="editor-section"><div className="section-heading"><h2>Arrangements</h2><span>{selectedTracks.length} selected</span></div><div className="table-scroll"><table className="arrangement-table"><thead><tr><th>Include / source part</th><th>In-game name</th><th>Role</th></tr></thead><tbody>{tracks.map(track => <tr key={track.partId}><td><label className="check-row"><input type="checkbox" checked={Boolean(track.selected)} disabled={!track.supported} onChange={event => updateTrack(track.partId,{selected:event.target.checked})}/><span>{track.title || track.instrument}<small>{track.isDrums ? 'Drums' : track.isBassGuitar ? 'Bass' : track.isGuitar ? 'Guitar' : 'This instrument is not supported'}</small></span></label></td><td>{track.supported && <input aria-label={`Name for ${track.title || track.partId}`} value={track.name} disabled={!track.selected} onChange={event => updateTrack(track.partId,{name:event.target.value})}/>}</td><td>{track.supported && <select aria-label={`Role for ${track.title || track.partId}`} value={track.role} disabled={!track.selected} onChange={event => updateTrack(track.partId,{role:event.target.value})}>{roleOptions(track).map(role => <option key={role}>{role}</option>)}</select>}</td></tr>)}</tbody></table></div></section>
        <section className="editor-section"><h2>Audio & output</h2>
          <div className="form-grid">
            <div><label>Replacement YouTube video<input type="url" value={videoUrl} placeholder={song.video_url || "https://www.youtube.com/watch?v=…"} onChange={event => { setVideoUrl(event.target.value); setAudioPath(""); setAudioPreview(null); setOffset(0); }}/></label>
              <p className="file-value">{audioPath || (videoUrl ? "Using your replacement video" : song.video_url || "Choose a video or local audio")}</p>
              <div className="compact-actions"><button onClick={() => guarded(chooseAudio)}><FileAudio size={15}/> Choose audio</button>{(audioPath || videoUrl) && <button onClick={() => {setAudioPath(''); setVideoUrl(''); setAudioPreview(null); setOffset(0);}}>Restore Songsterr audio</button>}</div>
            </div>
            <div><span className="field-label">Output folder</span><p className="file-value">{outputDir || 'Choose a folder'}</p><button onClick={() => guarded(chooseOutput)}><FolderOpen size={15}/> Choose folder</button></div>
          </div>
          <div className="audio-sync">
            <div className="section-heading"><h3>Audio sync</h3><button disabled={!selectedTracks.length} onClick={preparePreview}>Load audio preview</button></div>
            <div className="form-grid">
              <label>Chart timing<select value={timingMode} onChange={event => {setTimingMode(event.target.value); setAudioPreview(null); setOffset(0);}}><option value="songsterr">Songsterr sync</option><option value="score">Score tempo</option></select></label>
              <label>Chart offset (seconds)<input type="number" step="0.01" value={offset} onChange={event => setOffset(event.target.value)}/></label>
            </div>
            <p className="muted">Positive offsets move notes later; negative offsets move them earlier. Use score tempo if the original video timing is unsuitable. Lyrics keep their own timestamps.</p>
            {audioPreview && <>
              <audio ref={audioRef} key={audioPreview.audio_url} src={audioPreview.audio_url} controls preload="metadata" aria-label="Song audio preview" onError={() => setNotice({type:'error',text:'Audio preview could not be played. Try loading it again or choose local audio.'})}/>
              <div className="sync-controls">
                <label>Measure<select value={measureIndex} onChange={event => setMeasureIndex(Number(event.target.value))}>{audioPreview.measures.map((measure,index) => <option value={index} key={measure.measure}>Measure {measure.measure} · {measure.time.toFixed(2)}s</option>)}</select></label>
                <button disabled={!audioPreview.measures.length} onClick={() => {const player=audioRef.current; if (player && Number.isFinite(player.duration)) setOffset(Number((player.currentTime-audioPreview.measures[measureIndex].time).toFixed(3)));}}>Align measure here</button>
                <button disabled={!audioPreview.measures.length} onClick={() => {if(audioRef.current) audioRef.current.currentTime=Math.max(0,audioPreview.measures[measureIndex].time+Number(offset || 0));}}>Go to aligned measure</button>
                <button onClick={() => setOffset(0)}>Reset offset</button>
              </div>
              <small className="muted">Pause at the start of a measure, select that measure, then align it. This shifts the whole chart; it does not correct tempo drift in a different performance.</small>
            </>}
          </div>
        </section>
        <section className="editor-section lyrics-editor"><div className="section-heading"><h2>Synchronized lyrics</h2><div className="compact-actions"><button onClick={() => guarded(importLyrics)}><Upload size={15}/> Import LRC</button><button onClick={retryLyrics}><RefreshCw size={15}/> Search again</button></div></div><label className="check-row"><input type="checkbox" checked={lyricsEnabled} disabled={!lyrics.length} onChange={event => setLyricsEnabled(event.target.checked)}/> Include {lyrics.length} timed lines</label><p className="muted">{song.lyrics?.provider || song.lyrics?.message || 'No lyrics found. Import an LRC file or retry the search.'}</p>{lyrics.length > 0 && <div className="lyrics-table"><div className="lyric-labels"><span>Seconds</span><span>Lyric line</span></div>{lyrics.map((line,index) => <div className="lyric-row" key={index}><input aria-label={`Time for lyric ${index+1}`} type="number" min="0" step="0.01" value={line.t} onChange={event => updateLyric(index,{t:event.target.value})}/><input aria-label={`Lyric ${index+1}`} value={line.text} onChange={event => updateLyric(index,{text:event.target.value})}/></div>)}</div>}</section>
      </fieldset>
      <footer className="creation-footer"><div><strong>{outputName(form)}</strong><small>Existing files are kept.</small></div><button className="primary" onClick={createFeedPak} disabled={Boolean(busy) || !selectedTracks.length}><Download size={17}/> {batch.length > 1 ? `Create ${batch.length} FeedPaks` : 'Create FeedPak'}</button></footer>
      {results.length > 0 && <section className="creation-results" aria-label="Creation results"><h2>Results</h2>{results.map((row,index) => <div key={index} className={row.ok ? 'result-ok' : 'result-failed'}>{row.ok ? <Check size={16}/> : <XCircle size={16}/>}<span>{row.output_path || row.title}{row.error && <small>{row.error}</small>}{row.warnings?.map(warning => <small key={warning}>{warning}</small>)}</span>{row.ok && <button onClick={() => api.reveal(row.output_path)}>Show in folder</button>}</div>)}</section>}
    </>}
  </section>;
}

function InfoIcon() { return <Music2 size={17}/>; }

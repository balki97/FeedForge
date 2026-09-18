import React from "react";
import { Guitar, FileMusic, FolderOpen, Music2, ArrowUpRight } from "lucide-react";

export default function Home({ navigate, chooseFiles, chooseFolder, items, selectItem }) {
  return <section className="home-workspace">
    <div className="home-intro"><span className="page-kicker">CREATE · REFINE · PLAY</span><h2>Your FeedPak workbench</h2><p>Create from a supported source, or open a package to inspect and refine it.</p></div>
    <div className="home-actions">
      <button onClick={() => navigate("songsterr")}><Music2/><span><strong>Create from Songsterr</strong><small>Tab links, arrangements, audio and lyrics</small></span><ArrowUpRight size={17}/></button>
      <button onClick={() => navigate("workspace")}><Guitar/><span><strong>Convert Rocksmith / PSARC</strong><small>Single files, folders and conversion queues</small></span><ArrowUpRight size={17}/></button>
      <button onClick={chooseFiles}><FileMusic/><span><strong>Open a package</strong><small>Inspect, validate, edit metadata and stems</small></span><ArrowUpRight size={17}/></button>
      <button onClick={chooseFolder}><FolderOpen/><span><strong>Open a library folder</strong><small>Load packages and organize your collection</small></span><ArrowUpRight size={17}/></button>
    </div>
    <div className="section-heading"><h2>This session</h2><span>{items.length} files</span></div>
    {items.length ? <div className="session-list">{items.slice(-12).reverse().map(item => <button key={item.id} onClick={() => selectItem(item)}><FileMusic size={17}/><span><strong>{item.preview?.title || item.name}</strong><small>{item.error || item.preview?.artist || item.path}</small></span><em>{item.status}</em></button>)}</div> : <p className="session-empty">Opened files and generated packages will appear here.</p>}
  </section>;
}

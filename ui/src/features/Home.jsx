import React from "react";
import { Guitar, FileMusic, FolderOpen, Music2, ArrowUpRight } from "lucide-react";

export default function Home({ navigate, chooseFiles, chooseFolder, items, selectItem }) {
  return <section className="home-workspace">
    <div className="home-actions">
      <button onClick={() => navigate("workspace")}><Guitar/><span><strong>Convertor</strong><small>PSARC files</small></span><ArrowUpRight size={17}/></button>
      <button onClick={() => navigate("songsterr")}><Music2/><span><strong>Create from Songsterr</strong><small>Songsterr links</small></span><ArrowUpRight size={17}/></button>
      <button onClick={chooseFiles}><FileMusic/><span><strong>Open a package</strong><small>FeedPak file</small></span><ArrowUpRight size={17}/></button>
      <button onClick={chooseFolder}><FolderOpen/><span><strong>Open a library folder</strong><small>FeedPak folder</small></span><ArrowUpRight size={17}/></button>
    </div>
    <div className="section-heading"><h2>This session</h2><span>{items.length} files</span></div>
    {items.length ? <div className="session-list">{items.slice(-12).reverse().map(item => <button key={item.id} onClick={() => selectItem(item)}><FileMusic size={17}/><span><strong>{item.preview?.title || item.name}</strong><small>{item.error || item.preview?.artist || item.path}</small></span><em>{item.status}</em></button>)}</div> : <p className="session-empty">No files opened yet.</p>}
  </section>;
}

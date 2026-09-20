import React from "react";
import { Guitar, FileMusic, FolderOpen, Music2, ArrowRight, Disc3 } from "lucide-react";
import studio from "../../../assets/home-studio.png";

function Artwork({ item }) {
  const [failed, setFailed] = React.useState(false);
  const path = item.preview?.cover_path;
  return <span className="home-artwork">{path && !failed
    ? <img src={`file:///${path.replaceAll("\\", "/").split("/").map(encodeURIComponent).join("/").replace(/^([A-Za-z])%3A/, "$1:")}`} alt="" onError={() => setFailed(true)} />
    : <Disc3 aria-hidden="true" />}</span>;
}

export default function Home({ navigate, chooseFiles, chooseFolder, items, selectItem }) {
  const recent = items.slice(-8).reverse();
  return <section className="home-workspace">
    <div className="home-hero" style={{ backgroundImage: `url(${studio})` }}>
      <div className="home-hero-content">
        <h1>FeedForge</h1>
        <p className="home-formats">Songsterr <span>·</span> FeedPak</p>
        <div className="home-create-actions">
          <button className="primary" onClick={() => navigate("workspace")}><Guitar size={19}/><span>Convert files</span><ArrowRight size={17}/></button>
          <button onClick={() => navigate("songsterr")}><Music2 size={19}/><span>Create from Songsterr</span><ArrowRight size={17}/></button>
        </div>
        <div className="home-open-actions">
          <button onClick={chooseFiles}><FileMusic size={16}/>Open package</button>
          <button onClick={chooseFolder}><FolderOpen size={16}/>Open library</button>
        </div>
      </div>
    </div>
    <div className="home-session">
      <div className="home-session-heading"><div><h2>On your workbench</h2><span>This session · {items.length} {items.length === 1 ? "file" : "files"}</span></div><button onClick={() => navigate("feedpak")}>Library & editor<ArrowRight size={16}/></button></div>
      {recent.length ? <div className="home-file-list">{recent.map((item, index) => <button className="home-file-row" key={item.id} onClick={() => selectItem(item)} title={item.path}>
        <span className="home-row-number">{String(index + 1).padStart(2, "0")}</span>
        <Artwork item={item}/>
        <span className="home-file-title"><strong>{item.preview?.title || item.name}</strong><small>{item.error || item.preview?.artist || (["queued", "inspecting"].includes(item.status) ? "Loading artwork and details…" : "No artist information")}</small></span>
        <span className="home-file-album">{item.preview?.album || "—"}</span>
        <span className="home-file-type">{item.sourceType === "feedpak" ? "FeedPak" : "PSARC"}</span>
        <span className={`home-file-status status-${item.status}`}>{item.status.replaceAll("-", " ")}</span>
        <ArrowRight className="home-row-arrow" size={17}/>
      </button>)}</div> : <div className="home-empty"><Disc3 size={38} strokeWidth={1}/><h3>No files opened yet</h3><button onClick={chooseFolder}><FolderOpen size={16}/>Open library</button></div>}
    </div>
  </section>;
}

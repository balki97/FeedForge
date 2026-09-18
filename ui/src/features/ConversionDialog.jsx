import { useEffect, useRef } from "react";

export default function ConversionDialog({ request, finish, setup }) {
  const dialog = useRef(null);
  useEffect(() => { dialog.current.showModal(); }, []);
  const { enabled, ready, stems, error } = request;
  return <dialog ref={dialog} className="conversion-dialog" aria-labelledby="conversion-title" onCancel={event => { event.preventDefault(); finish(null); }}>
    <h2 id="conversion-title">{enabled && ready ? "Convert with stems?" : "Convert without stems?"}</h2>
    <p>{enabled && ready ? `Separate ${stems.join(", ")}. The full mix is also included.` : "Only the full mix will be included. Individual instruments won’t be available in the mixer."}</p>
    {enabled && !ready && <p className="dialog-error">{error || "The stem server isn’t ready. Open Tools · stems to install or start it."}</p>}
    <div className="dialog-actions">
      <button autoFocus onClick={() => finish(null)}>Cancel</button>
      {(!enabled || !ready) && <button onClick={setup}>{ready ? "Enable stems in Settings" : "Set up stems"}</button>}
      <button className="primary" onClick={() => finish(enabled && ready)}>Convert {enabled && ready ? "with" : "without"} stems</button>
    </div>
  </dialog>;
}

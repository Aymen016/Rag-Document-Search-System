import React, { useEffect, useRef, useState } from "react";
import { uploadFiles, runIngest, listSources } from "../api.js";

function UploadIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <path d="M17 8l-5-5-5 5" />
      <path d="M12 3v12" />
    </svg>
  );
}

function DocIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6" />
    </svg>
  );
}

function extOf(path) {
  const parts = path.split(".");
  return parts.length > 1 ? parts[parts.length - 1].toLowerCase() : "";
}

/**
 * The plan's Phase 6 "ingestion view": upload files, see parse status and
 * errors. Kept deliberately plain — a non-technical stakeholder should be
 * able to use it without instruction.
 */
export default function IngestPanel() {
  const [subfolder, setSubfolder] = useState("uploaded");
  const [pendingFiles, setPendingFiles] = useState([]);
  const [uploadResult, setUploadResult] = useState(null);
  const [runReport, setRunReport] = useState(null);
  const [sources, setSources] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef(null);

  useEffect(() => {
    refreshSources();
  }, []);

  async function refreshSources() {
    try {
      const data = await listSources();
      setSources(data.documents);
    } catch (err) {
      setError(err.message);
    }
  }

  function addFiles(fileList) {
    const incoming = Array.from(fileList);
    setPendingFiles((prev) => {
      const seen = new Set(prev.map((f) => f.name + f.size));
      const merged = [...prev];
      for (const f of incoming) {
        if (!seen.has(f.name + f.size)) merged.push(f);
      }
      return merged;
    });
  }

  function removeFile(name) {
    setPendingFiles((prev) => prev.filter((f) => f.name !== name));
  }

  async function handleUpload(e) {
    e.preventDefault();
    if (pendingFiles.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const result = await uploadFiles(pendingFiles, subfolder);
      setUploadResult(result);
      setPendingFiles([]);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleRunIngest() {
    setBusy(true);
    setError(null);
    try {
      const report = await runIngest();
      setRunReport(report);
      await refreshSources();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ingest-panel">
      <h2 className="ingest-panel-title">Ingest documents</h2>
      <p className="ingest-panel-subtitle">
        Upload files, run the pipeline, and see exactly what got indexed —
        no CLI needed.
      </p>

      <section className="card">
        <div className="card-header">
          <span className="step-badge">1</span>
          <h3>Upload files</h3>
        </div>
        <p className="hint">Supported: .md .markdown .txt .rst .html .htm .pdf .csv .jsonl</p>
        <form onSubmit={handleUpload} className="upload-form">
          <div className="field-group">
            <label className="field-label" htmlFor="subfolder-input">
              Subfolder
            </label>
            <input
              id="subfolder-input"
              type="text"
              value={subfolder}
              onChange={(e) => setSubfolder(e.target.value)}
              placeholder="e.g. kubernetes-docs"
            />
          </div>

          <div
            className={`dropzone ${dragOver ? "dragover" : ""}`}
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              if (e.dataTransfer.files?.length) addFiles(e.dataTransfer.files);
            }}
          >
            <UploadIcon />
            <p>
              <strong>Click to browse</strong> or drag files here
            </p>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              hidden
              onChange={(e) => {
                if (e.target.files?.length) addFiles(e.target.files);
                e.target.value = "";
              }}
            />
          </div>

          {pendingFiles.length > 0 && (
            <div className="file-chip-list">
              {pendingFiles.map((f) => (
                <span className="file-chip" key={f.name + f.size}>
                  {f.name}
                  <button type="button" onClick={() => removeFile(f.name)} aria-label={`Remove ${f.name}`}>
                    ×
                  </button>
                </span>
              ))}
            </div>
          )}

          <button className="btn" type="submit" disabled={busy || pendingFiles.length === 0} style={{ marginTop: 14 }}>
            {busy ? "Uploading…" : `Upload${pendingFiles.length > 0 ? ` (${pendingFiles.length})` : ""}`}
          </button>
        </form>
        {uploadResult && (
          <p className="status-line">
            <svg viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20 6 9 17l-5-5" />
            </svg>
            Saved {uploadResult.saved.length} file(s) to data/raw/{uploadResult.subfolder}/
          </p>
        )}
      </section>

      <section className="card">
        <div className="card-header">
          <span className="step-badge">2</span>
          <h3>Run ingestion</h3>
        </div>
        <p className="hint">
          Parses everything in data/raw/, chunks it, and rebuilds the search
          index. Re-run this any time you add more files.
        </p>
        <button className="btn" onClick={handleRunIngest} disabled={busy}>
          {busy ? "Running…" : "Run ingestion pipeline"}
        </button>
        {runReport && (
          <div className="ingest-report">
            <p className="summary-line">
              Parsed <strong>{runReport.pipeline.parsed}</strong>, failed{" "}
              <strong>{runReport.pipeline.failed}</strong>, wrote{" "}
              <strong>{runReport.pipeline.chunks}</strong> chunks.
            </p>
            {Object.keys(runReport.pipeline.failure_breakdown || {}).length > 0 && (
              <>
                <p className="hint" style={{ margin: "0 0 2px" }}>
                  Failure breakdown:
                </p>
                <div className="chip-row">
                  {Object.entries(runReport.pipeline.failure_breakdown).map(([reason, count]) => (
                    <span className="chip warn" key={reason}>
                      {reason}: {count}
                    </span>
                  ))}
                </div>
              </>
            )}
            {runReport.index && (
              <p className="status-line">
                <svg viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M20 6 9 17l-5-5" />
                </svg>
                Indexed {runReport.index.chunks_indexed} chunks for search.
              </p>
            )}
          </div>
        )}
      </section>

      <section className="card">
        <div className="card-header">
          <h3>Ingested documents ({sources.length})</h3>
        </div>
        {sources.length === 0 ? (
          <p className="hint">Nothing indexed yet.</p>
        ) : (
          <table className="sources-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Chunks</th>
                <th>Types</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((s) => (
                <tr key={s.source_path}>
                  <td title={s.source_path}>
                    <div className="doc-title-cell">
                      <span className="doc-icon">
                        <DocIcon />
                      </span>
                      {s.doc_title}
                      <span className="type-tag">.{extOf(s.source_path)}</span>
                    </div>
                  </td>
                  <td>{s.chunk_count}</td>
                  <td>{s.content_type_seen.join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {error && <p className="error-banner">{error}</p>}
    </div>
  );
}

import React from "react";

/**
 * Side panel showing the exact source chunk, file name, and section for a
 * clicked citation — the plan's Phase 6 requirement, so a stakeholder can
 * verify a claim against the real document instead of trusting the model.
 */
export default function CitationPanel({ citation, onClose }) {
  if (!citation) {
    return (
      <aside className="citation-panel empty">
        <p>Click a citation marker like [1] in an answer to see its source here.</p>
      </aside>
    );
  }

  return (
    <aside className="citation-panel">
      <div className="citation-panel-header">
        <h3>
          <span className="cite-num">{citation.id}</span>
          Source
        </h3>
        <button className="close-btn" onClick={onClose} aria-label="Close">
          ×
        </button>
      </div>
      <dl className="citation-meta">
        <dt>Document</dt>
        <dd>{citation.doc_title}</dd>
        {citation.section_path && citation.section_path !== "(root)" && (
          <>
            <dt>Section</dt>
            <dd>{citation.section_path}</dd>
          </>
        )}
        {citation.page_number != null && (
          <>
            <dt>Page</dt>
            <dd>{citation.page_number}</dd>
          </>
        )}
        <dt>File</dt>
        <dd className="mono">{citation.source_path}</dd>
      </dl>
      <pre className="citation-text">{citation.text}</pre>
    </aside>
  );
}

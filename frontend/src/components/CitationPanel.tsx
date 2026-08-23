import React, { useState } from 'react';
import { FileText, Database, X } from 'lucide-react';
import type { Citation } from '../types';

interface CitationPanelProps {
  citations: Citation[];
}

export const CitationPanel: React.FC<CitationPanelProps> = ({ citations }) => {
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);

  if (!citations || citations.length === 0) return null;

  const docs = citations.filter((c) => c.type === 'DOCUMENT');
  const ops = citations.filter((c) => c.type === 'OPERATIONAL_DATA');

  return (
    <div className="citations-container" data-testid="citations-container">
      <div className="citations-header-title">Sources & Evidence</div>

      {docs.length > 0 && (
        <div className="citations-section">
          <div className="citations-subheader">Documents</div>
          <div className="citations-list">
            {docs.map((cit, index) => (
              <button
                key={`doc-${index}`}
                className="citation-tag doc-tag"
                onClick={() => setSelectedCitation(cit)}
                data-testid={`citation-tag-${index}`}
              >
                <FileText size={12} className="tag-icon doc-color" />
                <span className="citation-tag-text">
                  📄 {cit.source_name.replace('.pdf', '')}
                  {cit.page ? ` [P.${cit.page}]` : ''}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {ops.length > 0 && (
        <div className="citations-section">
          <div className="citations-subheader">Operational Data</div>
          <div className="citations-list">
            {ops.map((cit, index) => (
              <button
                key={`op-${index}`}
                className="citation-tag op-tag"
                onClick={() => setSelectedCitation(cit)}
                data-testid={`citation-tag-op-${index}`}
              >
                <Database size={12} className="tag-icon op-color" />
                <span className="citation-tag-text">
                  📊 {cit.source_name}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {selectedCitation && (
        <div className="citation-modal-overlay" onClick={() => setSelectedCitation(null)}>
          <div className="citation-modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <span className="modal-title">Source Details</span>
              <button className="close-button" onClick={() => setSelectedCitation(null)}>
                <X size={16} />
              </button>
            </div>
            <div className="modal-body">
              <div className="info-row">
                <span className="info-label">Type:</span>
                <span className="info-value font-bold">{selectedCitation.type}</span>
              </div>
              <div className="info-row">
                <span className="info-label">Identifier:</span>
                <span className="info-value font-mono">{selectedCitation.source_name}</span>
              </div>
              <div className="info-row">
                <span className="info-label">Description:</span>
                <span className="info-value">{selectedCitation.description}</span>
              </div>
              {selectedCitation.page && (
                <div className="info-row">
                  <span className="info-label">Page Reference:</span>
                  <span className="info-value">Page {selectedCitation.page}</span>
                </div>
              )}
              {selectedCitation.authority_status && (
                <div className="info-row">
                  <span className="info-label">Authority/Status:</span>
                  <span className={`info-value status-text ${selectedCitation.authority_status.toLowerCase()}`}>
                    {selectedCitation.authority_status}
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

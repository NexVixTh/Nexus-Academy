import { useState, useEffect } from "react";
import { useApp } from "../../context/AppContext";
import { api } from "../../api/client";
import { DocumentUploader } from "./DocumentUploader";
import type { DocumentConceptItem } from "../../types/api";
import {
  DocumentLibraryIcon,
  SearchIcon,
  SparklesIcon,
  TutorIcon,
  QuizIcon,
  AnalyticsIcon,
  ChevronRightIcon,
  RefreshIcon,
  InfoIcon,
} from "../common/Icons";

export function DocumentLibrary() {
  const {
    documents,
    selectedDocumentId,
    selectDocument,
    setActiveTab,
    refreshDocuments,
    isLoadingDocuments,
    addToast,
  } = useApp();

  const [searchQuery, setSearchQuery] = useState("");
  const [selectedDocConcepts, setSelectedDocConcepts] = useState<DocumentConceptItem[]>([]);
  const [isLoadingConcepts, setIsLoadingConcepts] = useState(false);
  const [activeInspectorDocId, setActiveInspectorDocId] = useState<string | null>(
    selectedDocumentId
  );

  // Filter documents by search
  const filteredDocs = documents.filter((doc) =>
    doc.original_filename.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // Load concepts for inspector whenever activeInspectorDocId changes
  useEffect(() => {
    if (!activeInspectorDocId) {
      setSelectedDocConcepts([]);
      return;
    }
    let active = true;
    async function loadConcepts() {
      setIsLoadingConcepts(true);
      try {
        const res = await api.getDocumentConcepts(activeInspectorDocId!);
        if (active) setSelectedDocConcepts(res.concepts);
      } catch (err) {
        if (active) setSelectedDocConcepts([]);
      } finally {
        if (active) setIsLoadingConcepts(false);
      }
    }
    void loadConcepts();
    return () => {
      active = false;
    };
  }, [activeInspectorDocId]);

  const activeDocObj = documents.find((d) => d.document_id === activeInspectorDocId);

  return (
    <div className="view-container animate-fade-in">
      {/* View Header */}
      <div className="view-header">
        <div>
          <span className="view-eyebrow">SOURCE REPOSITORY</span>
          <h1 className="view-title">Knowledge Library</h1>
          <p className="view-desc">
            All course documents, lecture presentations, and reference texts indexed into NEXUS.
          </p>
        </div>
        <div className="view-header-actions">
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => {
              void refreshDocuments();
              addToast("Refreshed document library.", "info");
            }}
            disabled={isLoadingDocuments}
          >
            <RefreshIcon className={isLoadingDocuments ? "spin" : ""} />
            <span>Sync Library</span>
          </button>
        </div>
      </div>

      {/* Main Grid: Upload Area + Document Shelf */}
      <div className="library-layout">
        <div className="library-main">
          {/* Ingest Dropzone Card */}
          <section className="surface-card p-6 mb-6">
            <h2 className="section-title mb-4">Ingest New Learning Material</h2>
            <DocumentUploader
              onUploadSuccess={(docId) => {
                setActiveInspectorDocId(docId);
              }}
            />
          </section>

          {/* Search and Filters */}
          <div className="library-toolbar">
            <div className="search-bar">
              <SearchIcon className="search-icon" />
              <input
                type="text"
                placeholder="Search documents by title..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                aria-label="Filter documents by name"
              />
              {searchQuery && (
                <button
                  type="button"
                  className="search-clear-btn"
                  onClick={() => setSearchQuery("")}
                >
                  Clear
                </button>
              )}
            </div>
            <div className="library-stats">
              <span>{filteredDocs.length} {filteredDocs.length === 1 ? "document" : "documents"} available</span>
            </div>
          </div>

          {/* Document Cards List */}
          {filteredDocs.length === 0 ? (
            <div className="empty-state-card">
              <DocumentLibraryIcon className="w-12 h-12 text-muted" />
              <h3>No documents found</h3>
              <p>
                {searchQuery
                  ? `No study materials match "${searchQuery}". Try a different keyword.`
                  : "You haven't uploaded any study materials yet. Drag a PDF or PPTX into the box above to get started."}
              </p>
            </div>
          ) : (
            <div className="document-grid">
              {filteredDocs.map((doc) => {
                const isSelected = doc.document_id === selectedDocumentId;
                const isInspecting = doc.document_id === activeInspectorDocId;
                const isPdf = doc.content_type.includes("pdf");

                return (
                  <div
                    key={doc.document_id}
                    className={`document-card ${
                      isSelected ? "document-card-selected" : ""
                    } ${isInspecting ? "document-card-inspecting" : ""}`}
                    onClick={() => setActiveInspectorDocId(doc.document_id)}
                  >
                    <div className="document-card-header">
                      <span className={`format-tag ${isPdf ? "tag-pdf" : "tag-pptx"}`}>
                        {isPdf ? "PDF Document" : "Presentation Slides"}
                      </span>
                      {isSelected && (
                        <span className="active-pill">
                          <span className="active-dot" />
                          Active Study Context
                        </span>
                      )}
                    </div>

                    <h3 className="document-card-title" title={doc.original_filename}>
                      {doc.original_filename}
                    </h3>

                    <div className="document-meta-row">
                      <span>
                        <strong>{doc.record_count}</strong> {isPdf ? "pages" : "slides"}
                      </span>
                      <span>•</span>
                      <span>
                        {new Date(doc.ingested_at).toLocaleDateString(undefined, {
                          month: "short",
                          day: "numeric",
                          year: "numeric",
                        })}
                      </span>
                    </div>

                    <div className="document-card-actions">
                      <button
                        type="button"
                        className={`btn btn-sm ${
                          isSelected ? "btn-primary" : "btn-secondary"
                        }`}
                        onClick={(e) => {
                          e.stopPropagation();
                          selectDocument(doc.document_id);
                          setActiveInspectorDocId(doc.document_id);
                          addToast(`Set "${doc.original_filename}" as active context.`, "success");
                        }}
                      >
                        {isSelected ? "Active Workspace" : "Select Context"}
                      </button>
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          selectDocument(doc.document_id);
                          setActiveTab("tutor");
                        }}
                        title="Open Grounded AI Tutor with this document"
                      >
                        <TutorIcon className="w-3.5 h-3.5" />
                        <span>Tutor</span>
                      </button>
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          selectDocument(doc.document_id);
                          setActiveTab("quiz");
                        }}
                        title="Practice with adaptive quiz on this document"
                      >
                        <QuizIcon className="w-3.5 h-3.5" />
                        <span>Practice</span>
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Sidebar Inspector: Document Details & Extracted Concepts */}
        <aside className="library-inspector">
          {activeDocObj ? (
            <div className="inspector-card">
              <div className="inspector-header">
                <span className="inspector-eyebrow">DOCUMENT INSPECTOR</span>
                <h3 className="inspector-title" title={activeDocObj.original_filename}>
                  {activeDocObj.original_filename}
                </h3>
                <div className="inspector-id">
                  ID: <code>{activeDocObj.document_id}</code>
                </div>
              </div>

              <div className="inspector-stats-grid">
                <div className="stat-tile">
                  <span className="stat-label">Units Indexed</span>
                  <span className="stat-value">{activeDocObj.record_count}</span>
                </div>
                <div className="stat-tile">
                  <span className="stat-label">Concepts Extracted</span>
                  <span className="stat-value">
                    {isLoadingConcepts ? "..." : selectedDocConcepts.length}
                  </span>
                </div>
              </div>

              <div className="inspector-section">
                <div className="inspector-section-header">
                  <span className="section-subtitle">Extracted Concepts & Evidence</span>
                  <SparklesIcon className="w-4 h-4 text-violet" />
                </div>

                {isLoadingConcepts ? (
                  <div className="loading-concepts">
                    <RefreshIcon className="spin w-5 h-5 text-muted" />
                    <span>Analyzing document concepts...</span>
                  </div>
                ) : selectedDocConcepts.length === 0 ? (
                  <p className="no-concepts-text">
                    No explicit concept terms identified yet.
                  </p>
                ) : (
                  <div className="concepts-scrollable-list">
                    {selectedDocConcepts.map((c) => (
                      <div key={c.concept_id} className="concept-inspector-item">
                        <div className="concept-pill-row">
                          <span className="concept-name-pill">{c.name}</span>
                          <span className="concept-loc-tag">
                            {c.source_type === "pdf_page" ? "Page" : "Slide"} {c.page_or_slide_number}
                          </span>
                        </div>
                        <p className="concept-evidence-quote">
                          "{c.evidence_excerpt}"
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="inspector-footer">
                <button
                  type="button"
                  className="btn btn-primary btn-md w-full"
                  onClick={() => {
                    selectDocument(activeDocObj.document_id);
                    setActiveTab("tutor");
                  }}
                >
                  <TutorIcon className="w-4 h-4" />
                  <span>Start Tutor Session</span>
                  <ChevronRightIcon className="w-4 h-4 ml-auto" />
                </button>
              </div>
            </div>
          ) : (
            <div className="inspector-empty">
              <InfoIcon className="w-8 h-8 text-muted" />
              <p>Select a document from the shelf to inspect its extracted concepts and provenance.</p>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

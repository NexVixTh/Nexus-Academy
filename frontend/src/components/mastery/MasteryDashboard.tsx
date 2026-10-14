import { useState, useEffect, useCallback } from "react";
import { useApp } from "../../context/AppContext";
import { api, ApiError } from "../../api/client";
import type {
  LearnerDocumentConceptItem,
  LearnerDocumentProgressResponse,
  LearningStatus,
} from "../../types/api";
import {
  AnalyticsIcon,
  SparklesIcon,
  TargetIcon,
  CheckCircleIcon,
  AlertTriangleIcon,
  RefreshIcon,
  CitationIcon,
  DocumentLibraryIcon,
} from "../common/Icons";
import { ConceptConstellation } from "./ConceptConstellation";

export function MasteryDashboard() {
  const {
    activeDocument,
    learnerId,
    setActiveTab,
    addToast,
  } = useApp();

  const [progressData, setProgressData] = useState<LearnerDocumentProgressResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<"all" | LearningStatus>("all");

  const loadProgress = useCallback(async () => {
    if (!learnerId || !activeDocument) return;
    setIsLoading(true);
    try {
      const data = await api.getLearnerDocumentProgress(learnerId, activeDocument.document_id);
      setProgressData(data);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        // Document or learner not found, try to reload
        console.warn("Progress record not found yet.");
      } else {
        addToast("Could not load mastery analytics.", "error");
      }
    } finally {
      setIsLoading(false);
    }
  }, [learnerId, activeDocument, addToast]);

  useEffect(() => {
    void loadProgress();
  }, [loadProgress]);

  if (!activeDocument) {
    return (
      <div className="view-container animate-fade-in">
        <div className="empty-state-card mt-8">
          <AnalyticsIcon className="w-16 h-16 text-muted mb-3" />
          <h2>No Active Study Material</h2>
          <p>Select or upload a PDF or PPTX to inspect concept mastery intelligence.</p>
          <button
            type="button"
            className="btn btn-primary btn-md mt-4"
            onClick={() => setActiveTab("library")}
          >
            <DocumentLibraryIcon className="w-4 h-4" />
            <span>Open Document Library</span>
          </button>
        </div>
      </div>
    );
  }

  const summary = progressData?.summary;
  const concepts = progressData?.concepts || [];

  const filteredConcepts =
    statusFilter === "all"
      ? concepts
      : concepts.filter((c) => c.learning_status === statusFilter);

  const overallMasteryPct = summary?.overall_mastery_estimate != null
    ? Math.round(summary.overall_mastery_estimate * 100)
    : null;

  return (
    <div className="view-container animate-fade-in">
      {/* Header */}
      <div className="view-header">
        <div>
          <span className="view-eyebrow">LEARNING INTELLIGENCE & MASTERY</span>
          <h1 className="view-title">{activeDocument.original_filename}</h1>
          <p className="view-desc">
            Evidence-calibrated Bayesian mastery estimates and source-grounded remediation recommendations.
          </p>
        </div>
        <div className="view-header-actions">
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => void loadProgress()}
            disabled={isLoading}
          >
            <RefreshIcon className={isLoading ? "spin" : ""} />
            <span>Refresh Analytics</span>
          </button>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={() => setActiveTab("quiz")}
          >
            <TargetIcon className="w-3.5 h-3.5" />
            <span>Target Weak Concepts</span>
          </button>
        </div>
      </div>

      {/* Summary Scorecard Row */}
      <div className="analytics-summary-grid mb-8">
        {/* Overall Mastery Meter */}
        <div className="metric-card surface-card p-6">
          <span className="metric-eyebrow">OVERALL DOCUMENT MASTERY</span>
          <div className="metric-value-row">
            <span className="metric-large-number">
              {overallMasteryPct != null ? `${overallMasteryPct}%` : "—"}
            </span>
            <span className="metric-sublabel">
              {overallMasteryPct != null
                ? overallMasteryPct >= 70
                  ? "Proficient"
                  : overallMasteryPct >= 50
                  ? "In Progress"
                  : "Needs Remediation"
                : "No attempts recorded"}
            </span>
          </div>
          <div className="progress-bar-track mt-3">
            <div
              className="progress-bar-fill"
              style={{ width: `${overallMasteryPct || 0}%` }}
            />
          </div>
          <p className="metric-footnote mt-3">
            Bayesian Beta prior (α=2, β=2) prevents false confidence on small sample sizes.
          </p>
        </div>

        {/* Coverage Stat */}
        <div className="metric-card surface-card p-6">
          <span className="metric-eyebrow">CURRICULUM COVERAGE</span>
          <div className="metric-value-row">
            <span className="metric-large-number">
              {summary ? `${summary.attempted_concept_count} / ${summary.total_document_concepts}` : "—"}
            </span>
            <span className="metric-sublabel">concepts tested</span>
          </div>
          <div className="progress-bar-track mt-3">
            <div
              className="progress-bar-fill fill-cyan"
              style={{
                width: summary
                  ? `${(summary.attempted_concept_count / Math.max(summary.total_document_concepts, 1)) * 100}%`
                  : "0%",
              }}
            />
          </div>
          <p className="metric-footnote mt-3">
            {summary?.not_attempted_concept_count || 0} unattempted concepts waiting for baseline diagnostic test.
          </p>
        </div>

        {/* Question Performance */}
        <div className="metric-card surface-card p-6">
          <span className="metric-eyebrow">EXAM ACCURACY</span>
          <div className="metric-value-row">
            <span className="metric-large-number">
              {progressData && progressData.question_attempt_count > 0
                ? `${Math.round(progressData.correct_answer_rate * 100)}%`
                : "—"}
            </span>
            <span className="metric-sublabel">
              {progressData?.correct_question_count || 0} of {progressData?.question_attempt_count || 0} correct
            </span>
          </div>
          <p className="metric-footnote mt-5">
            Total quizzes submitted: <strong>{progressData?.quiz_attempt_count || 0}</strong>
          </p>
        </div>
      </div>

      {/* Interactive Concept Constellation Knowledge Graph */}
      <ConceptConstellation concepts={concepts} />

      {/* Filter Tabs by Status */}
      <div className="mastery-filters-toolbar mb-6">
        <div className="filter-pill-group">
          <button
            type="button"
            className={`filter-pill ${statusFilter === "all" ? "filter-pill-active" : ""}`}
            onClick={() => setStatusFilter("all")}
          >
            All Concepts ({concepts.length})
          </button>
          <button
            type="button"
            className={`filter-pill pill-struggling ${
              statusFilter === "struggling" ? "filter-pill-active" : ""
            }`}
            onClick={() => setStatusFilter("struggling")}
          >
            Struggling ({summary?.struggling_concept_count || 0})
          </button>
          <button
            type="button"
            className={`filter-pill pill-learning ${
              statusFilter === "learning" ? "filter-pill-active" : ""
            }`}
            onClick={() => setStatusFilter("learning")}
          >
            Learning ({summary?.learning_concept_count || 0})
          </button>
          <button
            type="button"
            className={`filter-pill pill-proficient ${
              statusFilter === "proficient" ? "filter-pill-active" : ""
            }`}
            onClick={() => setStatusFilter("proficient")}
          >
            Proficient ({summary?.proficient_concept_count || 0})
          </button>
          <button
            type="button"
            className={`filter-pill pill-unattempted ${
              statusFilter === "not_attempted" ? "filter-pill-active" : ""
            }`}
            onClick={() => setStatusFilter("not_attempted")}
          >
            Not Attempted ({summary?.not_attempted_concept_count || 0})
          </button>
        </div>
      </div>

      {/* Concept Items Grid */}
      {filteredConcepts.length === 0 ? (
        <div className="empty-state-card">
          <p>No concepts matching this status filter.</p>
        </div>
      ) : (
        <div className="concept-mastery-grid">
          {filteredConcepts.map((c) => {
            const masteryPct = c.mastery_estimate != null ? Math.round(c.mastery_estimate * 100) : null;
            return (
              <div
                key={c.concept_id}
                className={`concept-mastery-card status-border-${c.learning_status}`}
              >
                <div className="concept-card-top">
                  <span className="concept-title">{c.concept_label}</span>
                  <span className={`status-badge badge-${c.learning_status}`}>
                    {c.learning_status.replace("_", " ").toUpperCase()}
                  </span>
                </div>

                {/* Mastery Gauge */}
                <div className="mastery-num-row mt-2">
                  <span className="mastery-pct">
                    {masteryPct != null ? `${masteryPct}%` : "—"}
                  </span>
                  <span className="mastery-attempts-text">
                    {c.attempt_count === 0
                      ? "Unattempted"
                      : `${c.correct_count} of ${c.attempt_count} correct`}
                  </span>
                </div>

                {/* Pedagogical Explanation */}
                <div className="concept-explanation-box mt-3">
                  <p className="explanation-text">{c.explanation}</p>
                </div>

                {/* Source Grounded Action */}
                <div className="concept-action-box mt-3">
                  <span className="action-label">RECOMMENDED ACTION:</span>
                  <p className="action-text">{c.recommended_action}</p>
                </div>

                {/* Source Provenance */}
                <div className="concept-provenance-box mt-3">
                  <div className="provenance-loc">
                    <CitationIcon className="w-3 h-3 text-cyan" />
                    <span>
                      {c.source_type === "pdf_page" ? "Page" : "Slide"} {c.page_or_slide_number}:
                    </span>
                  </div>
                  <blockquote className="provenance-excerpt">
                    "{c.evidence_excerpt}"
                  </blockquote>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

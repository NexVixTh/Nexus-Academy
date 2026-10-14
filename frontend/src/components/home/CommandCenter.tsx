import { useEffect, useState } from "react";
import { useApp } from "../../context/AppContext";
import { api } from "../../api/client";
import { DocumentUploader } from "../documents/DocumentUploader";
import { GamificationPanel } from "../gamification/GamificationPanel";
import type { LearnerDocumentProgressResponse, LearnerProgressResponse } from "../../types/api";
import {
  SparklesIcon,
  TutorIcon,
  QuizIcon,
  AnalyticsIcon,
  DocumentLibraryIcon,
  CheckCircleIcon,
  ChevronRightIcon,
  CpuIcon,
  TargetIcon,
  AlertTriangleIcon,
} from "../common/Icons";

export function CommandCenter() {
  const {
    activeDocument,
    documents,
    learnerId,
    setActiveTab,
    backendStatus,
    modelStatus,
    setShowHackathonGuide,
    setShowOnboarding,
  } = useApp();

  const [learnerProgress, setLearnerProgress] = useState<LearnerProgressResponse | null>(null);
  const [docProgress, setDocProgress] = useState<LearnerDocumentProgressResponse | null>(null);

  useEffect(() => {
    if (!learnerId) return;
    let active = true;
    async function loadStats() {
      try {
        const prog = await api.getLearnerProgress(learnerId!);
        if (active) setLearnerProgress(prog);
      } catch {
        // learner might have no progress yet
      }

      if (activeDocument) {
        try {
          const dp = await api.getLearnerDocumentProgress(learnerId!, activeDocument.document_id);
          if (active) setDocProgress(dp);
        } catch {
          // document progress optional
        }
      }
    }
    void loadStats();
    return () => {
      active = false;
    };
  }, [learnerId, activeDocument]);

  const tutorTask = modelStatus?.tasks.find((t) => t.task === "tutor");
  const modelProviderLabel = tutorTask?.enabled
    ? `${tutorTask.provider.toUpperCase()} (${tutorTask.model || "live"})`
    : "Deterministic Extractive (Offline Fallback)";

  // Compute Next Best Action based on actual concept mastery
  const strugglingConcept = docProgress?.concepts.find((c) => c.learning_status === "struggling");
  const unattemptedConcept = docProgress?.concepts.find((c) => c.learning_status === "not_attempted");

  return (
    <div className="command-center animate-fade-in">
      {/* Hero Welcome Banner */}
      <section className="hero-section">
        <div className="hero-glow" />
        <div className="hero-badge-row flex items-center justify-between mb-4">
          <div className="hero-badge">
            <SparklesIcon className="w-4 h-4 text-cyan" />
            <span>MULTIMODAL AI ADAPTIVE TUTORING STUDIO</span>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => setShowOnboarding(true)}
            >
              How it Works
            </button>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => setShowHackathonGuide(true)}
            >
              <SparklesIcon className="w-3.5 h-3.5" />
              <span>Fast-Track Demo Guide</span>
            </button>
          </div>
        </div>

        <h1 className="hero-title">
          Evidence-Grounded Intelligence for Personalized Learning
        </h1>

        <p className="hero-subtitle">
          Transform your textbooks and slide decks into an interactive, citation-backed AI tutor with adaptive practice, transparent Bayesian mastery, and persisted achievements.
        </p>

        {/* Real Metrics Banner */}
        <div className="hero-metrics-row">
          <div className="hero-metric-item">
            <span className="hero-metric-value">{documents.length}</span>
            <span className="hero-metric-label">Ingested Documents</span>
          </div>
          <div className="hero-metric-divider" />
          <div className="hero-metric-item">
            <span className="hero-metric-value">
              {learnerProgress?.question_attempt_count || 0}
            </span>
            <span className="hero-metric-label">Questions Attempted</span>
          </div>
          <div className="hero-metric-divider" />
          <div className="hero-metric-item">
            <span className="hero-metric-value">
              {learnerProgress && learnerProgress.question_attempt_count > 0
                ? `${Math.round(learnerProgress.correct_answer_rate * 100)}%`
                : "—"}
            </span>
            <span className="hero-metric-label">Overall Accuracy</span>
          </div>
          <div className="hero-metric-divider" />
          <div className="hero-metric-item">
            <span className="hero-metric-value">
              {learnerProgress?.concepts_attempted.length || 0}
            </span>
            <span className="hero-metric-label">Concepts Explored</span>
          </div>
        </div>
      </section>

      {/* Next Best Learning Action Recommendation */}
      {activeDocument && (
        <section className="next-action-card surface-card p-6 mb-8 border-violet">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <div className="action-icon-pill">
                <TargetIcon className="w-5 h-5 text-violet" />
              </div>
              <div>
                <span className="text-2xs font-mono font-bold text-cyan tracking-wider block">
                  RECOMMENDED NEXT ACTION
                </span>
                <h3 className="text-lg font-bold font-serif text-primary mt-0.5">
                  {strugglingConcept
                    ? `Remediate Weak Concept: "${strugglingConcept.concept_label}"`
                    : unattemptedConcept
                    ? `Diagnostic Baseline: Practice "${unattemptedConcept.concept_label}"`
                    : `Review Mastered Concepts in "${activeDocument.original_filename}"`}
                </h3>
                <p className="text-xs text-secondary mt-1">
                  {strugglingConcept
                    ? strugglingConcept.recommended_action
                    : unattemptedConcept
                    ? unattemptedConcept.recommended_action
                    : "You have strong mastery across all explored concepts. Launch an adaptive challenge session to test retention."}
                </p>
              </div>
            </div>

            <button
              type="button"
              className="btn btn-primary btn-md flex-shrink-0"
              onClick={() => setActiveTab("quiz")}
            >
              <span>Practice Now</span>
              <ChevronRightIcon className="w-4 h-4 ml-1" />
            </button>
          </div>
        </section>
      )}

      {/* Gamification System Showcase */}
      <section className="gamification-section mb-8">
        <GamificationPanel />
      </section>

      {/* Active Material or Upload Section */}
      <section className="active-hub-section mb-8">
        {activeDocument ? (
          <div className="active-card surface-card p-6">
            <div className="active-card-header">
              <div>
                <span className="active-card-eyebrow">ACTIVE LEARNING CONTEXT</span>
                <h2 className="active-card-title">{activeDocument.original_filename}</h2>
              </div>
              <span className="active-format-badge">
                {activeDocument.content_type.includes("pdf") ? "PDF Document" : "Presentation Slides"}
              </span>
            </div>

            <p className="active-card-desc">
              Indexed with {activeDocument.record_count}{" "}
              {activeDocument.content_type.includes("presentationml") ? "slides" : "pages"}. Ready for question answering, adaptive tests, and concept mastery tracking.
            </p>

            <div className="active-actions-row">
              <button
                type="button"
                className="btn btn-primary btn-md"
                onClick={() => setActiveTab("tutor")}
              >
                <TutorIcon className="w-4 h-4" />
                <span>Ask AI Tutor</span>
                <ChevronRightIcon className="w-4 h-4 ml-auto" />
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-md"
                onClick={() => setActiveTab("quiz")}
              >
                <QuizIcon className="w-4 h-4" />
                <span>Adaptive Practice</span>
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-md"
                onClick={() => setActiveTab("mastery")}
              >
                <AnalyticsIcon className="w-4 h-4" />
                <span>View Mastery</span>
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setActiveTab("library")}
              >
                Switch Document
              </button>
            </div>
          </div>
        ) : (
          <div className="surface-card p-6">
            <h2 className="section-title mb-2">Start Learning by Ingesting Study Material</h2>
            <p className="text-sm text-muted mb-4">
              Upload a syllabus, lecture presentation, or reference document to unlock grounded tutoring and adaptive quizzes.
            </p>
            <DocumentUploader />
          </div>
        )}
      </section>

      {/* Feature Navigation Cards Grid */}
      <section className="features-grid mb-8">
        <div
          className="feature-card surface-card p-6 clickable"
          onClick={() => setActiveTab("tutor")}
          role="button"
          tabIndex={0}
        >
          <div className="feature-icon-wrapper icon-violet">
            <TutorIcon className="w-6 h-6" />
          </div>
          <h3 className="feature-title">Source-Grounded AI Tutor</h3>
          <p className="feature-desc">
            Ask any question. Answers cite exact pages or slides with verified excerpts. If evidence is missing, it honestly abstains without hallucinating.
          </p>
          <span className="feature-link">
            Open Tutor Studio <ChevronRightIcon className="w-4 h-4" />
          </span>
        </div>

        <div
          className="feature-card surface-card p-6 clickable"
          onClick={() => setActiveTab("quiz")}
          role="button"
          tabIndex={0}
        >
          <div className="feature-icon-wrapper icon-cyan">
            <TargetIcon className="w-6 h-6" />
          </div>
          <h3 className="feature-title">Adaptive Practice Engine</h3>
          <p className="feature-desc">
            Takes questions targeting concepts where your mastery is lowest, adjusts distractor difficulty, and avoids repeating questions you've already answered.
          </p>
          <span className="feature-link">
            Launch Practice <ChevronRightIcon className="w-4 h-4" />
          </span>
        </div>

        <div
          className="feature-card surface-card p-6 clickable"
          onClick={() => setActiveTab("mastery")}
          role="button"
          tabIndex={0}
        >
          <div className="feature-icon-wrapper icon-emerald">
            <AnalyticsIcon className="w-6 h-6" />
          </div>
          <h3 className="feature-title">Mastery Intelligence</h3>
          <p className="feature-desc">
            Explainable Bayesian learning progression with transparent 4-state status badges and source-grounded remediation recommendations.
          </p>
          <span className="feature-link">
            Inspect Analytics <ChevronRightIcon className="w-4 h-4" />
          </span>
        </div>
      </section>

      {/* The 4-Step Learning Loop Visual */}
      <section className="learning-loop-card surface-card p-8">
        <span className="inspector-eyebrow">THE NEXUS LEARNING ARCHITECTURE</span>
        <h2 className="text-xl font-semibold mt-1 mb-4">How NEXUS ACADEMY Powers Grounded Learning</h2>

        <div className="loop-steps-grid">
          <div className="loop-step">
            <span className="step-num">01</span>
            <h4 className="step-title">Ingest & Index</h4>
            <p className="step-desc">
              PyMuPDF and python-pptx extract clean structured pages, slides, and tables with full text indexing.
            </p>
          </div>
          <div className="loop-step">
            <span className="step-num">02</span>
            <h4 className="step-title">Extract Concepts</h4>
            <p className="step-desc">
              Identifies domain concepts, definitions, and causal chains, forming a knowledge map.
            </p>
          </div>
          <div className="loop-step">
            <span className="step-num">03</span>
            <h4 className="step-title">Grounded QA</h4>
            <p className="step-desc">
              BM25 retrieval + live LLM router synthesizes answers with verifiable citations and zero hallucination.
            </p>
          </div>
          <div className="loop-step">
            <span className="step-num">04</span>
            <h4 className="step-title">Adaptive Feedback</h4>
            <p className="step-desc">
              Dynamic Beta-prior mastery tracking recalculates weakness weights after every quiz submission.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}

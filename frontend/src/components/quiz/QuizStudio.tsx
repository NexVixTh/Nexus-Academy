import { useState, useEffect, useRef } from "react";
import { useApp } from "../../context/AppContext";
import { api, ApiError } from "../../api/client";
import type {
  QuizQuestion,
  QuizResponse,
  QuizSubmissionResponse,
} from "../../types/api";
import {
  QuizIcon,
  SparklesIcon,
  CheckCircleIcon,
  XCircleIcon,
  AlertTriangleIcon,
  ChevronRightIcon,
  ArrowLeftIcon,
  RefreshIcon,
  CitationIcon,
  TargetIcon,
  DocumentLibraryIcon,
  ClockIcon,
  ZapIcon,
  TutorIcon,
} from "../common/Icons";

type QuizMode = "setup" | "answering" | "results";

export function QuizStudio() {
  const {
    activeDocument,
    learnerId,
    setActiveTab,
    addToast,
    refreshDocuments,
    refreshGamification,
    setPendingTutorPrompt,
  } = useApp();

  const [mode, setMode] = useState<QuizMode>("setup");
  const [questionCount, setQuestionCount] = useState<number>(5);
  const [isAdaptiveMode, setIsAdaptiveMode] = useState<boolean>(true);
  const [isChallengeMode, setIsChallengeMode] = useState<boolean>(false);
  const [timeLeft, setTimeLeft] = useState<number>(30);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Active quiz state
  const [activeQuiz, setActiveQuiz] = useState<QuizResponse | null>(null);
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);
  const [selectedAnswers, setSelectedAnswers] = useState<Record<string, "A" | "B" | "C" | "D">>({});
  const [submissionResult, setSubmissionResult] = useState<QuizSubmissionResponse | null>(null);
  const [generationLimitation, setGenerationLimitation] = useState<string | null>(null);

  // Keyboard shortcut listener for options (A, B, C, D)
  useEffect(() => {
    if (mode !== "answering" || !activeQuiz) return;
    const currentQ = activeQuiz.questions[currentQuestionIndex];
    if (!currentQ) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      // Ignore if typing inside input or textarea
      if (
        document.activeElement?.tagName === "INPUT" ||
        document.activeElement?.tagName === "TEXTAREA"
      ) {
        return;
      }
      const key = e.key.toUpperCase();
      if (key === "A" || key === "B" || key === "C" || key === "D") {
        e.preventDefault();
        setSelectedAnswers((prev) => ({
          ...prev,
          [currentQ.question_id]: key as "A" | "B" | "C" | "D",
        }));
      } else if (e.key === "ArrowRight" || e.key === "Enter") {
        if (currentQuestionIndex < activeQuiz.questions.length - 1) {
          setCurrentQuestionIndex((prev) => prev + 1);
        }
      } else if (e.key === "ArrowLeft") {
        if (currentQuestionIndex > 0) {
          setCurrentQuestionIndex((prev) => prev - 1);
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [mode, activeQuiz, currentQuestionIndex]);

  const startQuiz = async (adaptive: boolean = isAdaptiveMode) => {
    if (!activeDocument) return;
    setIsGenerating(true);
    setGenerationLimitation(null);
    setSelectedAnswers({});
    setSubmissionResult(null);
    setCurrentQuestionIndex(0);

    try {
      let res: QuizResponse;
      if (adaptive && learnerId) {
        res = await api.generateAdaptiveQuiz(learnerId, activeDocument.document_id, questionCount);
      } else {
        res = await api.generateQuiz(activeDocument.document_id, questionCount, learnerId);
      }

      if (res.questions.length === 0) {
        addToast(res.limitation || "No reliable questions could be generated from this document.", "error");
        setGenerationLimitation(res.limitation);
        return;
      }

      if (res.limitation) {
        setGenerationLimitation(res.limitation);
      }

      setActiveQuiz(res);
      setMode("answering");
      addToast(
        adaptive
          ? `Adaptive quiz prepared prioritizing your weak concepts.`
          : `Standard quiz prepared (${res.questions.length} questions).`,
        "success"
      );
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail || err.message : "Failed to generate quiz.";
      addToast(msg, "error");
    } finally {
      setIsGenerating(false);
    }
  };

  const handleSubmitQuiz = async () => {
    if (!activeQuiz || !activeDocument || isSubmitting) return;

    const answersPayload = Object.entries(selectedAnswers).map(
      ([question_id, selected_option_id]) => ({
        question_id,
        selected_option_id,
      })
    );

    setIsSubmitting(true);
    try {
      const result = await api.submitQuiz(activeDocument.document_id, {
        quiz_id: activeQuiz.quiz_id,
        learner_id: learnerId,
        answers: answersPayload,
      });

      setSubmissionResult(result);
      setMode("results");
      void refreshGamification();
      addToast(
        `Quiz submitted! Score: ${result.correct_count}/${result.answered_count} (${(
          result.score_percentage_of_answered * 100
        ).toFixed(0)}%)`,
        "success"
      );
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail || err.message : "Submission failed.";
      addToast(msg, "error");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSubmitRef = useRef(handleSubmitQuiz);
  handleSubmitRef.current = handleSubmitQuiz;

  // Challenge Mode Timer Effect: 30s per question countdown
  useEffect(() => {
    if (mode !== "answering" || !isChallengeMode || !activeQuiz) return;

    setTimeLeft(30);
    const interval = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev <= 1) {
          if (currentQuestionIndex < activeQuiz.questions.length - 1) {
            setCurrentQuestionIndex((curr) => curr + 1);
            return 30;
          } else {
            clearInterval(interval);
            void handleSubmitRef.current();
            return 0;
          }
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [mode, isChallengeMode, currentQuestionIndex, activeQuiz]);

  if (!activeDocument) {
    return (
      <div className="view-container animate-fade-in">
        <div className="empty-state-card mt-8">
          <QuizIcon className="w-16 h-16 text-muted mb-3" />
          <h2>No Active Study Material</h2>
          <p>Select or upload a PDF or PPTX to begin adaptive practice testing.</p>
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

  // MODE 1: SETUP SCREEN
  if (mode === "setup") {
    return (
      <div className="view-container animate-fade-in">
        <div className="view-header">
          <div>
            <span className="view-eyebrow">ASSESSMENT & RETENTION</span>
            <h1 className="view-title">Adaptive Practice Studio</h1>
            <p className="view-desc">
              Test your understanding of <strong>{activeDocument.original_filename}</strong> with concept-calibrated questions.
            </p>
          </div>
        </div>

        <div className="quiz-setup-grid">
          {/* Main Setup Card */}
          <div className="surface-card p-6">
            <h2 className="text-xl font-semibold mb-4">Configure Practice Session</h2>

            {/* Mode Selector */}
            <div className="setup-mode-toggle-group mb-6">
              <button
                type="button"
                className={`mode-card ${isAdaptiveMode ? "mode-card-active" : ""}`}
                onClick={() => setIsAdaptiveMode(true)}
              >
                <div className="mode-card-header">
                  <TargetIcon className="w-5 h-5 text-violet" />
                  <span className="mode-card-title">Adaptive Practice</span>
                  <span className="recommended-badge">Recommended</span>
                </div>
                <p className="mode-card-desc">
                  Prioritizes concepts where your mastery is lowest, avoids repeating questions you've seen, and adjusts distractor difficulty.
                </p>
              </button>

              <button
                type="button"
                className={`mode-card ${!isAdaptiveMode ? "mode-card-active" : ""}`}
                onClick={() => setIsAdaptiveMode(false)}
              >
                <div className="mode-card-header">
                  <QuizIcon className="w-5 h-5 text-cyan" />
                  <span className="mode-card-title">Standard Comprehensive</span>
                </div>
                <p className="mode-card-desc">
                  Draws evenly across all extracted concepts in this document without personalized weighting.
                </p>
              </button>
            </div>

            {/* Question Count */}
            <div className="mb-6">
              <label className="input-label mb-2 block">Number of Questions</label>
              <div className="question-count-selector">
                {[3, 5, 10].map((num) => (
                  <button
                    key={num}
                    type="button"
                    className={`count-pill ${questionCount === num ? "count-pill-active" : ""}`}
                    onClick={() => setQuestionCount(num)}
                  >
                    {num} Questions
                  </button>
                ))}
              </div>
            </div>

            {/* Challenge Mode (Timed Sprint) Toggle */}
            <div className="challenge-mode-container mb-6 p-3 rounded-xl border border-border bg-surface-subtle">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className={`p-2 rounded-lg ${isChallengeMode ? "bg-amber-muted text-amber" : "bg-surface-elevated text-muted"}`}>
                    <ZapIcon className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-sm">Challenge Sprint</span>
                      <span className="challenge-speed-badge">30s / Q</span>
                    </div>
                    <p className="text-xs text-muted">
                      Countdown timer for rapid recall. Test yourself under timed pressure!
                    </p>
                  </div>
                </div>
                <label className="toggle-switch" aria-label="Toggle Challenge Sprint">
                  <input
                    type="checkbox"
                    checked={isChallengeMode}
                    onChange={(e) => setIsChallengeMode(e.target.checked)}
                  />
                  <span className="toggle-slider"></span>
                </label>
              </div>
            </div>

            {/* Limitation Notice if any */}
            {generationLimitation && (
              <div className="alert-box alert-error mb-4">
                <AlertTriangleIcon className="w-4 h-4 flex-shrink-0" />
                <span>{generationLimitation}</span>
              </div>
            )}

            {/* Start CTA */}
            <button
              type="button"
              className="btn btn-primary btn-lg w-full"
              onClick={() => void startQuiz()}
              disabled={isGenerating}
            >
              {isGenerating ? (
                <>
                  <RefreshIcon className="w-5 h-5 spin" />
                  <span>Synthesizing Concept Questions...</span>
                </>
              ) : (
                <>
                  <SparklesIcon className="w-5 h-5" />
                  <span>Launch Practice Session</span>
                  <ChevronRightIcon className="w-4 h-4 ml-auto" />
                </>
              )}
            </button>
          </div>

          {/* Quick Context Card */}
          <div className="surface-card p-6 flex flex-col justify-between">
            <div>
              <span className="inspector-eyebrow">EXAM INTEGRITY PROMISE</span>
              <h3 className="text-lg font-medium mt-1 mb-3">Honest, Unbiased Scoring</h3>
              <ul className="integrity-checklist">
                <li>
                  <CheckCircleIcon className="w-4 h-4 text-emerald" />
                  <span>Answer keys are strictly encrypted & never leaked in client state before submission.</span>
                </li>
                <li>
                  <CheckCircleIcon className="w-4 h-4 text-emerald" />
                  <span>Every question is directly traceable to an excerpt on a specific slide or page.</span>
                </li>
                <li>
                  <CheckCircleIcon className="w-4 h-4 text-emerald" />
                  <span>Results dynamically update your concept mastery profile in SQLite.</span>
                </li>
              </ul>
            </div>

            <div className="integrity-footer-box">
              <span className="text-xs text-muted">Learner Profile:</span>
              <code className="text-xs block text-cyan truncate mt-0.5">{learnerId}</code>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // MODE 2: ANSWERING QUESTIONS SCREEN
  if (mode === "answering" && activeQuiz) {
    const currentQ: QuizQuestion = activeQuiz.questions[currentQuestionIndex];
    const totalQ = activeQuiz.questions.length;
    const selectedOpt = selectedAnswers[currentQ.question_id];
    const isAnswered = Boolean(selectedOpt);
    const answeredCount = Object.keys(selectedAnswers).length;

    return (
      <div className="view-container animate-fade-in">
        {/* Quiz Progress Top Bar */}
        <div className="quiz-session-topbar">
          <div className="quiz-session-meta">
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => {
                if (confirm("Quit active practice session? Progress will not be recorded.")) {
                  setMode("setup");
                }
              }}
            >
              <ArrowLeftIcon className="w-4 h-4" />
              <span>Exit Practice</span>
            </button>
            <span className="session-divider">/</span>
            <span className="session-badge">
              Question {currentQuestionIndex + 1} of {totalQ}
            </span>
            <span className={`difficulty-badge diff-${currentQ.difficulty}`}>
              {currentQ.difficulty.toUpperCase()}
            </span>
            {isChallengeMode && (
              <div className={`challenge-timer-badge ${timeLeft <= 10 ? "timer-urgent" : ""}`}>
                <ClockIcon className="w-4 h-4" />
                <span>{timeLeft}s</span>
              </div>
            )}
          </div>

          {/* Question Nav Pills */}
          <div className="question-dots-nav">
            {activeQuiz.questions.map((q, idx) => {
              const answered = Boolean(selectedAnswers[q.question_id]);
              const isCurrent = idx === currentQuestionIndex;
              return (
                <button
                  key={q.question_id}
                  type="button"
                  className={`dot-pill ${isCurrent ? "dot-pill-current" : ""} ${
                    answered ? "dot-pill-answered" : ""
                  }`}
                  onClick={() => setCurrentQuestionIndex(idx)}
                  title={`Question ${idx + 1}`}
                  aria-label={`Jump to question ${idx + 1}`}
                >
                  {idx + 1}
                </button>
              );
            })}
          </div>
        </div>

        {/* Challenge Mode Countdown Bar */}
        {isChallengeMode && (
          <div className="challenge-timer-track">
            <div
              className={`challenge-timer-fill ${timeLeft <= 10 ? "challenge-timer-fill-urgent" : ""}`}
              style={{ width: `${(timeLeft / 30) * 100}%` }}
            />
          </div>
        )}

        {/* Question Card */}
        <div className="question-runner-card">
          <div className="question-header">
            <span className="concept-focus-tag">
              CONCEPT: <strong>{currentQ.concept_label}</strong>
            </span>
            <span className="provenance-tag">
              Source: {currentQ.source_type === "pdf_page" ? "Page" : "Slide"}{" "}
              {currentQ.page_or_slide_number}
            </span>
          </div>

          <h2 className="question-prompt-text">{currentQ.question_text}</h2>

          {/* Options Grid */}
          <div className="options-grid" role="radiogroup" aria-label="Quiz options">
            {currentQ.options.map((opt) => {
              const isSelected = selectedOpt === opt.option_id;
              return (
                <button
                  key={opt.option_id}
                  type="button"
                  className={`option-card ${isSelected ? "option-card-selected" : ""}`}
                  onClick={() => {
                    setSelectedAnswers((prev) => ({
                      ...prev,
                      [currentQ.question_id]: opt.option_id,
                    }));
                  }}
                  role="radio"
                  aria-checked={isSelected}
                >
                  <span className="option-key-badge">{opt.option_id}</span>
                  <span className="option-text">{opt.text}</span>
                </button>
              );
            })}
          </div>

          <div className="keyboard-hint">
            <span>Tip: Press <strong>A</strong>, <strong>B</strong>, <strong>C</strong>, or <strong>D</strong> on your keyboard to select an option.</span>
          </div>
        </div>

        {/* Bottom Navigation Dock */}
        <div className="quiz-session-dock">
          <button
            type="button"
            className="btn btn-secondary btn-md"
            disabled={currentQuestionIndex === 0}
            onClick={() => setCurrentQuestionIndex((prev) => prev - 1)}
          >
            <ArrowLeftIcon className="w-4 h-4" />
            <span>Previous</span>
          </button>

          <div className="dock-status">
            <span>
              {answeredCount} of {totalQ} answered
            </span>
          </div>

          {currentQuestionIndex < totalQ - 1 ? (
            <button
              type="button"
              className="btn btn-primary btn-md"
              onClick={() => setCurrentQuestionIndex((prev) => prev + 1)}
            >
              <span>Next Question</span>
              <ChevronRightIcon className="w-4 h-4" />
            </button>
          ) : (
            <button
              type="button"
              className="btn btn-primary btn-md"
              onClick={handleSubmitQuiz}
              disabled={isSubmitting}
            >
              {isSubmitting ? (
                <>
                  <RefreshIcon className="w-4 h-4 spin" />
                  <span>Submitting & Scoring...</span>
                </>
              ) : (
                <>
                  <CheckCircleIcon className="w-4 h-4" />
                  <span>Submit Practice Session</span>
                </>
              )}
            </button>
          )}
        </div>
      </div>
    );
  }

  // MODE 3: RESULTS & SCORECARD SCREEN
  if (mode === "results" && submissionResult && activeQuiz) {
    const scorePct = Math.round(submissionResult.score_percentage_of_answered * 100);
    const hasStruggling = submissionResult.results.some((r) => r.is_correct === false);

    return (
      <div className="view-container animate-fade-in">
        {/* Results Banner */}
        <div className="scorecard-banner surface-card p-8 mb-6">
          <div className="scorecard-layout">
            <div className="scorecard-metric">
              <span className="scorecard-label">SESSION ACCURACY</span>
              <div className="scorecard-number-row">
                <span className="scorecard-number">{scorePct}%</span>
                <span className="scorecard-fraction">
                  ({submissionResult.correct_count} of {submissionResult.answered_count} correct)
                </span>
              </div>
              <p className="scorecard-verdict">
                {scorePct >= 80
                  ? "Outstanding mastery! Your grasp on these core concepts is solid."
                  : scorePct >= 50
                  ? "Good progress. Review the highlighted source explanations below to shore up gaps."
                  : "Needs reinforcement. Review the cited excerpts below and launch an adaptive remediation session."}
              </p>
            </div>

            <div className="scorecard-actions">
              <button
                type="button"
                className="btn btn-primary btn-md w-full"
                onClick={() => void startQuiz(true)}
              >
                <TargetIcon className="w-4 h-4" />
                <span>Practice Weak Concepts (Adaptive)</span>
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-md w-full"
                onClick={() => setActiveTab("mastery")}
              >
                <SparklesIcon className="w-4 h-4" />
                <span>Inspect Updated Mastery</span>
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-sm w-full"
                onClick={() => setMode("setup")}
              >
                Configure New Quiz
              </button>
            </div>
          </div>
        </div>

        {/* Detailed Question Review */}
        <div className="review-section">
          <h2 className="section-title mb-4">Detailed Question Review & Provenance</h2>

          <div className="review-cards-list">
            {submissionResult.results.map((res, index) => {
              const originalQ = activeQuiz.questions.find((q) => q.question_id === res.question_id);
              const isCorrect = res.is_correct === true;

              return (
                <div
                  key={res.question_id}
                  className={`review-card ${isCorrect ? "review-correct" : "review-incorrect"}`}
                >
                  <div className="review-card-header">
                    <div className="flex items-center gap-2">
                      <span className="review-q-num">#{index + 1}</span>
                      <span className="review-concept-pill">{res.concept_label}</span>
                    </div>
                    <div className="review-status-indicator">
                      {isCorrect ? (
                        <span className="badge badge-success">
                          <CheckCircleIcon className="w-3.5 h-3.5" /> Correct
                        </span>
                      ) : (
                        <span className="badge badge-error">
                          <XCircleIcon className="w-3.5 h-3.5" /> Incorrect
                        </span>
                      )}
                    </div>
                  </div>

                  <p className="review-prompt">{originalQ?.question_text}</p>

                  <div className="review-feedback-box">
                    <p className="review-feedback-text">{res.feedback}</p>
                  </div>

                  {/* Grounded Excerpt */}
                  <div className="review-source-box">
                    <div className="review-source-header">
                      <CitationIcon className="w-3.5 h-3.5 text-cyan" />
                      <span>
                        Verified Grounding in Source ({res.source_type === "pdf_page" ? "Page" : "Slide"}{" "}
                        {res.page_or_slide_number}):
                      </span>
                    </div>
                    <blockquote className="review-excerpt-quote">
                      "{res.supporting_excerpt}"
                    </blockquote>
                  </div>

                  {/* Ask AI Tutor Action */}
                  <div className="review-action-row">
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm text-cyan hover:text-cyan-bright"
                      onClick={() => {
                        setPendingTutorPrompt(
                          `Can you explain the concept "${res.concept_label}" from ${
                            res.source_type === "pdf_page" ? "Page" : "Slide"
                          } ${res.page_or_slide_number}? Specifically why "${res.supporting_excerpt}" applies.`
                        );
                        setActiveTab("tutor");
                      }}
                    >
                      <TutorIcon className="w-4 h-4" />
                      <span>Ask AI Tutor About This</span>
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  return null;
}

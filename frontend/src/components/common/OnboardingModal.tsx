import { useState } from "react";
import { useApp } from "../../context/AppContext";
import {
  UploadCloudIcon,
  TutorIcon,
  QuizIcon,
  AnalyticsIcon,
  SparklesIcon,
  ChevronRightIcon,
  ArrowLeftIcon,
  CloseIcon,
  CheckCircleIcon,
} from "./Icons";

export function OnboardingModal() {
  const { showOnboarding, setShowOnboarding, setActiveTab } = useApp();
  const [step, setStep] = useState(0);

  if (!showOnboarding) return null;

  const steps = [
    {
      title: "Welcome to NEXUS ACADEMY",
      eyebrow: "NEXT-GENERATION AI LEARNING STUDIO",
      icon: <SparklesIcon className="w-8 h-8 text-cyan" />,
      desc: "NEXUS ACADEMY transforms your academic PDFs and PowerPoint slide decks into an interactive, grounded AI learning coach with adaptive quizzes and verifiable concept mastery.",
      actionLabel: "Explore the 4-Step Loop",
    },
    {
      title: "1. Ingest Course Materials",
      eyebrow: "MULTIMODAL DOCUMENT PARSING",
      icon: <UploadCloudIcon className="w-8 h-8 text-violet" />,
      desc: "Upload any textbook, lecture slides (PPTX), or syllabus up to 20 MB. Our ingestion engine extracts structured pages, slides, tables, and images with full lexical BM25 indexing.",
      actionLabel: "Next: Grounded AI Tutor",
    },
    {
      title: "2. Grounded AI Tutoring",
      eyebrow: "ZERO-HALLUCINATION QUESTION ANSWERING",
      icon: <TutorIcon className="w-8 h-8 text-cyan" />,
      desc: "Ask deep conceptual questions. Every answer cites exact slide or page numbers with quoted excerpts. If your materials don't cover the topic, the tutor honestly abstains rather than inventing answers.",
      actionLabel: "Next: Adaptive Practice",
    },
    {
      title: "3. Adaptive Practice & Quizzes",
      eyebrow: "CONCEPT-CALIBRATED ASSESSMENTS",
      icon: <QuizIcon className="w-8 h-8 text-emerald" />,
      desc: "Practice with multiple-choice quizzes that adapt in real time. The engine prioritizes concepts where your understanding is weak, prevents repeating questions you've already answered, and keeps answer keys secure.",
      actionLabel: "Next: Mastery & Gamification",
    },
    {
      title: "4. Mastery Intelligence & Real XP",
      eyebrow: "EXPLAINABLE BAYESIAN PROGRESSION",
      icon: <AnalyticsIcon className="w-8 h-8 text-amber" />,
      desc: "Track concept mastery across 4 transparent states (Proficient, Learning, Struggling, Not Attempted). Earn XP, level up from Novice Scholar to Academic Luminary, and unlock achievements backed by real database records.",
      actionLabel: "Enter Intelligence Studio",
    },
  ];

  const current = steps[step];

  const handleNext = () => {
    if (step < steps.length - 1) {
      setStep((prev) => prev + 1);
    } else {
      setShowOnboarding(false);
      setActiveTab("home");
    }
  };

  return (
    <div className="modal-backdrop animate-fade-in" role="dialog" aria-modal="true">
      <div className="modal-dialog surface-card p-8">
        <button
          type="button"
          className="modal-close-btn"
          onClick={() => setShowOnboarding(false)}
          aria-label="Close tour"
        >
          <CloseIcon className="w-5 h-5" />
        </button>

        <div className="onboarding-step-indicator">
          {steps.map((_, idx) => (
            <span
              key={idx}
              className={`step-dash ${idx === step ? "step-dash-active" : ""} ${
                idx < step ? "step-dash-done" : ""
              }`}
            />
          ))}
        </div>

        <div className="onboarding-content mt-6">
          <div className="onboarding-icon-wrap mb-4">{current.icon}</div>
          <span className="view-eyebrow">{current.eyebrow}</span>
          <h2 className="onboarding-title mb-3">{current.title}</h2>
          <p className="onboarding-desc mb-8">{current.desc}</p>
        </div>

        <div className="modal-footer flex items-center justify-between">
          {step > 0 ? (
            <button
              type="button"
              className="btn btn-secondary btn-md"
              onClick={() => setStep((prev) => prev - 1)}
            >
              <ArrowLeftIcon className="w-4 h-4" />
              <span>Back</span>
            </button>
          ) : (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setShowOnboarding(false)}
            >
              Skip Introduction
            </button>
          )}

          <button
            type="button"
            className="btn btn-primary btn-md"
            onClick={handleNext}
          >
            <span>{current.actionLabel}</span>
            <ChevronRightIcon className="w-4 h-4 ml-1" />
          </button>
        </div>
      </div>
    </div>
  );
}

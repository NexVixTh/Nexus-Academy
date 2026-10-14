import { useState, type ReactNode } from "react";
import { useApp, type NavTab } from "../../context/AppContext";
import {
  NexusLogo,
  HomeIcon,
  TutorIcon,
  QuizIcon,
  AnalyticsIcon,
  DocumentLibraryIcon,
  CpuIcon,
  CopyIcon,
  RefreshIcon,
  MenuIcon,
  CloseIcon,
  CheckCircleIcon,
  SparklesIcon,
} from "../common/Icons";
import { ToastContainer } from "./ToastContainer";
import { OnboardingModal } from "../common/OnboardingModal";
import { HackathonGuideModal } from "../common/HackathonGuideModal";

interface AppShellProps {
  children: ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  const {
    activeTab,
    setActiveTab,
    theme,
    toggleTheme,
    backendStatus,
    modelStatus,
    learnerId,
    gamification,
    activeDocument,
    documents,
    selectDocument,
    addToast,
    refreshHealth,
    resetLearner,
    setShowHackathonGuide,
    setShowOnboarding,
  } = useApp();

  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [copiedLearner, setCopiedLearner] = useState(false);

  const handleCopyLearnerId = () => {
    if (!learnerId) return;
    navigator.clipboard.writeText(learnerId);
    setCopiedLearner(true);
    addToast("Learner ID copied to clipboard.", "success");
    setTimeout(() => setCopiedLearner(false), 2000);
  };

  const navItems: { id: NavTab; label: string; icon: ReactNode; badge?: string }[] = [
    { id: "home", label: "Command Center", icon: <HomeIcon /> },
    { id: "tutor", label: "Grounded AI Tutor", icon: <TutorIcon /> },
    { id: "quiz", label: "Adaptive Practice", icon: <QuizIcon /> },
    { id: "mastery", label: "Mastery Intelligence", icon: <AnalyticsIcon /> },
    {
      id: "library",
      label: "Document Library",
      icon: <DocumentLibraryIcon />,
      badge: documents.length > 0 ? String(documents.length) : undefined,
    },
  ];

  const tutorTask = modelStatus?.tasks.find((t) => t.task === "tutor");
  const modelLabel = tutorTask?.enabled
    ? `${tutorTask.provider}: ${tutorTask.model || "active"}`
    : "Deterministic Extractive QA";

  return (
    <div className="app-layout">
      {/* Mobile Topbar */}
      <header className="mobile-header">
        <button
          type="button"
          className="mobile-menu-toggle"
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          aria-label={mobileMenuOpen ? "Close navigation menu" : "Open navigation menu"}
          aria-expanded={mobileMenuOpen}
        >
          {mobileMenuOpen ? <CloseIcon /> : <MenuIcon />}
        </button>
        <div className="mobile-brand">
          <NexusLogo className="w-6 h-6" />
          <span className="mobile-brand-name">NEXUS ACADEMY</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="theme-toggle-btn-compact"
            onClick={toggleTheme}
            title={theme === "dark" ? "Switch to Academic Paper Light theme" : "Switch to Studio Midnight Dark theme"}
            aria-label="Toggle theme"
          >
            {theme === "dark" ? "☀️" : "🌙"}
          </button>
          <div className="mobile-status-pill">
            <span className={`status-jewel jewel-${backendStatus}`} />
          </div>
        </div>
      </header>

      {/* Main Sidebar Navigation */}
      <aside
        className={`sidebar ${mobileMenuOpen ? "sidebar-open" : ""}`}
        aria-label="Primary Navigation"
      >
        <div className="sidebar-brand">
          <div className="brand-lockup">
            <NexusLogo className="brand-logo" />
            <div className="brand-meta">
              <span className="brand-title">NEXUS ACADEMY</span>
              <span className="brand-badge">INTELLIGENCE STUDIO</span>
            </div>
            <button
              type="button"
              className="theme-toggle-btn ml-auto"
              onClick={toggleTheme}
              title={theme === "dark" ? "Switch to Academic Light theme" : "Switch to Studio Dark theme"}
              aria-label="Toggle color theme"
            >
              {theme === "dark" ? "☀️" : "🌙"}
            </button>
          </div>
        </div>

        {/* Active Context Document Selector */}
        <div className="context-selector-card">
          <div className="context-header">
            <span className="context-label">ACTIVE STUDY MATERIAL</span>
            {activeDocument && (
              <span className="context-format">
                {activeDocument.content_type.includes("pdf") ? "PDF" : "PPTX"}
              </span>
            )}
          </div>
          {documents.length === 0 ? (
            <button
              type="button"
              className="context-empty-action"
              onClick={() => {
                setActiveTab("library");
                setMobileMenuOpen(false);
              }}
            >
              + Ingest course document
            </button>
          ) : (
            <select
              className="context-select"
              value={activeDocument?.document_id || ""}
              onChange={(e) => {
                selectDocument(e.target.value || null);
                addToast("Switched active document.", "info");
              }}
              aria-label="Select active study material"
            >
              {documents.map((doc) => (
                <option key={doc.document_id} value={doc.document_id}>
                  {doc.original_filename} ({doc.record_count}{" "}
                  {doc.content_type.includes("presentationml") ? "slides" : "pages"})
                </option>
              ))}
            </select>
          )}
        </div>

        {/* Primary Navigation Links */}
        <nav className="sidebar-nav">
          {navItems.map((item) => {
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                type="button"
                className={`nav-button ${isActive ? "nav-button-active" : ""}`}
                onClick={() => {
                  setActiveTab(item.id);
                  setMobileMenuOpen(false);
                }}
                aria-current={isActive ? "page" : undefined}
              >
                <span className="nav-icon" aria-hidden="true">
                  {item.icon}
                </span>
                <span className="nav-label">{item.label}</span>
                {item.badge && <span className="nav-badge">{item.badge}</span>}
              </button>
            );
          })}

          {/* Hackathon Guide Link */}
          <div className="mt-4 pt-4 border-t border-subtle">
            <button
              type="button"
              className="guide-pill-button"
              onClick={() => {
                setShowHackathonGuide(true);
                setMobileMenuOpen(false);
              }}
            >
              <SparklesIcon className="w-4 h-4 text-cyan" />
              <span>Judges' Fast-Track Guide</span>
            </button>
          </div>
        </nav>

        {/* Sidebar Footer — Engine Metadata & Learner ID */}
        <div className="sidebar-footer">
          {/* Engine Status */}
          <div className="engine-status-pill" title={`Tutor Engine: ${modelLabel}`}>
            <span className="engine-icon">
              <CpuIcon />
            </span>
            <div className="engine-meta">
              <span className="engine-title">REASONING ENGINE</span>
              <span className="engine-subtitle">{modelLabel}</span>
            </div>
            <button
              type="button"
              className="engine-refresh-btn"
              onClick={() => {
                void refreshHealth();
                addToast("Refreshed backend connection status.", "info");
              }}
              title="Refresh connection status"
              aria-label="Refresh backend status"
            >
              <RefreshIcon />
            </button>
          </div>

          {/* Learner Identity with XP Preview */}
          <div className="learner-card">
            <div className="learner-info">
              <span className="learner-eyebrow">
                {gamification ? `LVL ${gamification.level} • ${gamification.xp} XP` : "ACTIVE LEARNER"}
              </span>
              <span className="learner-id-code">
                {learnerId ? `${learnerId.substring(0, 8)}...${learnerId.substring(learnerId.length - 4)}` : "Initializing..."}
              </span>
            </div>
            <div className="learner-actions">
              <button
                type="button"
                className="learner-btn"
                onClick={handleCopyLearnerId}
                title="Copy Learner ID"
                aria-label="Copy Learner ID"
              >
                {copiedLearner ? <CheckCircleIcon className="w-3.5 h-3.5 text-emerald" /> : <CopyIcon className="w-3.5 h-3.5" />}
              </button>
              <button
                type="button"
                className="learner-btn"
                onClick={() => void resetLearner()}
                title="New Learner Profile (Reset Progress)"
                aria-label="Create new learner profile"
              >
                <RefreshIcon className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {/* Connection Jewel Status */}
          <div className="backend-conn-status">
            <span className={`status-jewel jewel-${backendStatus}`} />
            <span className="backend-conn-text">
              Backend {backendStatus === "online" ? "Synchronized" : backendStatus === "checking" ? "Checking..." : "Offline (Mock Fallback)"}
            </span>
          </div>
        </div>
      </aside>

      {/* Main Workspace Area */}
      <main className="main-content" tabIndex={-1}>
        <div className="content-wrapper">{children}</div>
      </main>

      {/* Global Modals & Toast Notifications */}
      <OnboardingModal />
      <HackathonGuideModal />
      <ToastContainer />
    </div>
  );
}

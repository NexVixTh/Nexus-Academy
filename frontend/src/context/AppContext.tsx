import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { api } from "../api/client";
import type {
  BackendStatus,
  DocumentListItem,
  LearnerGamificationResponse,
  ModelStatusResponse,
} from "../types/api";

export type NavTab = "home" | "tutor" | "quiz" | "mastery" | "library";
export type AppTheme = "dark" | "light";

export interface ToastItem {
  id: string;
  type: "success" | "error" | "info";
  message: string;
}

interface AppContextValue {
  activeTab: NavTab;
  setActiveTab: (tab: NavTab) => void;
  theme: AppTheme;
  toggleTheme: () => void;
  backendStatus: BackendStatus;
  modelStatus: ModelStatusResponse | null;
  learnerId: string | null;
  gamification: LearnerGamificationResponse | null;
  documents: DocumentListItem[];
  selectedDocumentId: string | null;
  activeDocument: DocumentListItem | null;
  isLoadingDocuments: boolean;
  toasts: ToastItem[];
  showOnboarding: boolean;
  setShowOnboarding: (show: boolean) => void;
  showHackathonGuide: boolean;
  setShowHackathonGuide: (show: boolean) => void;
  addToast: (message: string, type?: "success" | "error" | "info") => void;
  removeToast: (id: string) => void;
  selectDocument: (id: string | null) => void;
  refreshDocuments: () => Promise<void>;
  refreshHealth: () => Promise<void>;
  refreshGamification: () => Promise<void>;
  resetLearner: () => Promise<void>;
  pendingTutorPrompt: string | null;
  setPendingTutorPrompt: (prompt: string | null) => void;
}

const AppContext = createContext<AppContextValue | null>(null);

const STORAGE_KEY_LEARNER = "nexus_learner_id";
const STORAGE_KEY_DOC = "nexus_selected_doc_id";
const STORAGE_KEY_THEME = "nexus_theme";
const STORAGE_KEY_ONBOARDING = "nexus_onboarding_completed";

export function AppProvider({ children }: { children: ReactNode }) {
  const [activeTab, setActiveTab] = useState<NavTab>("home");
  const [theme, setTheme] = useState<AppTheme>(() => {
    return (localStorage.getItem(STORAGE_KEY_THEME) as AppTheme) || "dark";
  });
  const [backendStatus, setBackendStatus] = useState<BackendStatus>("checking");
  const [modelStatus, setModelStatus] = useState<ModelStatusResponse | null>(null);
  const [learnerId, setLearnerId] = useState<string | null>(() => {
    return localStorage.getItem(STORAGE_KEY_LEARNER);
  });
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(() => {
    return localStorage.getItem(STORAGE_KEY_DOC);
  });
  const [gamification, setGamification] = useState<LearnerGamificationResponse | null>(null);
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [isLoadingDocuments, setIsLoadingDocuments] = useState(false);
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [showOnboarding, setShowOnboardingState] = useState<boolean>(() => {
    return !localStorage.getItem(STORAGE_KEY_ONBOARDING);
  });
  const [showHackathonGuide, setShowHackathonGuide] = useState(false);
  const [pendingTutorPrompt, setPendingTutorPrompt] = useState<string | null>(null);

  // Sync theme attribute to HTML root
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem(STORAGE_KEY_THEME, theme);
  }, [theme]);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  }, []);

  const setShowOnboarding = useCallback((show: boolean) => {
    setShowOnboardingState(show);
    if (!show) {
      localStorage.setItem(STORAGE_KEY_ONBOARDING, "true");
    }
  }, []);

  const addToast = useCallback(
    (message: string, type: "success" | "error" | "info" = "info") => {
      const id = `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
      setToasts((prev) => [...prev, { id, message, type }]);
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, 4000);
    },
    []
  );

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const selectDocument = useCallback((id: string | null) => {
    setSelectedDocumentId(id);
    if (id) {
      localStorage.setItem(STORAGE_KEY_DOC, id);
    } else {
      localStorage.removeItem(STORAGE_KEY_DOC);
    }
  }, []);

  const refreshHealth = useCallback(async () => {
    try {
      const health = await api.getHealth();
      setBackendStatus(health.status === "ok" ? "online" : "offline");
      try {
        const models = await api.getModelsStatus();
        setModelStatus(models);
      } catch {
        // Models status optional if router is inactive
      }
    } catch {
      setBackendStatus("offline");
    }
  }, []);

  const refreshDocuments = useCallback(async () => {
    setIsLoadingDocuments(true);
    try {
      const res = await api.listDocuments();
      setDocuments(res.documents);

      // Auto-select first document if none selected, or restore selected
      setSelectedDocumentId((current) => {
        if (current && res.documents.some((d) => d.document_id === current)) {
          return current;
        }
        if (res.documents.length > 0) {
          const firstId = res.documents[0].document_id;
          localStorage.setItem(STORAGE_KEY_DOC, firstId);
          return firstId;
        }
        localStorage.removeItem(STORAGE_KEY_DOC);
        return null;
      });
    } catch (err) {
      console.warn("Could not fetch document list:", err);
    } finally {
      setIsLoadingDocuments(false);
    }
  }, []);

  const refreshGamification = useCallback(async () => {
    if (!learnerId) return;
    try {
      const g = await api.getLearnerGamification(learnerId);
      setGamification(g);
    } catch (err) {
      // Learner may not have any gamification yet
    }
  }, [learnerId]);

  // Ensure learner exists
  const ensureLearner = useCallback(async () => {
    const existing = localStorage.getItem(STORAGE_KEY_LEARNER);
    if (existing) {
      setLearnerId(existing);
      return;
    }
    try {
      const profile = await api.createLearner();
      localStorage.setItem(STORAGE_KEY_LEARNER, profile.learner_id);
      setLearnerId(profile.learner_id);
    } catch (err) {
      console.warn("Failed to create learner profile on startup:", err);
    }
  }, []);

  const resetLearner = useCallback(async () => {
    try {
      const profile = await api.createLearner();
      localStorage.setItem(STORAGE_KEY_LEARNER, profile.learner_id);
      setLearnerId(profile.learner_id);
      addToast("Created new learner profile.", "success");
      await refreshGamification();
    } catch (err) {
      addToast("Failed to initialize new learner profile.", "error");
    }
  }, [addToast, refreshGamification]);

  // Initial startup
  useEffect(() => {
    let mounted = true;
    async function init() {
      await refreshHealth();
      if (mounted) {
        await Promise.all([ensureLearner(), refreshDocuments()]);
      }
    }
    void init();
    return () => {
      mounted = false;
    };
  }, [refreshHealth, ensureLearner, refreshDocuments]);

  // Auto-refresh gamification whenever learnerId changes
  useEffect(() => {
    if (learnerId) {
      void refreshGamification();
    }
  }, [learnerId, refreshGamification]);

  const activeDocument =
    documents.find((d) => d.document_id === selectedDocumentId) || null;

  return (
    <AppContext.Provider
      value={{
        activeTab,
        setActiveTab,
        theme,
        toggleTheme,
        backendStatus,
        modelStatus,
        learnerId,
        gamification,
        documents,
        selectedDocumentId,
        activeDocument,
        isLoadingDocuments,
        toasts,
        showOnboarding,
        setShowOnboarding,
        showHackathonGuide,
        setShowHackathonGuide,
        addToast,
        removeToast,
        selectDocument,
        refreshDocuments,
        refreshHealth,
        refreshGamification,
        resetLearner,
        pendingTutorPrompt,
        setPendingTutorPrompt,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  const context = useContext(AppContext);
  if (!context) {
    throw new Error("useApp must be used within an AppProvider");
  }
  return context;
}

import { useState, useEffect, useRef, type FormEvent } from "react";
import { useApp } from "../../context/AppContext";
import { api, ApiError } from "../../api/client";
import type { AskResponse, Citation, DocumentConceptItem } from "../../types/api";
import {
  TutorIcon,
  SendIcon,
  SparklesIcon,
  CitationIcon,
  AlertTriangleIcon,
  CheckCircleIcon,
  InfoIcon,
  RefreshIcon,
  CpuIcon,
  CopyIcon,
  DocumentLibraryIcon,
} from "../common/Icons";

interface MessageItem {
  id: string;
  sender: "user" | "tutor";
  text: string;
  citations?: Citation[];
  abstained?: boolean;
  abstentionReason?: string | null;
  timestamp: string;
}

export function TutorStudio() {
  const {
    activeDocument,
    documents,
    selectedDocumentId,
    selectDocument,
    setActiveTab,
    modelStatus,
    addToast,
    pendingTutorPrompt,
    setPendingTutorPrompt,
  } = useApp();

  const [questionInput, setQuestionInput] = useState("");
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>([]);
  const [activeConcepts, setActiveConcepts] = useState<DocumentConceptItem[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Load document concepts for suggested questions
  useEffect(() => {
    if (!selectedDocumentId) {
      setSuggestedQuestions([]);
      setActiveConcepts([]);
      return;
    }

    let active = true;
    async function loadConcepts() {
      try {
        const res = await api.getDocumentConcepts(selectedDocumentId!);
        if (!active) return;
        setActiveConcepts(res.concepts);

        // Derive grounded suggestions from real concept names
        const suggestions: string[] = [];
        for (const c of res.concepts.slice(0, 4)) {
          suggestions.push(`What is ${c.name}?`);
          if (c.description && c.description.length > 20) {
            suggestions.push(`Explain how ${c.name} works in this context`);
          }
        }
        // Fallback default suggestions if concepts are limited
        if (suggestions.length === 0) {
          suggestions.push("Summarize the main points of this document.");
          suggestions.push("What are the key technical concepts explained here?");
        }
        setSuggestedQuestions(suggestions.slice(0, 4));
      } catch {
        if (active) {
          setSuggestedQuestions([
            "Summarize the main definitions in this document.",
            "What equations or relationships are introduced?",
          ]);
        }
      }
    }

    void loadConcepts();
    return () => {
      active = false;
    };
  }, [selectedDocumentId]);

  // Auto-scroll chat to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  // Handle incoming seeded questions from Quiz or Constellation
  useEffect(() => {
    if (pendingTutorPrompt) {
      setQuestionInput(pendingTutorPrompt);
      setPendingTutorPrompt(null);
      setTimeout(() => {
        textareaRef.current?.focus();
      }, 50);
    }
  }, [pendingTutorPrompt, setPendingTutorPrompt]);

  const handleAsk = async (questionText: string) => {
    const trimmed = questionText.trim();
    if (!trimmed || !selectedDocumentId || isLoading) return;

    const userMsg: MessageItem = {
      id: `user-${Date.now()}`,
      sender: "user",
      text: trimmed,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setQuestionInput("");
    setIsLoading(true);

    try {
      const response: AskResponse = await api.askDocument(selectedDocumentId, trimmed);

      const tutorMsg: MessageItem = {
        id: `tutor-${Date.now()}`,
        sender: "tutor",
        text: response.answer,
        citations: response.citations,
        abstained: response.abstained,
        abstentionReason: response.abstention_reason,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };

      setMessages((prev) => [...prev, tutorMsg]);
    } catch (err) {
      const errorDetail =
        err instanceof ApiError ? err.detail || err.message : "Failed to obtain response.";
      const errorMsg: MessageItem = {
        id: `tutor-err-${Date.now()}`,
        sender: "tutor",
        text: `Error contacting reasoning engine: ${errorDetail}`,
        abstained: true,
        abstentionReason: "Network or server failure",
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };
      setMessages((prev) => [...prev, errorMsg]);
      addToast("Failed to process question.", "error");
    } finally {
      setIsLoading(false);
      setTimeout(() => textareaRef.current?.focus(), 100);
    }
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    void handleAsk(questionInput);
  };

  const tutorTask = modelStatus?.tasks.find((t) => t.task === "tutor");
  const modelProviderLabel = tutorTask?.enabled
    ? `${tutorTask.provider.toUpperCase()} (${tutorTask.model || "live"})`
    : "DETERMINISTIC EXTRACTIVE (Offline Fallback)";

  if (!activeDocument) {
    return (
      <div className="view-container animate-fade-in">
        <div className="empty-state-card mt-8">
          <TutorIcon className="w-16 h-16 text-muted mb-3" />
          <h2>No Active Study Material</h2>
          <p>
            Please select or ingest a PDF or PPTX document to start a source-grounded tutoring session.
          </p>
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

  return (
    <div className="tutor-workspace animate-fade-in">
      {/* Workspace Header */}
      <div className="tutor-header">
        <div className="tutor-header-title-col">
          <div className="flex items-center gap-2">
            <span className="view-eyebrow">GROUNDED LEARNING STUDIO</span>
            <span className="source-grounded-badge">
              <CheckCircleIcon className="w-3.5 h-3.5" />
              100% Traceable Citations
            </span>
          </div>
          <h1 className="tutor-title">{activeDocument.original_filename}</h1>
        </div>

        <div className="tutor-header-meta">
          <div className="tutor-engine-badge">
            <CpuIcon className="w-3.5 h-3.5 text-violet" />
            <span className="engine-badge-label">{modelProviderLabel}</span>
          </div>
          <select
            className="header-doc-select"
            value={activeDocument.document_id}
            onChange={(e) => {
              selectDocument(e.target.value);
              setMessages([]);
            }}
            aria-label="Switch document context"
          >
            {documents.map((d) => (
              <option key={d.document_id} value={d.document_id}>
                {d.original_filename} ({d.record_count}{" "}
                {d.content_type.includes("presentationml") ? "slides" : "pages"})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Main Conversation Canvas */}
      <div className="tutor-canvas">
        {messages.length === 0 ? (
          <div className="tutor-welcome-screen">
            <div className="tutor-welcome-glow" />
            <div className="welcome-avatar">
              <SparklesIcon className="w-8 h-8 text-cyan" />
            </div>
            <h2>Nexus AI Reasoning Tutor</h2>
            <p className="welcome-desc">
              Ask deep questions about <strong>{activeDocument.original_filename}</strong>. Every response is strictly grounded in the ingested material with verified source citations. If the document doesn't contain the answer, the tutor will honestly abstain rather than hallucinate.
            </p>

            {suggestedQuestions.length > 0 && (
              <div className="welcome-suggestions-container">
                <span className="suggestions-label">RECOMMENDED QUESTIONS FROM EXTRACTED CONCEPTS:</span>
                <div className="suggestions-pills">
                  {suggestedQuestions.map((q, idx) => (
                    <button
                      key={idx}
                      type="button"
                      className="suggestion-chip"
                      onClick={() => handleAsk(q)}
                    >
                      <SparklesIcon className="w-3 h-3 text-cyan flex-shrink-0" />
                      <span>{q}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="message-stream">
            {messages.map((msg) => {
              const isUser = msg.sender === "user";
              return (
                <div
                  key={msg.id}
                  className={`message-row ${isUser ? "message-user" : "message-tutor"}`}
                >
                  <div className="message-bubble-wrapper">
                    <div className="message-meta-header">
                      <span className="message-sender-name">
                        {isUser ? "You" : "Nexus Grounded Tutor"}
                      </span>
                      <span className="message-timestamp">{msg.timestamp}</span>
                    </div>

                    <div className="message-bubble">
                      {/* Abstention Warning Banner */}
                      {msg.abstained && (
                        <div className="abstention-banner">
                          <AlertTriangleIcon className="w-4 h-4 text-amber flex-shrink-0" />
                          <div>
                            <strong>Honest Abstention:</strong>{" "}
                            {msg.abstentionReason || "This topic is outside the scope of the provided document evidence."}
                          </div>
                        </div>
                      )}

                      {/* Main Message Text */}
                      <div className="message-body">{msg.text}</div>

                      {/* Grounded Source Citations */}
                      {msg.citations && msg.citations.length > 0 && (
                        <div className="citations-tray">
                          <div className="citations-header">
                            <CitationIcon className="w-3.5 h-3.5 text-cyan" />
                            <span>VERIFIED SOURCE PROVENANCE ({msg.citations.length}):</span>
                          </div>
                          <div className="citations-grid">
                            {msg.citations.map((cite, cIdx) => (
                              <div key={cIdx} className="citation-card">
                                <div className="citation-badge-row">
                                  <span className="citation-location">
                                    {cite.source_type === "pdf_page" ? "Page" : "Slide"}{" "}
                                    {cite.page_or_slide_number}
                                  </span>
                                  <button
                                    type="button"
                                    className="citation-copy-btn"
                                    onClick={() => {
                                      navigator.clipboard.writeText(cite.excerpt);
                                      addToast("Citation excerpt copied.", "info");
                                    }}
                                    title="Copy excerpt"
                                    aria-label="Copy citation excerpt"
                                  >
                                    <CopyIcon className="w-3 h-3" />
                                  </button>
                                </div>
                                <blockquote className="citation-quote">
                                  "{cite.excerpt}"
                                </blockquote>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}

            {isLoading && (
              <div className="message-row message-tutor">
                <div className="message-bubble-wrapper">
                  <div className="message-meta-header">
                    <span className="message-sender-name">Nexus Grounded Tutor</span>
                    <span className="message-timestamp">Analyzing...</span>
                  </div>
                  <div className="message-bubble loading-bubble">
                    <div className="typing-indicator">
                      <span />
                      <span />
                      <span />
                    </div>
                    <span className="loading-text">
                      Searching BM25 index & synthesizing grounded evidence...
                    </span>
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Composer Input Bar */}
      <div className="tutor-composer-dock">
        <form onSubmit={onSubmit} className="composer-form">
          <div className="composer-input-wrapper">
            <textarea
              ref={textareaRef}
              rows={1}
              className="composer-textarea"
              placeholder={`Ask a question about ${activeDocument.original_filename}... (Shift+Enter for new line)`}
              value={questionInput}
              onChange={(e) => setQuestionInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void handleAsk(questionInput);
                }
              }}
              disabled={isLoading}
              aria-label="Ask a question about the active document"
            />
            <button
              type="submit"
              className="composer-send-btn"
              disabled={!questionInput.trim() || isLoading}
              aria-label="Send question"
            >
              {isLoading ? (
                <RefreshIcon className="w-4 h-4 spin" />
              ) : (
                <SendIcon className="w-4 h-4" />
              )}
            </button>
          </div>
          <div className="composer-footer-hints">
            <span>Press <strong>Enter</strong> to ask • <strong>Shift+Enter</strong> for newline</span>
            <span>Grounding: <strong>Strict Citation Verification</strong></span>
          </div>
        </form>
      </div>
    </div>
  );
}

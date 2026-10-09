import { useEffect, useState } from "react";

type BackendStatus = "checking" | "online" | "offline";
type HealthResponse = { status: string };

const statusLabels: Record<BackendStatus, string> = {
  checking: "Checking connection",
  online: "Connected",
  offline: "Unavailable",
};

export default function App() {
  const [backendStatus, setBackendStatus] = useState<BackendStatus>("checking");

  useEffect(() => {
    let active = true;

    async function checkBackend() {
      try {
        const response = await fetch("/api/health");
        if (!response.ok) throw new Error("Health check failed");

        const health = (await response.json()) as HealthResponse;
        if (active) setBackendStatus(health.status === "ok" ? "online" : "offline");
      } catch {
        if (active) setBackendStatus("offline");
      }
    }

    void checkBackend();
    return () => {
      active = false;
    };
  }, []);

  return (
    <main className="app-shell">
      <div className="brand-mark" aria-hidden="true">N</div>
      <p className="eyebrow">PERSONALIZED LEARNING</p>
      <h1>NEXUS ACADEMY</h1>
      <p className="intro">Your learning space is taking shape.</p>
      <section className="service-status" aria-live="polite">
        <span className={`status-indicator status-${backendStatus}`} aria-hidden="true" />
        <span className="service-name">Backend</span>
        <span className="status-label">{statusLabels[backendStatus]}</span>
      </section>
    </main>
  );
}
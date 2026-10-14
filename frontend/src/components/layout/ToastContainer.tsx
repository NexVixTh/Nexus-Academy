import { useApp } from "../../context/AppContext";
import { CheckCircleIcon, XCircleIcon, InfoIcon, CloseIcon } from "../common/Icons";

export function ToastContainer() {
  const { toasts, removeToast } = useApp();

  if (toasts.length === 0) return null;

  return (
    <aside
      className="toast-container"
      aria-live="polite"
      aria-label="Notifications"
    >
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast toast-${toast.type}`} role="status">
          <span className="toast-icon" aria-hidden="true">
            {toast.type === "success" && <CheckCircleIcon className="w-4 h-4" />}
            {toast.type === "error" && <XCircleIcon className="w-4 h-4" />}
            {toast.type === "info" && <InfoIcon className="w-4 h-4" />}
          </span>
          <span className="toast-message">{toast.message}</span>
          <button
            type="button"
            className="toast-close"
            onClick={() => removeToast(toast.id)}
            aria-label="Dismiss notification"
          >
            <CloseIcon className="w-3.5 h-3.5" />
          </button>
        </div>
      ))}
    </aside>
  );
}

import { useSyncExternalStore } from "react";
import { ErrorNotice } from "./ErrorNotice";
import { dismissError, getErrorToasts, subscribeToErrors } from "../utils/errorReporter";

/** Renders error toasts raised with reportError() in the bottom-right corner. */
export default function ErrorToaster() {
  const toasts = useSyncExternalStore(subscribeToErrors, getErrorToasts);
  if (toasts.length === 0) return null;

  return (
    <div
      aria-live="assertive"
      style={{
        position: "fixed",
        right: "var(--space-4)",
        bottom: "var(--space-4)",
        zIndex: 1000,
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-2)",
        width: "min(420px, calc(100vw - 2 * var(--space-4)))",
      }}
    >
      {toasts.map((t) => (
        <div key={t.id} style={{ boxShadow: "0 4px 16px rgba(0,0,0,0.18)" }}>
          <ErrorNotice error={t.error} title={t.title} onDismiss={() => dismissError(t.id)} />
        </div>
      ))}
    </div>
  );
}

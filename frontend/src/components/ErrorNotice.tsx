import { useState } from "react";
import { toErrorInfo } from "../api/client";

interface Props {
  error: unknown;
  /** Short context line, e.g. "Could not create job run". */
  title?: string;
  /** Use colors suited to a dark (inverse) background. */
  dark?: boolean;
  onDismiss?: () => void;
}

/**
 * Displays an error clearly: what went wrong, how to fix it (hint), and the
 * request ID to search for in the backend logs.
 */
export function ErrorNotice({ error, title, dark = false, onDismiss }: Props) {
  const info = toErrorInfo(error);
  const [copied, setCopied] = useState(false);

  const copyId = async () => {
    if (!info.requestId) return;
    try {
      await navigator.clipboard.writeText(info.requestId);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard not available; the ID is still visible */
    }
  };

  const muted = dark ? "var(--text-on-inverse)" : "var(--text-secondary)";

  return (
    <div
      role="alert"
      style={{
        padding: "var(--space-3)",
        border: `1px solid ${dark ? "var(--accent-alert-on-inverse)" : "var(--accent-alert)"}`,
        backgroundColor: dark ? "var(--bg-inverse)" : "var(--status-alert-bg)",
        color: dark ? "var(--text-on-inverse)" : "var(--status-alert-text)",
        fontSize: "var(--text-xs)",
        lineHeight: 1.5,
        display: "flex",
        flexDirection: "column",
        gap: "4px",
        minWidth: 0,
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: "var(--space-2)" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          {title && <div style={{ fontWeight: 600 }}>{title}</div>}
          <div style={{ fontFamily: "var(--font-mono)", overflowWrap: "anywhere" }}>{info.message}</div>
        </div>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            aria-label="Dismiss error"
            style={{ background: "none", border: "none", color: "inherit", cursor: "pointer", fontSize: "14px", lineHeight: 1, padding: 0 }}
          >
            ×
          </button>
        )}
      </div>

      {info.hint && (
        <div style={{ color: muted }}>
          <span style={{ fontWeight: 600 }}>How to fix: </span>
          {info.hint}
        </div>
      )}

      {(info.code || info.requestId) && (
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: muted, display: "flex", gap: "var(--space-3)", flexWrap: "wrap" }}>
          {info.code && <span>code: {info.code}</span>}
          {info.requestId && (
            <button
              type="button"
              onClick={copyId}
              title="Copy request ID (search for it in the backend logs)"
              style={{ background: "none", border: "none", padding: 0, color: "inherit", cursor: "pointer", fontFamily: "inherit", fontSize: "inherit", textDecoration: "underline dotted" }}
            >
              request: {info.requestId} {copied ? "✓ copied" : ""}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

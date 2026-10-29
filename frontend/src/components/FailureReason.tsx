import { useState } from "react";

import { splitFailureReason } from "../utils/failureReason";

// Displays a stored failure reason ("<message> | How to fix: <hint>").

interface Props {
  text: string;
  /** "alert" for failures, "warning" for partial failures (e.g. some segments failed). */
  tone?: "alert" | "warning";
  /** Use colors for a dark (inverse) background. */
  dark?: boolean;
  /**
   * inline  - one truncated line; click to expand the full message and hint below
   *           (the parent should be a wrapping flex row).
   * block   - full message and hint always visible.
   * compact - one truncated line with the full text in a tooltip (for clickable cards).
   */
  variant?: "inline" | "block" | "compact";
  maxWidth?: string;
}

export function FailureReason({ text, tone = "alert", dark = false, variant = "inline", maxWidth = "260px" }: Props) {
  const [expanded, setExpanded] = useState(false);
  const { message, hint } = splitFailureReason(text);

  const color =
    tone === "warning"
      ? "var(--accent-caution)"
      : dark
      ? "var(--accent-alert-on-inverse)"
      : "var(--accent-alert)";
  const icon = tone === "warning" ? "⚠" : "✕";
  const tooltip = hint ? `${message}\n\nHow to fix: ${hint}` : message;

  const oneLine: React.CSSProperties = {
    fontSize: "10px",
    fontFamily: "var(--font-mono)",
    color,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    minWidth: 0,
  };

  const details = (
    <div
      style={{
        fontSize: "10px",
        fontFamily: "var(--font-mono)",
        lineHeight: 1.5,
        color: dark ? "var(--text-on-inverse-secondary)" : "var(--text-secondary)",
        borderLeft: `2px solid ${color}`,
        padding: "2px 0 2px var(--space-2)",
        overflowWrap: "anywhere",
        whiteSpace: "pre-wrap",
      }}
    >
      <div style={{ color }}>{message}</div>
      {hint && (
        <div style={{ marginTop: "2px" }}>
          <span style={{ fontWeight: 700 }}>How to fix: </span>
          {hint}
        </div>
      )}
    </div>
  );

  if (variant === "block") return details;

  if (variant === "compact") {
    return (
      <div title={tooltip} style={{ ...oneLine, maxWidth }}>
        {icon} {message}
      </div>
    );
  }

  return (
    <>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setExpanded((v) => !v);
        }}
        title={expanded ? "Hide details" : tooltip}
        aria-expanded={expanded}
        style={{ ...oneLine, maxWidth, background: "none", border: "none", padding: 0, cursor: "pointer", textAlign: "left" }}
      >
        {expanded ? "▾" : "▸"} {message}
      </button>
      {expanded && <div style={{ flexBasis: "100%", width: "100%" }}>{details}</div>}
    </>
  );
}

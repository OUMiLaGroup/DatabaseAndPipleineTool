import { useState, useRef, useEffect } from "react";
import { reportError } from "../../utils/errorReporter";

const ROUTE_ID_REGEX = /^[^|]+\|[^-]+--[^/]+$/;

export function ImportRouteButton({
  onImport,
  dark = false,
}: {
  onImport: (routeId: string) => Promise<void>;
  dark?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const [value, setValue] = useState("");
  const [touched, setTouched] = useState(false);
  const [importError, setImportError] = useState("");
  const [submitState, setSubmitState] = useState<"idle" | "loading" | "success">("idle");
  const [btnHovered, setBtnHovered] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const trimmed = value.trim().replace("/", "|");
  const isValid = ROUTE_ID_REGEX.test(trimmed);
  const showError = Boolean(importError) || (touched && trimmed.length > 0 && !isValid);

  // Close when clicking outside the component
  useEffect(() => {
    if (!expanded) return;
    function onMouseDown(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        close();
      }
    }
    document.addEventListener("mousedown", onMouseDown);
    return () => document.removeEventListener("mousedown", onMouseDown);
  }, [expanded]);

  function open() {
    setExpanded(true);
    setBtnHovered(false);
    setTouched(false);
    setValue("");
    setSubmitState("idle");
    setImportError("");
    setTimeout(() => inputRef.current?.focus(), 30);
  }

  function close() {
    setExpanded(false);
    setValue("");
    setTouched(false);
    setSubmitState("idle");
  }

  async function handleSubmit() {
    setTouched(true);
    if (!isValid) return;
    setSubmitState("loading");

    try {
      await onImport(trimmed);
      setSubmitState("success");
      setTimeout(close, 900);
    } catch {
      setSubmitState("idle");
      setImportError("Could not queue route. Check the route ID and whether it already exists.");
    }
  }

  return (
    <div ref={wrapperRef} style={{ position: "relative", display: "inline-block", flexShrink: 0 }}>

      {/* Trigger button — kept in DOM with visibility:hidden when expanded so layout never shifts */}
      <button
        onClick={open}
        onMouseEnter={() => setBtnHovered(true)}
        onMouseLeave={() => setBtnHovered(false)}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "6px",
          padding: "var(--space-2) var(--space-3)",
          backgroundColor: dark
            ? btnHovered ? "var(--bg-on-inverse-hover)" : "transparent"
            : "var(--bg-inverse)",
          border: dark ? "1px solid var(--border-on-inverse)" : "none",
          color: dark
            ? btnHovered ? "var(--text-on-inverse)" : "var(--text-on-inverse-secondary)"
            : "var(--text-on-inverse)",
          cursor: "pointer",
          fontFamily: "var(--font-mono)",
          fontSize: "10px",
          fontWeight: 700,
          letterSpacing: "0.07em",
          textTransform: "uppercase",
          opacity: !dark && btnHovered ? 0.8 : 1,
          transition: expanded ? "none" : "var(--transition-fast)",
          visibility: expanded ? "hidden" : "visible",
        }}
      >
        <span style={{ fontSize: "16px", lineHeight: 1, fontWeight: 300 }}>+</span>
        Import Route
      </button>

      {/* Expanded form — absolutely positioned over the button, grows leftward from right edge */}
      {expanded && (
        <form
          onSubmit={(e) => { e.preventDefault(); handleSubmit(); }}
          onKeyDown={(e) => { if (e.key === "Escape") close(); }}
          style={{
            position: "absolute",
            top: 0,
            right: 0,
            display: "flex",
            alignItems: "stretch",
            gap: "3px",
            zIndex: 10,
          }}
        >
          {/* Input wrapper — relative so error message can anchor below it */}
          <div style={{ position: "relative" }}>
            <input
              ref={inputRef}
              type="text"
              value={value}
              onChange={(e) => { setValue(e.target.value); setTouched(false); }}
              onBlur={() => { if (trimmed.length > 0) setTouched(true); }}
              placeholder="db478799b6f9f210|0000000e--9ecd39f6bc"
              spellCheck={false}
              autoComplete="off"
              disabled={submitState !== "idle"}
              style={{
                width: "286px",
                padding: "var(--space-2) var(--space-3)",
                border: `1px solid ${
                  showError
                    ? "var(--accent-alert)"
                    : dark ? "var(--border-on-inverse-strong)" : "var(--border-strong)"
                }`,
                backgroundColor: dark ? "var(--bg-on-inverse)" : "var(--bg-primary)",
                fontFamily: "var(--font-mono)",
                fontSize: "11px",
                color: dark ? "var(--text-on-inverse)" : "var(--text-primary)",
                outline: "none",
                letterSpacing: "0.01em",
                opacity: submitState !== "idle" ? 0.6 : 1,
                transition: "border-color var(--transition-fast)",
              }}
            />
            {/* Error floats below the input — absolutely positioned so it never shifts the layout */}
            {showError && (
              <div style={{
                position: "absolute",
                top: "calc(100% + 4px)",
                left: 0,
                fontSize: "10px",
                fontFamily: "var(--font-mono)",
                color: dark ? "var(--accent-alert-on-inverse)" : "var(--accent-alert)",
                letterSpacing: "0.02em",
                whiteSpace: "nowrap",
                pointerEvents: "none",
              }}>
                {importError || "Expected: db478799b6f9f210|0000000e--9ecd39f6bc"}
              </div>
            )}
          </div>

          <button
            type="submit"
            disabled={submitState !== "idle"}
            style={{
              padding: "var(--space-2) var(--space-3)",
              backgroundColor: submitState === "success"
                ? dark ? "var(--accent-go-on-inverse)" : "var(--accent-go)"
                : dark ? "var(--bg-on-inverse-hover)" : "var(--bg-inverse)",
              border: `1px solid ${dark
                ? submitState === "success" ? "var(--accent-go)" : "var(--border-on-inverse)"
                : "transparent"
              }`,
              color: submitState === "success" && dark ? "var(--accent-go)" : "var(--text-on-inverse)",
              cursor: submitState !== "idle" ? "default" : "pointer",
              fontFamily: "var(--font-mono)",
              fontSize: "10px",
              fontWeight: 700,
              letterSpacing: "0.07em",
              textTransform: "uppercase",
              whiteSpace: "nowrap",
              transition: "background-color var(--transition-base), border-color var(--transition-base), color var(--transition-base)",
            }}
          >
            {submitState === "loading" ? "…" : submitState === "success" ? "✓ Queued" : "↓ Download"}
          </button>

          <button
            type="button"
            onClick={close}
            disabled={submitState === "loading"}
            style={{
              padding: "var(--space-2) var(--space-3)",
              backgroundColor: "transparent",
              border: `1px solid ${dark ? "var(--border-on-inverse-subtle)" : "var(--border-subtle)"}`,
              color: dark ? "var(--text-on-inverse-muted)" : "var(--text-muted)",
              cursor: submitState === "loading" ? "default" : "pointer",
              fontFamily: "var(--font-mono)",
              fontSize: "11px",
              lineHeight: 1,
              opacity: submitState === "loading" ? 0.4 : 1,
            }}
          >
            ✕
          </button>
        </form>
      )}
    </div>
  );
}

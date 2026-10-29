import { useState } from "react";
import type { Segment } from "../../api/types";
import { formatOffset, formatDuration } from "../../utils/formatters";
import { SegmentThumbnail } from "./SegmentThumbnail";
import { SegStatusBadge } from "./SegStatusBadge";
import { FailureReason } from "../FailureReason";

export function SegmentCard({ segment, onClick }: { segment: Segment; onClick: () => void }) {
  const [hovered, setHovered] = useState(false);

  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{ backgroundColor: "var(--bg-surface)", border: "1px solid var(--border-subtle)", outline: hovered ? "2px solid var(--border-black)" : "2px solid transparent", outlineOffset: "-1px", cursor: "pointer", display: "flex", flexDirection: "column", overflow: "hidden" }}
    >
      <div style={{ position: "relative", height: "96px", overflow: "hidden", flexShrink: 0 }}>
        <SegmentThumbnail segment={segment} hovered={hovered} />
        <div style={{ position: "absolute", inset: 0, background: "var(--overlay-thumbnail-gradient)", pointerEvents: "none" }} />
        <div style={{ position: "absolute", top: "var(--space-2)", left: "var(--space-2)" }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-lg)", fontWeight: 700, color: "var(--text-on-inverse)", lineHeight: 1, letterSpacing: "-0.02em", textShadow: "0 1px 4px var(--overlay-thumbnail-dark)" }}>
            {String(segment.index).padStart(2, "0")}
          </span>
        </div>
        <div style={{ position: "absolute", bottom: "var(--space-2)", left: "var(--space-2)" }}>
          <SegStatusBadge status={segment.status} />
        </div>
        <div style={{ position: "absolute", bottom: "var(--space-2)", right: "var(--space-2)", backgroundColor: "var(--overlay-thumbnail-dark)", backdropFilter: "blur(4px)", padding: "2px 5px" }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "9px", fontWeight: 700, color: "var(--text-on-inverse)", letterSpacing: "0.04em" }}>
            {formatOffset(segment.startSeconds)}
          </span>
        </div>
      </div>

      <div style={{ padding: "var(--space-2) var(--space-3)", display: "flex", flexDirection: "column", gap: "var(--space-2)", flex: 1 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-secondary)" }}>{formatDuration(segment.durationSeconds)}</span>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-muted)" }}>{segment.frameCount.toLocaleString()} fr</span>
        </div>
        {segment.status === "failed" && segment.error ? (
          // The card is clickable, so show the reason as one line with a tooltip
          <FailureReason text={segment.error} variant="compact" maxWidth="100%" />
        ) : (
        <div style={{ fontSize: "9px", fontFamily: "var(--font-mono)", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.07em" }}>
          {segment.status === "failed"
            ? "— processing failed"
            : segment.status === "uploading" || segment.status === "downloading"
            ? "— in progress…"
            : segment.status === "uploaded"
            ? "— uploaded"
            : "— pending"}
        </div>
        )}
      </div>
    </div>
  );
}

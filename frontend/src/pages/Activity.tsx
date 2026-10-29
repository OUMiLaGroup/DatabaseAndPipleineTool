import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useInfiniteQuery } from "@tanstack/react-query";
import { listAuditLogs } from "../api/audit_logs";
import type { AuditLogEntry, AuditOutcome } from "../api/audit_logs";
import { ErrorNotice } from "../components/ErrorNotice";
import { FailureReason } from "../components/FailureReason";
import { AUDIT_ACTION_GROUPS, AUDIT_ACTION_LABELS, AUDIT_OUTCOME_STYLE, AUDIT_SOURCES } from "../utils/auditConfig";
import { formatRelativeTime } from "../utils/formatters";

const PAGE_SIZE = 100;

const selectStyle: React.CSSProperties = {
  padding: "var(--space-2) var(--space-3)",
  border: "1px solid var(--border-subtle)",
  backgroundColor: "var(--bg-surface)",
  fontSize: "var(--text-sm)",
  color: "var(--text-primary)",
  outline: "none",
  cursor: "pointer",
};

const cellStyle: React.CSSProperties = {
  padding: "var(--space-2) var(--space-3)",
  borderBottom: "1px solid var(--border-subtle)",
  verticalAlign: "top",
  fontSize: "11px",
  fontFamily: "var(--font-mono)",
  color: "var(--text-secondary)",
};

/**
 * Audit log: who/what did something, to what, and whether it worked.
 * Filters live in the URL (e.g. /activity?route=<id>&outcome=failure) so views can be shared.
 */
export default function Activity() {
  const [params, setParams] = useSearchParams();
  const routeId = params.get("route") ?? "";
  const outcome = (params.get("outcome") ?? "") as AuditOutcome | "";
  const source = params.get("source") ?? "";
  const action = params.get("action") ?? "";

  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };

  const query = useInfiniteQuery({
    queryKey: ["audit-logs", routeId, outcome, source, action],
    queryFn: ({ pageParam }) =>
      listAuditLogs({
        routeId: routeId || undefined,
        outcome: outcome || undefined,
        source: source || undefined,
        action: action || undefined,
        beforeId: pageParam,
        limit: PAGE_SIZE,
      }),
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (lastPage) => (lastPage.length === PAGE_SIZE ? lastPage[lastPage.length - 1].id : undefined),
    refetchInterval: 5000,
  });

  const entries = useMemo(() => query.data?.pages.flat() ?? [], [query.data]);
  const hasFilters = Boolean(routeId || outcome || source || action);

  return (
    <div style={{ paddingBottom: "var(--space-12)" }}>
      <div style={{ marginBottom: "var(--space-5)" }}>
        <h1 style={{ fontFamily: "var(--font-sans)", fontSize: "var(--text-2xl)", fontWeight: 600, color: "var(--text-primary)" }}>
          Activity
        </h1>
        <p style={{ color: "var(--text-secondary)", fontSize: "var(--text-sm)", marginTop: "2px" }}>
          Audit log of every change made in the app and the outcome of every pipeline job, newest first
        </p>
      </div>

      {/* Filters */}
      <div style={{ display: "flex", gap: "var(--space-2)", marginBottom: "var(--space-4)", flexWrap: "wrap" }}>
        <input
          type="search"
          placeholder="Filter by route ID…"
          value={routeId}
          onChange={(e) => setFilter("route", e.target.value.trim())}
          style={{ flex: 1, minWidth: "220px", padding: "var(--space-2) var(--space-3)", border: "1px solid var(--border-subtle)", backgroundColor: "var(--bg-surface)", fontFamily: "var(--font-mono)", fontSize: "var(--text-sm)", color: "var(--text-primary)", outline: "none" }}
        />
        <select aria-label="Outcome" value={outcome} onChange={(e) => setFilter("outcome", e.target.value)} style={selectStyle}>
          <option value="">All outcomes</option>
          <option value="failure">Failed</option>
          <option value="warning">Warnings</option>
          <option value="success">Succeeded</option>
        </select>
        <select aria-label="Type" value={action} onChange={(e) => setFilter("action", e.target.value)} style={selectStyle}>
          <option value="">All types</option>
          {AUDIT_ACTION_GROUPS.map((g) => (
            <option key={g.value} value={g.value}>{g.label}</option>
          ))}
        </select>
        <select aria-label="Source" value={source} onChange={(e) => setFilter("source", e.target.value)} style={selectStyle}>
          <option value="">All sources</option>
          {AUDIT_SOURCES.map((s) => (
            <option key={s} value={s}>{s === "api" ? "App / API" : s}</option>
          ))}
        </select>
        {hasFilters && (
          <button type="button" onClick={() => setParams(new URLSearchParams(), { replace: true })} style={{ ...selectStyle, fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)" }}>
            Clear filters
          </button>
        )}
      </div>

      {query.error != null && (
        <div style={{ marginBottom: "var(--space-4)" }}>
          <ErrorNotice error={query.error} title="Could not load activity" />
        </div>
      )}

      {query.isLoading ? (
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-muted)" }}>Loading…</div>
      ) : entries.length === 0 && query.error == null ? (
        <div style={{ padding: "var(--space-8)", border: "1px dashed var(--border-subtle)", textAlign: "center", fontFamily: "var(--font-mono)", fontSize: "var(--text-sm)", color: "var(--text-muted)" }}>
          {hasFilters ? "No activity matches these filters." : "No activity recorded yet."}
        </div>
      ) : (
        <div style={{ overflowX: "auto", border: "1px solid var(--border-subtle)", backgroundColor: "var(--bg-surface)" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", minWidth: "760px" }}>
            <thead>
              <tr>
                {["Time", "Outcome", "Action", "Target", "Details", "Source"].map((h) => (
                  <th key={h} style={{ ...cellStyle, textAlign: "left", fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-muted)", fontWeight: 600 }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => (
                <ActivityRow key={entry.id} entry={entry} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {query.hasNextPage && (
        <div style={{ marginTop: "var(--space-3)", textAlign: "center" }}>
          <button
            type="button"
            onClick={() => query.fetchNextPage()}
            disabled={query.isFetchingNextPage}
            style={{ ...selectStyle, fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)" }}
          >
            {query.isFetchingNextPage ? "Loading…" : "Load older activity"}
          </button>
        </div>
      )}
    </div>
  );
}

function ActivityRow({ entry }: { entry: AuditLogEntry }) {
  const style = AUDIT_OUTCOME_STYLE[entry.outcome] ?? AUDIT_OUTCOME_STYLE.failure;
  const label = AUDIT_ACTION_LABELS[entry.action] ?? entry.action;

  return (
    <tr>
      <td style={{ ...cellStyle, whiteSpace: "nowrap" }} title={new Date(entry.createdAt).toLocaleString()}>
        {formatRelativeTime(entry.createdAt)}
      </td>
      <td style={{ ...cellStyle, whiteSpace: "nowrap" }}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: "5px", color: style.color, fontWeight: 700, fontSize: "10px", textTransform: "uppercase", letterSpacing: "0.07em" }}>
          <span style={{ width: "6px", height: "6px", borderRadius: "50%", backgroundColor: style.color }} />
          {style.label}
        </span>
      </td>
      <td style={{ ...cellStyle, color: "var(--text-primary)", whiteSpace: "nowrap" }} title={entry.action}>
        {label}
      </td>
      <td style={{ ...cellStyle, maxWidth: "280px", overflowWrap: "anywhere" }}>
        {entry.routeId && entry.entityType !== "route" ? (
          <>
            <Link to={`/routes/${encodeURIComponent(entry.routeId)}`} style={{ color: "var(--text-primary)" }}>
              {entry.routeId}
            </Link>
            <div style={{ color: "var(--text-muted)" }}>{entry.entityId?.replace(`${entry.routeId}/`, "")}</div>
          </>
        ) : entry.routeId ? (
          <Link to={`/routes/${encodeURIComponent(entry.routeId)}`} style={{ color: "var(--text-primary)" }}>
            {entry.entityId ?? entry.routeId}
          </Link>
        ) : (
          entry.entityId ?? "—"
        )}
      </td>
      <td style={{ ...cellStyle, maxWidth: "420px" }}>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "var(--space-2)" }}>
          {entry.message ? (
            <FailureReason text={entry.message} tone={entry.outcome === "failure" ? "alert" : "warning"} maxWidth="360px" />
          ) : (
            <span style={{ color: "var(--text-muted)" }}>—</span>
          )}
        </div>
        {(entry.errorCode || entry.requestId) && (
          <div style={{ marginTop: "2px", fontSize: "10px", color: "var(--text-muted)" }}>
            {entry.errorCode && <span>code: {entry.errorCode}</span>}
            {entry.errorCode && entry.requestId && <span> · </span>}
            {entry.requestId && <span title="Search the backend logs for this ID">request: {entry.requestId}</span>}
          </div>
        )}
      </td>
      <td style={{ ...cellStyle, whiteSpace: "nowrap" }}>{entry.source === "api" ? "App / API" : entry.source}</td>
    </tr>
  );
}

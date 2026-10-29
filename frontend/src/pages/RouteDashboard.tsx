import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { listRoutes } from "../api/routes";
import { listSegments } from "../api/segments";
import { listJobRuns } from "../api/job_runs";
import type { Segment, JobRun } from "../api/types";
import { ROUTE_TERMINAL_STATUSES, SEGMENT_TERMINAL_STATUSES, JOB_TERMINAL_STATUSES } from "../api/types";
import { getStatusCfg } from "../utils/statusConfig";
import { RouteCard } from "../components/route-dashboard/RouteCard";
import { StatCard } from "../components/route-dashboard/StatCard";
import { LiveDot } from "../components/route-dashboard/LiveDot";
import { ImportRouteButton } from "../components/route-dashboard/ImportRouteButton";
import { createRoute } from "../api/routes";
import { useQueryClient } from "@tanstack/react-query";
import { ErrorNotice } from "../components/ErrorNotice";
type SortKey = "date" | "status" | "segments";

export default function RouteDashboard() {
  const navigate = useNavigate();
  const queryClient = useQueryClient(); 
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [sortBy, setSortBy] = useState<SortKey>("date");

  // ── Queries with live polling ───────────────────────────────────────────────

  const routesQuery = useQuery({
    queryKey: ["routes"],
    queryFn: listRoutes,
    refetchInterval: (query) => {
      const routes = query.state.data ?? [];
      // Active routes poll every 5s; fall back to 30s so newly created routes are detected
      return routes.some((r) => !ROUTE_TERMINAL_STATUSES.includes(r.status)) ? 5000 : 30000;
    },
  });

  const segmentsQuery = useQuery({
    queryKey: ["segments"],
    queryFn: listSegments,
    refetchInterval: (query) => {
      const segs = query.state.data ?? [];
      return segs.some((s) => !SEGMENT_TERMINAL_STATUSES.includes(s.status)) ? 5000 : false;
    },
  });

  const jobRunsQuery = useQuery({
    queryKey: ["jobRuns"],
    queryFn: listJobRuns,
    refetchInterval: (query) => {
      const runs = query.state.data ?? [];
      if (runs.length === 0) return 10000;
      return runs.some((r) => !JOB_TERMINAL_STATUSES.includes(r.status)) ? 3000 : false;
    },
  });

  const routes = routesQuery.data ?? [];
  const segments = segmentsQuery.data ?? [];
  const jobRuns = jobRunsQuery.data ?? [];
  const loading = routesQuery.isLoading;
  const error = routesQuery.error ?? null;
  const isPolling = routesQuery.isFetching || segmentsQuery.isFetching || jobRunsQuery.isFetching;

  // ── Computed per-route maps ─────────────────────────────────────────────────

  const segmentsByRoute = useMemo(() => {
    const map: Record<string, Segment[]> = {};
    for (const s of segments) {
      if (!map[s.routeId]) map[s.routeId] = [];
      map[s.routeId].push(s);
    }
    return map;
  }, [segments]);

  const jobRunsByRoute = useMemo(() => {
    const map: Record<string, JobRun[]> = {};
    for (const j of jobRuns) {
      if (!map[j.routeId]) map[j.routeId] = [];
      map[j.routeId].push(j);
    }
    return map;
  }, [jobRuns]);

  // ── Stats ───────────────────────────────────────────────────────────────────

  const stats = useMemo(() => {
    const totalSegments = segments.length;
    const totalUploaded = segments.filter((s) => s.status === "uploaded").length;
    return {
      total: routes.length,
      totalSegments,
      overallPct: totalSegments > 0 ? Math.round((totalUploaded / totalSegments) * 100) : 0,
      pending: routes.filter((r) => r.status === "download queue" || r.status === "upload queue").length,
      inProgress: routes.filter((r) => {
        const routeActive = r.status === "downloading" || r.status === "uploading";
        const jobActive = (jobRunsByRoute[r.id] ?? []).some((j) => j.status === "queued" || j.status === "running");
        return routeActive || jobActive;
      }).length,
      completed: routes.filter((r) => {
        if (r.status !== "uploaded") return false;
        const runs = jobRunsByRoute[r.id] ?? [];
        return runs.length === 0 || runs.every((j) => JOB_TERMINAL_STATUSES.includes(j.status));
      }).length,
      failed: routes.filter((r) => r.status === "failed").length,
    };
  }, [routes, segments, jobRunsByRoute]);

  // ── Filter + sort ───────────────────────────────────────────────────────────

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    let list = routes.filter((r) => {
      if (q && !r.id.toLowerCase().includes(q)) return false;
      if (statusFilter !== "all" && r.status !== statusFilter) return false;
      return true;
    });

    list.sort((a, b) => {
      switch (sortBy) {
        case "date":     return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
        case "status":   return a.status.localeCompare(b.status);
        case "segments": return (segmentsByRoute[b.id]?.length ?? 0) - (segmentsByRoute[a.id]?.length ?? 0);
      }
    });
    return list;
  }, [routes, search, statusFilter, sortBy, segmentsByRoute]);

  return (
    <div style={{ paddingBottom: "var(--space-12)" }}>
      {/* Header */}
      <div style={{ marginBottom: "var(--space-5)", display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
        <div style={{ flex: 1 }}>
          <h1 style={{ fontFamily: "var(--font-sans)", fontSize: "var(--text-2xl)", fontWeight: 600, color: "var(--text-primary)" }}>
            Routes
          </h1>
          <p style={{ color: "var(--text-secondary)", fontSize: "var(--text-sm)", marginTop: "2px" }}>
            Annotation pipeline overview
          </p>
        </div>
        {isPolling && <LiveDot />}
      <ImportRouteButton
        onImport={async (routeId) => {
          try {
            await createRoute(routeId);
            queryClient.invalidateQueries({ queryKey: ["routes"] });
          } catch (err) {
            console.error("Failed to import route:", err);
            throw err;
          }
        }}
      />
      </div>

      {/* Stat strip */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(100px, 1fr))", gap: "1px", backgroundColor: "var(--border-subtle)", border: "1px solid var(--border-subtle)", marginBottom: "var(--space-5)" }}>
        <StatCard label="Total Routes"  value={loading ? "…" : stats.total} />
        <StatCard label="Segments"      value={loading ? "…" : stats.totalSegments} />
        <StatCard label="Uploaded"      value={loading ? "…" : `${stats.overallPct}%`} />
        <StatCard label="Pending"       value={loading ? "…" : stats.pending} />
        <StatCard label="In Progress"   value={loading ? "…" : stats.inProgress}  accentColor={stats.inProgress  > 0 ? "var(--accent-caution)" : undefined} />
        <StatCard label="Completed"     value={loading ? "…" : stats.completed}   accentColor={stats.completed   > 0 ? "var(--accent-go)"      : undefined} />
        <StatCard label="Failed"        value={loading ? "…" : stats.failed}      accentColor={stats.failed      > 0 ? "var(--accent-alert)"   : undefined} />
      </div>

      {/* Filter bar */}
      <div style={{ display: "flex", gap: "var(--space-2)", marginBottom: "var(--space-4)", flexWrap: "wrap" }}>
        <input
          type="search"
          placeholder="Search route ID…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ flex: 1, minWidth: "200px", padding: "var(--space-2) var(--space-3)", border: "1px solid var(--border-subtle)", backgroundColor: "var(--bg-surface)", fontFamily: "var(--font-mono)", fontSize: "var(--text-sm)", color: "var(--text-primary)", outline: "none" }}
        />
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={{ padding: "var(--space-2) var(--space-3)", border: "1px solid var(--border-subtle)", backgroundColor: "var(--bg-surface)", fontSize: "var(--text-sm)", color: "var(--text-primary)", outline: "none", cursor: "pointer" }}>
          <option value="all">All Statuses</option>
          <option value="download queue">Queued</option>
          <option value="downloading">Downloading</option>
          <option value="upload queue">Upload Queue</option>
          <option value="uploading">Uploading</option>
          <option value="uploaded">Uploaded</option>
          <option value="failed">Failed</option>
        </select>
        <select value={sortBy} onChange={(e) => setSortBy(e.target.value as SortKey)} style={{ padding: "var(--space-2) var(--space-3)", border: "1px solid var(--border-subtle)", backgroundColor: "var(--bg-surface)", fontSize: "var(--text-sm)", color: "var(--text-primary)", outline: "none", cursor: "pointer" }}>
          <option value="date">Sort: Date</option>
          <option value="status">Sort: Status</option>
          <option value="segments">Sort: Segments</option>
        </select>
      </div>

      {/* Count */}
      <div style={{ fontSize: "10px", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.09em", fontWeight: 600, marginBottom: "var(--space-4)" }}>
        {loading ? "Loading…" : `${filtered.length} route${filtered.length !== 1 ? "s" : ""}${statusFilter !== "all" ? ` · ${getStatusCfg(statusFilter).label}` : ""}`}
      </div>

      {/* Error */}
      {error != null && (
        <div style={{ marginBottom: "var(--space-4)" }}>
          <ErrorNotice error={error} title="Could not load routes" />
        </div>
      )}

      {/* Loading skeleton */}
      {loading && !error && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: "var(--space-4)" }}>
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} style={{ backgroundColor: "var(--bg-surface)", border: "1px solid var(--border-subtle)", height: "240px", opacity: 0.4 }} />
          ))}
        </div>
      )}

      {/* Grid */}
      {!loading && !error && (
        filtered.length === 0 ? (
          <div style={{ padding: "var(--space-12)", textAlign: "center", color: "var(--text-muted)", border: "1px dashed var(--border-subtle)", fontFamily: "var(--font-mono)", fontSize: "var(--text-sm)" }}>
            No routes match your filters.
          </div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: "var(--space-4)" }}>
            {filtered.map((route) => (
              <RouteCard
                key={route.id}
                route={route}
                segments={segmentsByRoute[route.id] ?? []}
                jobRuns={jobRunsByRoute[route.id] ?? []}
                onClick={() => navigate(`/routes/${encodeURIComponent(route.id)}`)}
                onDeleted={() => queryClient.invalidateQueries({ queryKey: ["routes"] })}
              />
            ))}
          </div>
        )
      )}
    </div>
  );
}

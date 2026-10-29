import { useState, useRef, useEffect, useMemo } from "react";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { listJobDefinitions } from "../../api/job_definitions";
import { createJobRun } from "../../api/job_runs";
import { CAMERAS } from "../../api/types";
import type { JobRun } from "../../api/types";
import { formatCamera } from "../../utils/formatters";
import { ErrorNotice } from "../ErrorNotice";

const selectStyle: React.CSSProperties = {
  flex: 1,
  minWidth: 0,
  padding: "var(--space-2) var(--space-3)",
  border: "1px solid var(--border-on-inverse-strong)",
  backgroundColor: "var(--bg-on-inverse)",
  color: "var(--text-on-inverse)",
  fontFamily: "var(--font-mono)",
  fontSize: "11px",
  outline: "none",
  cursor: "pointer",
  colorScheme: "dark",
};

const optionStyle: React.CSSProperties = {
  backgroundColor: "var(--bg-inverse)",
  color: "var(--text-on-inverse)",
};

export function CreateJobRunButton({ routeId }: { routeId: string }) {
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = useState(false);
  const [hovered, setHovered] = useState(false);
  const [jobDefId, setJobDefId] = useState<number | "">("");
  const [camera, setCamera] = useState<string>(CAMERAS[0]);
  const [error, setError] = useState<unknown>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  const { data: jobDefsRaw = [], isLoading: defsLoading } = useQuery({
    queryKey: ["job-definitions"],
    queryFn: listJobDefinitions,
    enabled: expanded,
  });

  const jobDefs = useMemo(
    () => [...jobDefsRaw].sort((a, b) => a.id - b.id),
    [jobDefsRaw],
  );

  const createMutation = useMutation({
    mutationFn: createJobRun,
    onMutate: async (vars) => {
      await queryClient.cancelQueries({ queryKey: ["jobRuns", routeId] });
      const previous = queryClient.getQueryData<JobRun[]>(["jobRuns", routeId]) ?? [];
      const optimisticNum = -Date.now();
      const optimistic: JobRun = {
        jobRunNum: optimisticNum,
        jobDefId: vars.jobDefId,
        routeId: vars.routeId,
        camera: vars.camera,
        status: "queued",
        queuedAt: new Date().toISOString(),
        startedAt: null,
        finishedAt: null,
        error: null,
        stats: null,
      };
      queryClient.setQueryData<JobRun[]>(["jobRuns", routeId], (old = []) => [...old, optimistic]);
      return { previous, optimisticNum };
    },
    onSuccess: (newRun: JobRun, _vars, ctx) => {
      queryClient.setQueryData<JobRun[]>(["jobRuns", routeId], (old = []) => {
        const filtered = (old ?? []).filter((r) => r.jobRunNum !== ctx?.optimisticNum);
        return [...filtered, newRun];
      });
      close();
    },
    onError: (err: unknown, _vars, ctx) => {
      if (ctx) queryClient.setQueryData(["jobRuns", routeId], ctx.previous);
      setError(err);
    },
    // Shown inline in the form below, so no global toast
    meta: { inlineError: true },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["jobRuns", routeId] });
    },
  });

  useEffect(() => {
    if (!expanded) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") close();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [expanded]);

  useEffect(() => {
    if (expanded && jobDefId === "" && jobDefs.length > 0) {
      setJobDefId(jobDefs[0].id);
    }
  }, [expanded, jobDefId, jobDefs]);

  function open() {
    setExpanded(true);
    setError(null);
    setJobDefId("");
    setCamera(CAMERAS[0]);
  }

  function close() {
    setExpanded(false);
    setError(null);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (jobDefId === "" || createMutation.isPending) return;
    setError(null);
    createMutation.mutate({
      jobDefId: Number(jobDefId),
      routeId,
      camera,
    });
  }

  const submitting = createMutation.isPending;
  const canSubmit = jobDefId !== "" && !submitting;

  if (!expanded) {
    return (
      <button
        ref={(el) => { wrapperRef.current = el as unknown as HTMLDivElement; }}
        type="button"
        onClick={open}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        style={{
          width: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: "var(--space-2)",
          padding: "var(--space-3) var(--space-4)",
          background: "none",
          border: `1px dashed ${hovered ? "var(--text-on-inverse-secondary)" : "var(--border-on-inverse)"}`,
          color: hovered ? "var(--text-on-inverse)" : "var(--text-on-inverse-secondary)",
          cursor: "pointer",
          fontFamily: "var(--font-mono)",
          fontSize: "11px",
          fontWeight: 700,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          transition: "var(--transition-fast)",
        }}
      >
        <span style={{ fontSize: "16px", lineHeight: 1, fontWeight: 300 }}>+</span>
        New Job Run
      </button>
    );
  }

  return (
    <form
      ref={(el) => { wrapperRef.current = el as unknown as HTMLDivElement; }}
      onSubmit={handleSubmit}
      style={{
        width: "100%",
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-2)",
        padding: "var(--space-3) var(--space-4)",
        border: "1px solid var(--border-on-inverse)",
        backgroundColor: "var(--bg-on-inverse-subtle)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "var(--space-2)" }}>
        <span style={{ fontSize: "9px", fontFamily: "var(--font-mono)", color: "var(--text-on-inverse-dim)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
          New Job Run
        </span>
        <button
          type="button"
          onClick={close}
          disabled={submitting}
          aria-label="Cancel"
          style={{
            padding: "0 var(--space-2)",
            background: "transparent",
            border: "none",
            color: "var(--text-on-inverse-muted)",
            cursor: submitting ? "default" : "pointer",
            fontFamily: "var(--font-mono)",
            fontSize: "12px",
            lineHeight: 1,
            opacity: submitting ? 0.4 : 1,
          }}
        >
          ✕
        </button>
      </div>

      <div style={{ display: "flex", gap: "var(--space-2)", alignItems: "stretch", flexWrap: "wrap" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: "4px", flex: 2, minWidth: "200px" }}>
          <label style={{ fontSize: "9px", fontFamily: "var(--font-mono)", color: "var(--text-on-inverse-dim)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
            Job Definition
          </label>
          <select
            value={jobDefId}
            onChange={(e) => setJobDefId(e.target.value === "" ? "" : Number(e.target.value))}
            disabled={submitting || defsLoading}
            style={selectStyle}
          >
            {(defsLoading || jobDefs.length === 0) && (
              <option value="" style={optionStyle}>
                {defsLoading ? "Loading…" : "No job definitions"}
              </option>
            )}
            {jobDefs.map((d) => (
              <option key={d.id} value={d.id} style={optionStyle}>
                #{d.id} · {d.name}
              </option>
            ))}
          </select>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "4px", flex: 1, minWidth: "140px" }}>
          <label style={{ fontSize: "9px", fontFamily: "var(--font-mono)", color: "var(--text-on-inverse-dim)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
            Camera
          </label>
          <select
            value={camera}
            onChange={(e) => setCamera(e.target.value)}
            disabled={submitting}
            style={selectStyle}
          >
            {CAMERAS.map((c) => (
              <option key={c} value={c} style={optionStyle}>{formatCamera(c)}</option>
            ))}
          </select>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "4px", justifyContent: "flex-end" }}>
          <button
            type="submit"
            disabled={!canSubmit}
            style={{
              padding: "var(--space-2) var(--space-4)",
              backgroundColor: canSubmit ? "var(--accent-go)" : "var(--bg-on-inverse-hover)",
              border: "1px solid var(--border-on-inverse)",
              color: canSubmit ? "var(--bg-inverse)" : "var(--text-on-inverse-muted)",
              cursor: canSubmit ? "pointer" : "default",
              fontFamily: "var(--font-mono)",
              fontSize: "10px",
              fontWeight: 700,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              whiteSpace: "nowrap",
              opacity: canSubmit ? 1 : 0.6,
              transition: "var(--transition-fast)",
            }}
          >
            {submitting ? "Queueing…" : "Queue Job"}
          </button>
        </div>
      </div>

      {error != null && <ErrorNotice error={error} title="Could not create job run" />}
    </form>
  );
}

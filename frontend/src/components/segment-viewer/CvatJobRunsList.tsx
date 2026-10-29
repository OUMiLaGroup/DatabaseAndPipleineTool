import { useQuery, useQueries, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { getJobSegmentRunsForSegment, importToCvat, deleteFromCvat, getCvatImportForRun } from "../../api/job_segment_run";
import { listJobDefinitions } from "../../api/job_definitions";
import type { CvatImport, JobSegmentRun } from "../../api/types";
import { CVAT_IN_PROGRESS_STATUSES } from "../../api/types";
import { STATUS_COLOR, STATUS_LABEL, resolveAction } from "../../utils/jobSegmentRunConfig";
import type { CvatAction } from "../../utils/jobSegmentRunConfig";
import { formatCamera } from "../../utils/formatters";
import { CvatActionButton } from "./CvatActionButton";
import { FailureReason } from "../FailureReason";

type RunKeyFields = Pick<JobSegmentRun, "jobDefId" | "jobRunNum" | "segmentId" | "camera">;
const runKey = (r: RunKeyFields) => `${r.jobDefId}-${r.jobRunNum}-${r.segmentId}-${r.camera}`;

// ─── Main component ───────────────────────────────────────────────────────────

export function CvatJobRunsList({ routeId, segmentId }: { routeId: string; segmentId: number }) {
  const queryClient = useQueryClient();

  const { data: segmentRuns = [], isLoading: runsLoading } = useQuery({
    queryKey: ["job-segment-runs", routeId, segmentId],
    queryFn: () => getJobSegmentRunsForSegment(routeId, segmentId),
    enabled: !!routeId,
    refetchInterval: (q) =>
      (q.state.data ?? []).some((r) => r.status === "queued" || r.status === "running") ? 5000 : false,
  });

  const { data: jobDefs = [] } = useQuery({ queryKey: ["job-definitions"], queryFn: listJobDefinitions });

  const importQueryKey = (r: RunKeyFields) =>
    ["cvat-import", routeId, r.jobDefId, r.jobRunNum, r.segmentId, r.camera] as const;

  const importQueries = useQueries({
    queries: segmentRuns.map((run) => ({
      queryKey: importQueryKey(run),
      queryFn: () => getCvatImportForRun({ routeId, jobDefId: run.jobDefId, jobRunNum: run.jobRunNum, segmentId: run.segmentId, camera: run.camera }),
      enabled: !!routeId,
      placeholderData: keepPreviousData,
      refetchInterval: (q: { state: { data?: CvatImport | null } }) =>
        q.state.data && CVAT_IN_PROGRESS_STATUSES.includes(q.state.data.status) ? 3000 : false,
    })),
  });

  const loadMutation = useMutation({
    mutationFn: (run: JobSegmentRun) =>
      importToCvat({ routeId, jobDefId: run.jobDefId, jobRunNum: run.jobRunNum, segmentId: run.segmentId, camera: run.camera }),
    onSuccess: (newImport) => {
      const key = importQueryKey(newImport);
      queryClient.setQueryData<CvatImport | null>(key, newImport);
      return queryClient.invalidateQueries({ queryKey: key });
    },
    meta: { errorTitle: "Could not load segment into CVAT" },
  });

  const unloadMutation = useMutation({
    mutationFn: (run: JobSegmentRun) =>
      deleteFromCvat({ routeId, jobDefId: run.jobDefId, jobRunNum: run.jobRunNum, segmentId: run.segmentId, camera: run.camera }),
    onSuccess: (_, run) => {
      const key = importQueryKey(run);
      queryClient.setQueryData<CvatImport | null>(key, null);
      return queryClient.invalidateQueries({ queryKey: key });
    },
    meta: { errorTitle: "Could not remove segment from CVAT" },
  });

  const pendingKey   = loadMutation.isPending   && loadMutation.variables   ? runKey(loadMutation.variables)   : null;
  const unloadingKey = unloadMutation.isPending && unloadMutation.variables ? runKey(unloadMutation.variables) : null;
  const loading = runsLoading || importQueries.some((q) => q.isLoading);
  const sortedRuns = [...segmentRuns].sort((a, b) => b.jobRunNum - a.jobRunNum);

  return (
    <div className="border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-[var(--space-5)]">
      <div className="text-[10px] [font-family:var(--font-mono)] uppercase tracking-[0.09em] text-[var(--text-muted)] font-semibold mb-[var(--space-4)]">
        Job Runs
      </div>

      {loading ? (
        <div className="[font-family:var(--font-mono)] text-[11px] text-[var(--text-muted)] py-[var(--space-3)]">Loading…</div>
      ) : sortedRuns.length === 0 ? (
        <div className="[font-family:var(--font-mono)] text-[11px] text-[var(--text-muted)] py-[var(--space-3)]">No job runs for this segment.</div>
      ) : (
        <div className="flex flex-col gap-[var(--space-2)]">
          {sortedRuns.map((run) => {
            const key = runKey(run);
            const originalIdx = segmentRuns.indexOf(run);
            const imp = importQueries[originalIdx]?.data ?? null;
            const defName = jobDefs.find((d) => d.id === run.jobDefId)?.name ?? `def ${run.jobDefId}`;
            return (
              <RunRow
                key={key}
                run={run}
                imp={imp}
                action={jobDefs.find((d) => d.id === run.jobDefId)?.type === "depth"
                  ? { state: "unavailable", label: "Depth: use route export" }
                  : resolveAction(run, imp, false)}
                defName={defName}
                isLoading={key === pendingKey}
                isUnloading={key === unloadingKey}
                onLoad={() => loadMutation.mutate(run)}
                onUnload={() => unloadMutation.mutate(run)}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}

// ─── Row ──────────────────────────────────────────────────────────────────────

function RunRow({ run, imp, action, defName, isLoading, isUnloading, onLoad, onUnload }: { run: JobSegmentRun; imp: CvatImport | null; action: CvatAction; defName: string; isLoading: boolean; isUnloading: boolean; onLoad: () => void; onUnload: () => void }) {
  const color    = STATUS_COLOR[run.status];
  const isActive = run.status === "queued" || run.status === "running";
  const resolvedAction: CvatAction =
    isUnloading ? { state: "in_progress", label: "Unloading…" } :
    isLoading   ? { state: "in_progress", label: "Loading…"   } :
    action;

  return (
    <div className="flex flex-wrap items-center gap-[var(--space-3)] py-[calc(var(--space-2)+1px)] px-[var(--space-3)] bg-[var(--bg-elevated)] border border-[var(--border-subtle)]">
      <div className="flex items-center gap-[6px] min-w-[90px]">
        {isActive && <span className="w-[5px] h-[5px] rounded-full shrink-0" style={{ backgroundColor: color }} />}
        <span className="text-[10px] font-bold tracking-[0.07em] uppercase [font-family:var(--font-mono)]" style={{ color }}>
          {STATUS_LABEL[run.status]}
        </span>
      </div>
      <span className="text-[10px] [font-family:var(--font-mono)] text-[var(--text-secondary)] flex-1 min-w-0 overflow-hidden text-ellipsis whitespace-nowrap">
        job #{run.jobRunNum} · {defName} · {formatCamera(run.camera)}
      </span>
      {run.status === "failed" && run.error && <FailureReason text={run.error} maxWidth="160px" />}
      {imp?.status === "failed" && imp.errorMessage && <FailureReason text={imp.errorMessage} maxWidth="160px" />}
      {imp?.status === "loaded" && (
        <button
          type="button"
          onClick={onUnload}
          disabled={isUnloading}
          className="shrink-0 flex items-center py-[var(--space-2)] px-[var(--space-3)] [font-family:var(--font-mono)] text-[9px] font-bold uppercase tracking-[0.07em] whitespace-nowrap bg-[var(--bg-elevated)] text-[var(--accent-alert)]! border border-[var(--accent-alert)] cursor-pointer transition-colors hover:bg-[var(--accent-alert)] hover:text-[var(--bg-elevated)]! disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Unload in CVAT
        </button>
      )}
      <CvatActionButton action={resolvedAction} taskUrl={imp?.taskUrl ?? null} onLoad={onLoad} />
    </div>
  );
}

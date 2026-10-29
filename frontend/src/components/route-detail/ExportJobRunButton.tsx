import { useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listDatasetExportsForRoute,
  createDatasetExport,
  deleteDatasetExport,
  getDatasetExport,
  getDatasetExportDownloadUrl,
} from "../../api/dataset_exports";
import type { DatasetExport, DatasetExportStatus } from "../../api/dataset_exports";

const EXPORT_IN_PROGRESS: DatasetExportStatus[] = ["queued", "running"];

type ExportState = "unavailable" | "export" | "exporting" | "download" | "failed";

interface ResolvedState {
  state: ExportState;
  label: string;
  export: DatasetExport | null;
}

function resolveState(
  jobSucceeded: boolean,
  existing: DatasetExport | null,
  isPending: boolean,
): ResolvedState {
  if (isPending) return { state: "exporting", label: "Creating…", export: null };
  if (!jobSucceeded) return { state: "unavailable", label: "Export", export: null };
  if (!existing) return { state: "export", label: "Export", export: null };
  if (EXPORT_IN_PROGRESS.includes(existing.status)) {
    return { state: "exporting", label: "Exporting…", export: existing };
  }
  if (existing.status === "failed") {
    return { state: "failed", label: "Export Failed", export: existing };
  }
  return { state: "download", label: "Download ↓", export: existing };
}

interface Props {
  routeId: string;
  jobDefId: number;
  jobRunNum: number;
  camera: string;
  jobSucceeded: boolean;
  companionDepth?: { jobDefId: number; jobRunNum: number; camera: string };
}

export function ExportJobRunButton({ routeId, jobDefId, jobRunNum, camera, jobSucceeded, companionDepth }: Props) {
  if (!camera) return null;
  const queryClient = useQueryClient();
  const queryKey = ["dataset-exports", routeId];

  const { data: allExports = [] } = useQuery({
    queryKey,
    queryFn: () => listDatasetExportsForRoute(routeId),
    enabled: jobSucceeded,
    refetchInterval: (q) => {
      const exports = q.state.data ?? [];
      return exports.some((e) => EXPORT_IN_PROGRESS.includes(e.status)) ? 3000 : false;
    },
  });

  const existing = useMemo(
    () =>
      allExports.find((e) =>
        e.jobRuns.length === (companionDepth ? 2 : 1) && e.jobRuns.some(
          (jr) => jr.jobDefId === jobDefId && jr.jobRunNum === jobRunNum && jr.camera === camera,
        ) && (!companionDepth || e.jobRuns.some((jr) => jr.jobDefId === companionDepth.jobDefId && jr.jobRunNum === companionDepth.jobRunNum && jr.camera === companionDepth.camera)),
      ) ?? null,
    [allExports, jobDefId, jobRunNum, camera, companionDepth],
  );

  const createMutation = useMutation({
    mutationFn: () =>
      createDatasetExport({
        routeId,
        cameraViews: [camera],
        jobRuns: [{ jobDefId, jobRunNum, camera }, ...(companionDepth ? [companionDepth] : [])],
      }),
    onSuccess: (newExport) => {
      queryClient.setQueryData<DatasetExport[]>(queryKey, (old = []) => [...old, newExport]);
      queryClient.invalidateQueries({ queryKey });
    },
    meta: { errorTitle: "Could not start dataset export" },
  });

  const retryMutation = useMutation({
    mutationFn: async () => {
      if (existing) await deleteDatasetExport(existing.exportId);
      return createDatasetExport({
        routeId,
        cameraViews: [camera],
        jobRuns: [{ jobDefId, jobRunNum, camera }, ...(companionDepth ? [companionDepth] : [])],
      });
    },
    onSuccess: (newExport) => {
      queryClient.setQueryData<DatasetExport[]>(queryKey, (old = []) => [
        ...(old ?? []).filter((e) => e.exportId !== existing?.exportId),
        newExport,
      ]);
      queryClient.invalidateQueries({ queryKey });
    },
    meta: { errorTitle: "Could not retry dataset export" },
  });

  const isPending = createMutation.isPending || retryMutation.isPending;
  const { state, label, export: resolvedExport } = resolveState(jobSucceeded, existing, isPending);

  // Poll individual export while in-progress for tighter updates
  useQuery({
    queryKey: [...queryKey, resolvedExport?.exportId],
    queryFn: async () => {
      const updated = await getDatasetExport(resolvedExport!.exportId);
      queryClient.setQueryData<DatasetExport[]>(queryKey, (old = []) =>
        old.map((e) => (e.exportId === updated.exportId ? updated : e)),
      );
      return updated;
    },
    enabled: !!resolvedExport && EXPORT_IN_PROGRESS.includes(resolvedExport.status),
    refetchInterval: 3000,
  });

  const style = { ...BASE_STYLE, ...VARIANT[state] };

  if (state === "download" && resolvedExport) {
    return (
      <a
        href={getDatasetExportDownloadUrl(resolvedExport.exportId)}
        style={style}
        title="Download export zip"
      >
        {companionDepth ? "Download + depth ↓" : label}
      </a>
    );
  }

  const canClick = state === "export";
  const isRetry = state === "failed";

  return (
    <button
      type="button"
      disabled={!canClick && !isRetry}
      onClick={() => {
        if (canClick) createMutation.mutate();
        else if (isRetry) retryMutation.mutate();
      }}
      style={style}
      title={state === "unavailable" ? "Job run must succeed before exporting" : undefined}
    >
      {state === "exporting" && (
        <span
          style={{
            width: "5px",
            height: "5px",
            borderRadius: "50%",
            backgroundColor: "var(--accent-caution)",
            flexShrink: 0,
            display: "inline-block",
          }}
        />
      )}
      {companionDepth && state === "export" ? "Export + depth" : label}
    </button>
  );
}

const BASE_STYLE: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: "5px",
  padding: "2px 8px",
  fontFamily: "var(--font-mono)",
  fontSize: "9px",
  fontWeight: 700,
  letterSpacing: "0.07em",
  textTransform: "uppercase",
  whiteSpace: "nowrap",
  textDecoration: "none",
  border: "1px solid",
  cursor: "pointer",
};

const VARIANT: Record<ExportState, React.CSSProperties> = {
  unavailable: {
    backgroundColor: "transparent",
    borderColor: "var(--border-on-inverse-faint)",
    color: "var(--text-on-inverse-dim)",
    cursor: "not-allowed",
    opacity: 0.5,
  },
  export: {
    backgroundColor: "transparent",
    borderColor: "var(--border-on-inverse-strong)",
    color: "var(--text-on-inverse-secondary)",
  },
  exporting: {
    backgroundColor: "transparent",
    borderColor: "var(--accent-caution)",
    color: "var(--accent-caution)",
    cursor: "not-allowed",
    opacity: 0.8,
  },
  download: {
    backgroundColor: "var(--accent-go)",
    borderColor: "var(--accent-go)",
    color: "var(--bg-inverse)",
  },
  failed: {
    backgroundColor: "transparent",
    borderColor: "var(--accent-alert)",
    color: "var(--accent-alert)",
  },
};

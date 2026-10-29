import { useMutation, useQueryClient } from "@tanstack/react-query";
import { cancelJobRun, deleteJobRun } from "../../api/job_runs";
import type { JobStatus } from "../../api/types";
import { formatCamera } from "../../utils/formatters";

interface Props {
  routeId: string;
  jobDefId: number;
  jobRunNum: number;
  camera: string;
  status: JobStatus;
}

const BASE_CLASSES =
  "inline-flex items-center justify-center w-4 h-4 p-0 text-[10px] font-bold tracking-[0.07em] whitespace-nowrap border shrink-0 font-[family-name:var(--font-mono)] transition-colors";

const DEFAULT_CLASSES =
  "bg-transparent border-[var(--border-on-inverse-faint)] text-[var(--text-on-inverse-dim)] cursor-pointer hover:border-[var(--accent-alert)] hover:text-[var(--accent-alert)]";

const PENDING_CLASSES =
  "bg-transparent border-[var(--accent-alert)] text-[var(--accent-alert)] cursor-not-allowed opacity-80";

export function DeleteJobRunButton({ routeId, jobDefId, jobRunNum, camera, status }: Props) {
  const queryClient = useQueryClient();
  const isQueued = status === "queued";

  const mutation = useMutation({
    mutationFn: async () => {
      if (isQueued) {
        await cancelJobRun({ routeId, jobDefId, jobRunNum, camera });
      } else {
        await deleteJobRun({ routeId, jobDefId, jobRunNum, camera });
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobRuns", routeId] });
    },
    meta: { errorTitle: isQueued ? "Could not cancel job run" : "Could not delete job run" },
  });

  if (status === "running") return null;

  const action = isQueued ? "Cancel" : "Delete";
  const confirmMessage = isQueued
    ? `Cancel job run #${jobRunNum} (${formatCamera(camera)})?`
    : `Delete job run #${jobRunNum} (${formatCamera(camera)})? This cannot be undone.`;

  const handleClick = () => {
    if (!confirm(confirmMessage)) return;
    mutation.mutate();
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={mutation.isPending}
      title={`${action} job run`}
      className={`${BASE_CLASSES} ${mutation.isPending ? PENDING_CLASSES : DEFAULT_CLASSES}`}
    >
      {mutation.isPending ? "…" : "✕"}
    </button>
  );
}

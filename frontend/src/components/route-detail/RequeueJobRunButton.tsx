import { useMutation, useQueryClient } from "@tanstack/react-query";
import { requeueJobRun } from "../../api/job_runs";
import { formatCamera } from "../../utils/formatters";

interface Props {
  routeId: string;
  jobDefId: number;
  jobRunNum: number;
  camera: string;
}

const BASE_CLASSES =
  "inline-flex items-center gap-[5px] px-2 py-[2px] text-[9px] font-bold uppercase tracking-[0.07em] whitespace-nowrap border font-[family-name:var(--font-mono)] bg-[var(--accent-go)] border-[var(--accent-go)] text-[var(--bg-inverse)] transition-opacity";

const DEFAULT_CLASSES = "cursor-pointer hover:opacity-90";

const PENDING_CLASSES = "cursor-not-allowed opacity-70";

export function RequeueJobRunButton({ routeId, jobDefId, jobRunNum, camera }: Props) {
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => requeueJobRun({ routeId, jobDefId, jobRunNum, camera }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobRuns", routeId] });
    },
    meta: { errorTitle: "Could not retry job run" },
  });

  const handleClick = () => {
    if (!confirm(`Retry job run #${jobRunNum} (${formatCamera(camera)})?`)) return;
    mutation.mutate();
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={mutation.isPending}
      title="Requeue this cancelled job run"
      className={`${BASE_CLASSES} ${mutation.isPending ? PENDING_CLASSES : DEFAULT_CLASSES}`}
    >
      {mutation.isPending ? "Retrying…" : "Retry"}
    </button>
  );
}

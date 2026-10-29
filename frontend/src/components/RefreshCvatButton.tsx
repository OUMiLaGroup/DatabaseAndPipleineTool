import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { RotateCcw } from "lucide-react";
import { getCvatActiveStatus, restartCvat } from "../api/cvat";

const COOLDOWN_SECONDS = 60;
const ACTIVE_POLL_MS = 5000;
const TOOLTIP =
  "Restart the CVAT server. Only use this if CVAT is frozen or unresponsive";
const TOOLTIP_BUSY =
  "A job run or CVAT import is in progress. Wait for it to finish before restarting.";

export default function RefreshCvatButton() {
  const [cooldownLeft, setCooldownLeft] = useState(0);

  const { data: activeStatus } = useQuery({
    queryKey: ["cvat-active-status"],
    queryFn: getCvatActiveStatus,
    refetchInterval: ACTIVE_POLL_MS,
  });
  const isBusy = activeStatus?.active ?? false;

  const mutation = useMutation({
    mutationFn: restartCvat,
    onSuccess: () => setCooldownLeft(COOLDOWN_SECONDS),
    meta: { errorTitle: "Could not restart CVAT" },
  });

  useEffect(() => {
    if (cooldownLeft <= 0) return;
    const id = setInterval(() => setCooldownLeft((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(id);
  }, [cooldownLeft]);

  const isCoolingDown = cooldownLeft > 0;
  const isPending = mutation.isPending;
  const disabled = isPending || isCoolingDown || isBusy;

  const label = isPending
    ? "Restarting…"
    : isCoolingDown
    ? `Wait ${cooldownLeft}s`
    : isBusy
    ? "CVAT Busy"
    : "Refresh CVAT";

  const handleClick = () => {
    if (disabled) return;
    if (
      !confirm(
        "Restart the CVAT server?\n\n" +
          "This will end your active CVAT sessions\n" +
          "Only do this if CVAT is frozen.\n\n" +
          "After clicking OK, wait ~30 seconds, then refresh your CVAT browser tab to reconnect.",
      )
    )
      return;
    mutation.mutate();
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={disabled}
      title={
        mutation.isError
          ? `Restart failed: ${(mutation.error as Error).message}`
          : isBusy
          ? TOOLTIP_BUSY
          : TOOLTIP
      }
      className="flex items-center gap-2 px-3 py-1.5 text-sm rounded transition-colors border"
      style={{
        color: "var(--bg-inverse)",
        borderColor: "var(--text-on-inverse)",
        backgroundColor: "var(--text-on-inverse)",
        opacity: disabled ? 0.6 : 1,
        cursor: disabled ? "not-allowed" : "pointer",
        fontFamily: "var(--font-mono)",
        letterSpacing: "0.05em",
      }}
    >
      <RotateCcw size={14} className={isPending ? "animate-spin" : undefined} />
      {label}
    </button>
  );
}

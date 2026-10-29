import { useQuery } from "@tanstack/react-query";
import type { JobRun } from "../../api/types";
import { formatCamera, formatRelativeTime } from "../../utils/formatters";
import { listJobDefinitions } from "../../api/job_definitions";
import { listJobRunsForRoute } from "../../api/job_runs";
import { STATUS_COLOR, STATUS_LABEL } from "../../utils/jobSegmentRunConfig";
import { ExportJobRunButton } from "./ExportJobRunButton";
import { DeleteJobRunButton } from "./DeleteJobRunButton";
import { RequeueJobRunButton } from "./RequeueJobRunButton";
import { FailureReason } from "../FailureReason";

export function JobRunRow({ jobRun }: { jobRun: JobRun }) {
  const color = STATUS_COLOR[jobRun.status as keyof typeof STATUS_COLOR] ?? "var(--text-secondary)";
  const label = STATUS_LABEL[jobRun.status as keyof typeof STATUS_LABEL] ?? jobRun.status;
  const isActive = jobRun.status === "queued" || jobRun.status === "running";

  const { data: jobDefs = [] } = useQuery({
    queryKey: ["job-definitions"],
    queryFn: listJobDefinitions,
  });
  const defName = jobDefs.find((d) => d.id === jobRun.jobDefId)?.name ?? `def ${jobRun.jobDefId}`;
  const { data: routeRuns = [] } = useQuery({
    queryKey: ["depth-companions", jobRun.routeId],
    queryFn: () => listJobRunsForRoute(jobRun.routeId),
    refetchInterval: 5000,
  });
  const depthRun = routeRuns.filter((run) => run.status === "succeeded" && run.camera === jobRun.camera &&
    jobDefs.find((definition) => definition.id === run.jobDefId)?.type === "depth")
    .sort((a, b) => (b.finishedAt ?? "").localeCompare(a.finishedAt ?? ""))[0];
  const supportsDepth = jobDefs.find((definition) => definition.id === jobRun.jobDefId)?.type === "object_detection";

  return (
    <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "var(--space-3)", padding: "calc(var(--space-2) + 1px) var(--space-3)", backgroundColor: "var(--bg-on-inverse-subtle)", border: "1px solid var(--border-on-inverse-faint)" }}>
      <DeleteJobRunButton
        routeId={jobRun.routeId}
        jobDefId={jobRun.jobDefId}
        jobRunNum={jobRun.jobRunNum}
        camera={jobRun.camera}
        status={jobRun.status}
      />
      <div style={{ display: "flex", alignItems: "center", gap: "6px", minWidth: "100px" }}>
        {isActive && <span style={{ width: "5px", height: "5px", borderRadius: "50%", backgroundColor: color, flexShrink: 0 }} />}
        <span style={{ fontSize: "10px", fontWeight: 700, color, letterSpacing: "0.07em", textTransform: "uppercase", fontFamily: "var(--font-mono)" }}>
          {label}
        </span>
      </div>
      <span style={{ fontSize: "10px", fontFamily: "var(--font-mono)", color: "var(--text-on-inverse-muted)" }}>
        job #{jobRun.jobRunNum} · {defName} · {formatCamera(jobRun.camera)}
      </span>
      <span style={{ fontSize: "10px", fontFamily: "var(--font-mono)", color: "var(--text-on-inverse-dim)", marginLeft: "auto" }}>
        {isActive ? `queued ${formatRelativeTime(jobRun.queuedAt)}` : formatRelativeTime(jobRun.finishedAt)}
      </span>
      {jobRun.error && (
        // A succeeded run can still carry a warning, e.g. "2 of 10 segments failed"
        <FailureReason text={jobRun.error} tone={jobRun.status === "failed" ? "alert" : "warning"} dark maxWidth="220px" />
      )}
      {jobRun.status === "cancelled" && (
        <RequeueJobRunButton
          routeId={jobRun.routeId}
          jobDefId={jobRun.jobDefId}
          jobRunNum={jobRun.jobRunNum}
          camera={jobRun.camera}
        />
      )}
      <ExportJobRunButton
        routeId={jobRun.routeId}
        jobDefId={jobRun.jobDefId}
        jobRunNum={jobRun.jobRunNum}
        camera={jobRun.camera}
        jobSucceeded={jobRun.status === "succeeded"}
      />
      {supportsDepth && depthRun && jobRun.status === "succeeded" && <ExportJobRunButton
        routeId={jobRun.routeId} jobDefId={jobRun.jobDefId} jobRunNum={jobRun.jobRunNum}
        camera={jobRun.camera} jobSucceeded={true}
        companionDepth={{ jobDefId: depthRun.jobDefId, jobRunNum: depthRun.jobRunNum, camera: depthRun.camera }}
      />}
    </div>
  );
}

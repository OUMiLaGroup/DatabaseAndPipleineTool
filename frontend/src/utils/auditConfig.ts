import type { AuditOutcome } from "../api/audit_logs";

/** Readable names for audit actions; unknown actions are shown as-is. */
export const AUDIT_ACTION_LABELS: Record<string, string> = {
  "route.import": "Import route",
  "route.delete": "Delete route",
  "route.download.finished": "Route download finished",
  "route.download.interrupted": "Route download interrupted",
  "route.upload.finished": "Route upload finished",
  "segment.download.finished": "Segment download",
  "segment.upload.finished": "Segment upload",
  "segment.upload.interrupted": "Segment upload interrupted",
  "job_definition.create": "Create job definition",
  "job_definition.delete": "Delete job definition",
  "job_run.create": "Queue job run",
  "job_run.cancel": "Cancel job run",
  "job_run.requeue": "Retry job run",
  "job_run.delete": "Delete job run",
  "job_run.finished": "Job run finished",
  "job_run.interrupted": "Job run interrupted",
  "cvat.load_segment": "Load segment into CVAT",
  "cvat.load_segment.finished": "CVAT load finished",
  "cvat.remove_segment": "Remove segment from CVAT",
  "cvat.remove_segment.finished": "CVAT removal finished",
  "cvat.import.interrupted": "CVAT import interrupted",
  "cvat.restart": "Restart CVAT",
  "dataset_export.create": "Start dataset export",
  "dataset_export.delete": "Delete dataset export",
  "dataset_export.finished": "Dataset export finished",
  "dataset_export.interrupted": "Dataset export interrupted",
};

export const AUDIT_OUTCOME_STYLE: Record<AuditOutcome, { label: string; color: string }> = {
  success: { label: "Success", color: "var(--accent-go)" },
  warning: { label: "Warning", color: "var(--accent-caution)" },
  failure: { label: "Failed", color: "var(--accent-alert)" },
};

export const AUDIT_SOURCES = [
  "api",
  "open_pilot_download_worker",
  "open_pilot_upload_worker",
  "cvat_worker",
  "cvat_import_export_worker",
  "dataset_export_worker",
];

export const AUDIT_ACTION_GROUPS: { value: string; label: string }[] = [
  { value: "route", label: "Routes" },
  { value: "segment", label: "Segments" },
  { value: "job_run", label: "Job runs" },
  { value: "job_definition", label: "Job definitions" },
  { value: "cvat", label: "CVAT" },
  { value: "dataset_export", label: "Dataset exports" },
];

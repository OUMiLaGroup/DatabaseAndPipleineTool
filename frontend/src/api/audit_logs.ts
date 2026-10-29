import { apiFetch } from "./client";

// ─── Audit log ────────────────────────────────────────────────────────────────
// Every change made through the API (including failed attempts) and the outcome of
// every worker job is recorded by the backend. See backend/api/audit.py.

export type AuditOutcome = "success" | "warning" | "failure";

interface AuditLogResponse {
  id: number;
  created_at: string;
  source: string;
  action: string;
  outcome: AuditOutcome;
  entity_type: string | null;
  entity_id: string | null;
  route_id: string | null;
  message: string | null;
  error_code: string | null;
  request_id: string | null;
  details: Record<string, unknown> | null;
}

export interface AuditLogEntry {
  id: number;
  createdAt: string;
  source: string;
  action: string;
  outcome: AuditOutcome;
  entityType: string | null;
  entityId: string | null;
  routeId: string | null;
  message: string | null;
  errorCode: string | null;
  requestId: string | null;
  details: Record<string, unknown> | null;
}

export interface AuditLogFilters {
  routeId?: string;
  outcome?: AuditOutcome;
  source?: string;
  /** Action prefix, e.g. "job_run" or "route.import" */
  action?: string;
  beforeId?: number;
  limit?: number;
}

function mapAuditLog(r: AuditLogResponse): AuditLogEntry {
  return {
    id: r.id,
    createdAt: r.created_at,
    source: r.source,
    action: r.action,
    outcome: r.outcome,
    entityType: r.entity_type,
    entityId: r.entity_id,
    routeId: r.route_id,
    message: r.message,
    errorCode: r.error_code,
    requestId: r.request_id,
    details: r.details,
  };
}

export async function listAuditLogs(filters: AuditLogFilters = {}): Promise<AuditLogEntry[]> {
  const params = new URLSearchParams();
  if (filters.routeId) params.set("route_id", filters.routeId);
  if (filters.outcome) params.set("outcome", filters.outcome);
  if (filters.source) params.set("source", filters.source);
  if (filters.action) params.set("action", filters.action);
  if (filters.beforeId !== undefined) params.set("before_id", String(filters.beforeId));
  params.set("limit", String(filters.limit ?? 100));
  const raw = await apiFetch<AuditLogResponse[]>(`/audit-logs/?${params.toString()}`);
  return raw.map(mapAuditLog);
}

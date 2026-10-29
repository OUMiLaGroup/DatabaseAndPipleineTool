// ─── API Base Client ──────────────────────────────────────────────────────────
// Reads VITE_API_URL at build time; falls back to same-origin for local dev.

export const API_BASE = ((import.meta.env as Record<string, string>).VITE_API_URL ?? "").replace(/\/$/, "");

/**
 * Shape of every error body returned by the backend (see backend/main.py and
 * shared/services/errors.py). All fields are optional so older/foreign responses
 * still parse.
 */
interface ApiErrorBody {
  detail?: unknown;
  code?: string;
  hint?: string | null;
  context?: Record<string, unknown>;
  request_id?: string;
}

interface ApiErrorOptions {
  code?: string;
  hint?: string | null;
  requestId?: string | null;
  context?: Record<string, unknown>;
}

export class ApiError extends Error {
  status: number;
  /** Stable machine-readable error code, e.g. "ROUTE_NOT_READY". */
  code: string;
  /** Short suggestion on how to fix the problem, when the backend provides one. */
  hint: string | null;
  /** Request ID to search for in the backend logs. */
  requestId: string | null;
  context: Record<string, unknown>;

  constructor(status: number, message: string, opts: ApiErrorOptions = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = opts.code ?? fallbackCode(status);
    this.hint = opts.hint ?? fallbackHint(status);
    this.requestId = opts.requestId ?? null;
    this.context = opts.context ?? {};
  }
}

function fallbackCode(status: number): string {
  if (status === 0) return "NETWORK_ERROR";
  if (status === 404) return "NOT_FOUND";
  if (status === 409) return "CONFLICT";
  if (status === 422) return "VALIDATION_ERROR";
  if (status >= 500) return "SERVER_ERROR";
  return "REQUEST_FAILED";
}

function fallbackHint(status: number): string | null {
  if (status === 0)
    return "Make sure the backend is running (docker compose up -d backend) and open http://localhost:8000/health-check to check it responds.";
  if (status === 502 || status === 503 || status === 504)
    return "The backend or a service it depends on (Postgres, MinIO, CVAT) is not responding. Check `docker compose ps` and the backend logs.";
  if (status >= 500) return "Check the backend logs: docker compose logs backend";
  return null;
}

/** FastAPI's `detail` can be a string, or a list of validation problems. */
function detailToMessage(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = detail.map((d) => {
      if (d && typeof d === "object" && "msg" in d) {
        const loc = Array.isArray((d as { loc?: unknown[] }).loc)
          ? (d as { loc: unknown[] }).loc.filter((p) => p !== "body").join(".")
          : "";
        return loc ? `${loc}: ${(d as { msg: string }).msg}` : (d as { msg: string }).msg;
      }
      return String(d);
    });
    return parts.join("; ");
  }
  return null;
}

async function toApiError(res: Response): Promise<ApiError> {
  const raw = await res.text().catch(() => "");
  let body: ApiErrorBody | null = null;
  try {
    body = raw ? (JSON.parse(raw) as ApiErrorBody) : null;
  } catch {
    body = null; // not JSON (e.g. a proxy error page)
  }
  const message =
    detailToMessage(body?.detail) ??
    (raw && raw.length < 300 ? raw : null) ??
    `${res.status} ${res.statusText || "Request failed"}`;

  return new ApiError(res.status, message, {
    code: body?.code,
    hint: body?.hint,
    requestId: body?.request_id ?? res.headers.get("X-Request-ID"),
    context: body?.context,
  });
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json", ...init?.headers },
      ...init,
    });
  } catch (err) {
    // Request cancelled by React Query / the caller: not an error to report
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    // fetch only throws for network-level failures: backend down, CORS, DNS...
    throw new ApiError(0, `Could not reach the backend at ${API_BASE || window.location.origin}.`);
  }
  if (!res.ok) {
    throw await toApiError(res);
  }
  if (res.status === 204 || res.headers.get("content-length") === "0") {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

/** Normalised view of any thrown value, for displaying in the UI. */
export interface ErrorInfo {
  message: string;
  hint: string | null;
  code: string | null;
  requestId: string | null;
}

export function toErrorInfo(err: unknown, fallbackMessage = "Something went wrong."): ErrorInfo {
  if (err instanceof ApiError) {
    return { message: err.message, hint: err.hint, code: err.code, requestId: err.requestId };
  }
  if (err instanceof Error) {
    return { message: err.message || fallbackMessage, hint: null, code: null, requestId: null };
  }
  return { message: typeof err === "string" ? err : fallbackMessage, hint: null, code: null, requestId: null };
}

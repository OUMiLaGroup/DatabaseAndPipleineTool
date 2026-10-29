// ─── Global error reporting ───────────────────────────────────────────────────
// Any code can call reportError(err, "Could not ...") to show an error toast
// (rendered by components/ErrorToaster.tsx).
// Failed React Query mutations are reported automatically (see App.tsx) unless
// they set `meta: { inlineError: true }` because they show the error themselves.

export interface ErrorToast {
  id: number;
  error: unknown;
  title?: string;
}

const AUTO_DISMISS_MS = 12_000;
const MAX_TOASTS = 4;

let toasts: ErrorToast[] = [];
let nextId = 1;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((l) => l());
}

export function dismissError(id: number) {
  toasts = toasts.filter((t) => t.id !== id);
  emit();
}

export function reportError(error: unknown, title?: string) {
  const id = nextId++;
  toasts = [...toasts, { id, error, title }].slice(-MAX_TOASTS);
  emit();
  setTimeout(() => dismissError(id), AUTO_DISMISS_MS);
}

export function subscribeToErrors(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getErrorToasts(): ErrorToast[] {
  return toasts;
}

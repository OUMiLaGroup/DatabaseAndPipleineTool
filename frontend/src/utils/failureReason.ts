// The workers store why something failed in an `error` column, formatted as
//   "<what went wrong> | How to fix: <hint>"
// (see shared/utilities/error_utilities.py).

const HINT_SEPARATOR = " | How to fix: ";

export function splitFailureReason(text: string): { message: string; hint: string | null } {
  const idx = text.indexOf(HINT_SEPARATOR);
  if (idx === -1) return { message: text, hint: null };
  return { message: text.slice(0, idx), hint: text.slice(idx + HINT_SEPARATOR.length) };
}

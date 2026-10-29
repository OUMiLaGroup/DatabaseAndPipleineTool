// Typed `meta` for React Query mutations, used by the global error toaster.
//   errorTitle  - title shown on the error toast, e.g. "Could not delete job run"
//   inlineError - true if the component shows the error itself (no toast)
import "@tanstack/react-query";

declare module "@tanstack/react-query" {
  interface Register {
    mutationMeta: {
      errorTitle?: string;
      inlineError?: boolean;
    };
  }
}

export {};

import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { MutationCache, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import "./api/queryMeta";
import { reportError } from "./utils/errorReporter";
import "./App.css";

import AppLayout from "./layouts/AppLayout";
import RouteDashboard from "./pages/RouteDashboard";
import RouteDetail from "./pages/RouteDetail";
import SegmentViewer from "./pages/SegmentViewer";
import JobDefinitions from "./pages/JobDefinitions";
import Activity from "./pages/Activity";

const queryClient = new QueryClient({
  // Show a toast for every failed mutation unless the component displays it inline
  mutationCache: new MutationCache({
    onError: (error, _vars, _ctx, mutation) => {
      if (mutation.meta?.inlineError) return;
      reportError(error, mutation.meta?.errorTitle ?? "Action failed");
    },
  }),
  defaultOptions: {
    queries: {
      // Prevent redundant window-focus refetches on top of scheduled polls
      staleTime: 2000,
    },
  },
})

export default function App() {
  return (
    <BrowserRouter>
    <QueryClientProvider client={queryClient}>
      <Routes>
        {/* Redirect / → /routes */}
        <Route path="/" element={<Navigate to="/routes" replace />} />

        {/* All pages share the AppLayout (topbar + content wrapper) */}
        <Route element={<AppLayout />}>
          <Route path="/routes" element={<RouteDashboard />} />
          <Route path="/routes/:routeId" element={<RouteDetail />} />
          <Route path="/routes/:routeId/segments/:segmentId" element={<SegmentViewer />} />
          <Route path="/job-definitions" element={<JobDefinitions />} />
          <Route path="/activity" element={<Activity />} />
        </Route>
      </Routes>
      </QueryClientProvider>
    </BrowserRouter>
  );
}

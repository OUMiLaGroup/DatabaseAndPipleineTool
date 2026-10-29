import { Outlet } from "react-router-dom";
import TopBar from "../components/TopBar";
import ErrorToaster from "../components/ErrorToaster";

// Total offset = racing stripe (3px) + topbar (48px)
const TOP_OFFSET = "calc(3px + var(--topbar-height))";

export default function AppLayout() {
  return (
    <div style={{ backgroundColor: "var(--bg-primary)", minHeight: "100vh" }}>
      <TopBar />

      {/* Page content scrolls independently below the fixed topbar */}
      <main
        style={{
          paddingTop: TOP_OFFSET,
          maxWidth: "var(--content-max-w)",
          margin: "0 auto",
          padding: `${TOP_OFFSET} var(--space-8) var(--space-8)`,
        }}
      >
        <Outlet />
      </main>
      <ErrorToaster />
    </div>
  );
}

import { NavLink } from "react-router-dom";
import { Route, BriefcaseBusiness, History } from "lucide-react";
import RefreshCvatButton from "./RefreshCvatButton";
import milaLogo from "../assets/mila_logo.png";

const navItems = [
  { to: "/routes", label: "Routes", icon: Route },
  { to: "/job-definitions", label: "Jobs", icon: BriefcaseBusiness },
  { to: "/activity", label: "Activity", icon: History },
];

export default function TopBar() {
  return (
    <header
      className="fixed left-0 right-0 flex items-center px-6 gap-8 z-50"
      style={{
        top: "3px", // sits just below the racing stripe
        height: "var(--topbar-height)",
        backgroundColor: "var(--bg-inverse)",
        borderBottom: "1px solid var(--border-black)",
      }}
    >
      {/* MiLa logo */}
      <img
        src={milaLogo}
        alt="Mobility Intelligence Lab"
        className="select-none"
        style={{ height: "var(--topbar-height)", width: "auto", display: "block" }}
      />
      
      {/* Nav links */}
      <nav className="flex items-center gap-1">
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className="flex items-center gap-2 px-3 py-1.5 text-sm rounded transition-colors border no-underline"
            style={({ isActive }) => ({
              color: isActive ? "var(--bg-inverse)" : "var(--text-on-inverse)",
              backgroundColor: isActive ? "var(--text-on-inverse)" : "transparent",
              borderColor: isActive ? "var(--text-on-inverse)" : "var(--border-on-inverse-faint)",
              opacity: isActive ? 1 : 0.85,
              fontFamily: "var(--font-mono)",
              letterSpacing: "0.05em",
            })}
          >
            <Icon size={14} />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Right-side actions */}
      <div className="ml-auto flex items-center">
        <RefreshCvatButton />
      </div>
    </header>
  );
}

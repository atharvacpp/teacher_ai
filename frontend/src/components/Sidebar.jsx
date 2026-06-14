/**
 * Sidebar.jsx — Collapsible navigation sidebar for Teacher AI.
 *
 * Props:
 *   isOpen       (boolean)  — whether the sidebar is expanded
 *   onToggle     (function) — toggle expanded/collapsed
 *   activeTab    (string)   — currently active workspace tab
 *   onTabChange  (function) — switch to a different tab
 *   theme        (string)   — "vs-dark" | "vs-light"
 *   onToggleTheme (function) — toggle light/dark theme
 */

const NAV_ITEMS = [
  {
    id: "teacher",
    label: "Teacher AI",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
        <path d="m19 8-7 7-7-7" />
      </svg>
    ),
    emoji: "✨",
  },
  {
    id: "code",
    label: "Code Assistant",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="16 18 22 12 16 6" />
        <polyline points="8 6 2 12 8 18" />
      </svg>
    ),
    emoji: "💻",
  },
  {
    id: "lesson",
    label: "Generate Lesson",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
        <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
      </svg>
    ),
    emoji: "🎓",
  },
];

export default function Sidebar({ isOpen, onToggle, activeTab, onTabChange, theme, onToggleTheme }) {
  return (
    <aside className={`sidebar ${isOpen ? "sidebar--open" : "sidebar--collapsed"}`}>
      {/* ── Toggle Button ── */}
      <button
        className="sidebar-toggle"
        onClick={onToggle}
        title={isOpen ? "Collapse sidebar" : "Expand sidebar"}
        aria-label={isOpen ? "Collapse sidebar" : "Expand sidebar"}
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          {isOpen ? (
            <>
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </>
          ) : (
            <>
              <line x1="3" y1="6" x2="21" y2="6" />
              <line x1="3" y1="12" x2="21" y2="12" />
              <line x1="3" y1="18" x2="21" y2="18" />
            </>
          )}
        </svg>
      </button>

      {/* ── Brand ── */}
      <div className="sidebar-brand">
        <div className="sidebar-brand__icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
            <path d="m19 8-7 7-7-7" />
          </svg>
          <span className="sidebar-brand__sparkle">✨</span>
        </div>
        {isOpen && (
          <div className="sidebar-brand__text">
            <span className="sidebar-brand__title">Teacher AI</span>
            <span className="sidebar-brand__subtitle">AI Coding Tutor</span>
          </div>
        )}
      </div>

      {/* ── Navigation ── */}
      <nav className="sidebar-nav">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.id}
            className={`sidebar-nav-btn ${activeTab === item.id ? "sidebar-nav-btn--active" : ""}`}
            onClick={() => onTabChange(item.id)}
            title={item.label}
            aria-label={item.label}
          >
            <span className="sidebar-nav-btn__icon">{item.icon}</span>
            {isOpen && <span className="sidebar-nav-btn__label">{item.label}</span>}
            {activeTab === item.id && <span className="sidebar-nav-btn__indicator" />}
          </button>
        ))}
      </nav>

      {/* ── Spacer ── */}
      <div className="sidebar-spacer" />

      {/* ── Theme Toggle at Bottom ── */}
      <div className="sidebar-bottom">
        <button
          className="sidebar-nav-btn sidebar-theme-btn"
          onClick={onToggleTheme}
          title="Toggle Theme"
          aria-label="Toggle Theme"
        >
          <span className="sidebar-nav-btn__icon">
            {theme === "vs-dark" ? (
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
              </svg>
            ) : (
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="5" />
                <line x1="12" y1="1" x2="12" y2="3" />
                <line x1="12" y1="21" x2="12" y2="23" />
                <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
                <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
                <line x1="1" y1="12" x2="3" y2="12" />
                <line x1="21" y1="12" x2="23" y2="12" />
                <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
                <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
              </svg>
            )}
          </span>
          {isOpen && <span className="sidebar-nav-btn__label">{theme === "vs-dark" ? "Dark Mode" : "Light Mode"}</span>}
        </button>
      </div>
    </aside>
  );
}

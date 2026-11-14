import { useEffect, useRef, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { api, User } from "../api";
import suseLogo from "../assets/suse-logo.svg";
import { Icon } from "../Icon";
import { useLanguage } from "../i18n";

type Theme = "light" | "dark";

// Same key the poc-planner iframe (embedded on "/", see PlanPoc.tsx) reads on its own
// load. A `storage` event never fires in the window that made the change, so toggling
// here can't rely on it to refresh the already-open iframe -- dispatch a same-window
// custom event instead, which PlanPoc.tsx listens for to reload the iframe.
const THEME_KEY = "suse_poc_planner_theme";
const THEME_EVENT = "poc-control:theme-changed";

function readStoredTheme(): Theme {
  try {
    const stored = localStorage.getItem(THEME_KEY);
    if (stored === "light" || stored === "dark") return stored;
  } catch {
    // localStorage indisponível (modo privado etc.) -- cai no fallback de sistema
  }
  try {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  } catch {
    return "light";
  }
}

function formatBuildInfo(lang: string): string {
  const locale = lang === "pt" ? "pt-BR" : lang === "es" ? "es-ES" : "en-US";
  const formatada = new Intl.DateTimeFormat(locale, { dateStyle: "short", timeStyle: "short" }).format(
    new Date(__APP_BUILD_TIME__),
  );
  return `v${__APP_VERSION__} · ${formatada}`;
}

export function Layout({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [theme, setTheme] = useState<Theme>(readStoredTheme);
  const [accountOpen, setAccountOpen] = useState(false);
  const location = useLocation();
  const { lang, setLang, t } = useLanguage();
  const mounted = useRef(false);
  const accountRef = useRef<HTMLDivElement>(null);

  // Only the planner's own iframe page needs the no-padding, fixed-height treatment (and skips
  // the Gemini-key banner, which wouldn't make sense floating over an iframe that has its own
  // full-page UI) -- "/" is the real Home page now, a normal page like any other.
  const isPlanejador = location.pathname === "/plan";
  // Home's hub (hero + action tiles + 3 history cards side by side) reads cramped at the normal
  // .page width now that the sidebar is gone -- give it more of the screen (page-wide, ~66vw)
  // instead of widening .page globally for every other screen.
  const isHome = location.pathname === "/";

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {
      // localStorage indisponível -- a preferência só não persiste entre sessões
    }
    if (mounted.current) window.dispatchEvent(new Event(THEME_EVENT));
    mounted.current = true;
  }, [theme]);

  useEffect(() => {
    if (!accountOpen) return;
    function onClickOutside(e: MouseEvent) {
      if (accountRef.current && !accountRef.current.contains(e.target as Node)) setAccountOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [accountOpen]);

  async function handleLogout() {
    await api.logout();
    onLogout();
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <Link to="/" className="topbar-brand">
          <img src={suseLogo} alt="" className="navbar-logo" />
          {t("brand")}
        </Link>
        <Link to="/" className="theme-toggle" title={t("nav.dashboard")} aria-label={t("nav.dashboard")}>
          <Icon name="home" />
        </Link>
        <button
          className="theme-toggle"
          onClick={() => setTheme((cur) => (cur === "dark" ? "light" : "dark"))}
          aria-label={theme === "dark" ? t("theme.toLight") : t("theme.toDark")}
          title={theme === "dark" ? t("theme.toLight") : t("theme.toDark")}
        >
          {theme === "dark" ? (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
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
          ) : (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
            </svg>
          )}
        </button>
        <div className="lang-switch">
          <button className={lang === "pt" ? "lang-btn active" : "lang-btn"} onClick={() => setLang("pt")}>
            PT
          </button>
          <button className={lang === "en" ? "lang-btn active" : "lang-btn"} onClick={() => setLang("en")}>
            EN
          </button>
          <button className={lang === "es" ? "lang-btn active" : "lang-btn"} onClick={() => setLang("es")}>
            ES
          </button>
        </div>
        <div className="account-menu" ref={accountRef}>
          <button className="account-toggle" onClick={() => setAccountOpen((o) => !o)}>
            {user.email}
          </button>
          {accountOpen && (
            <div className="account-dropdown">
              <Link to="/my-account" onClick={() => setAccountOpen(false)}>
                {t("nav.minhaConta")}
              </Link>
              {user.is_admin && (
                <Link to="/users" onClick={() => setAccountOpen(false)}>
                  {t("nav.usuarios")}
                </Link>
              )}
              <button className="btn btn-secondary" onClick={handleLogout}>
                {t("action.sair")}
              </button>
            </div>
          )}
        </div>
      </header>

      <div className="app-body">
        <main className={isPlanejador ? "page page-flush" : isHome ? "page page-wide" : "page"}>
          {!isPlanejador && !user.tem_gemini_key && (
            <p className="alert alert-warning" style={{ marginBottom: 20 }}>
              {t("layout.chaveCompartilhadaAntes")} <Link to="/my-account">{t("nav.minhaConta")}</Link>{" "}
              {t("layout.chaveCompartilhadaDepois")}
            </p>
          )}
          <Outlet />
        </main>
      </div>

      <span className="build-info" title={__APP_BUILD_TIME__}>
        {formatBuildInfo(lang)}
      </span>
    </div>
  );
}

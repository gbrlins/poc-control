import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useLanguage } from "@/i18n";

const THEME_EVENT = "poc-control:theme-changed";

// The planner is a single self-contained file maintained in the sibling top-level
// `poc-planner/` project (its own history, its own tests, no build step). poc-control
// never forks or ports its logic: the web image copies `poc-planner/index.html` verbatim
// at build time (see `web/Dockerfile`) and nginx serves it at `/planner/` (see
// `nginx.conf`). This page just embeds that same-origin page in an iframe, which is what
// lets the planner's optional connector work (`GET /api/planner/capabilities` — see
// `api/app/planner/`) and keeps the session cookie usable for it.
//
// Home (the hub) is now the only entry point: it owns "Novo projeto", "Importar projeto",
// "Importar documento do cliente", the procedure library and the project list. The planner's own
// dashboard is no longer shown when embedded. Home tells the planner where to land through
// one-time query params that this page forwards to the iframe on its FIRST load only (the planner
// strips them from its own URL after applying them): ?open=<local project id>, ?new=1,
// ?import=project|doc, ?view=library. Forwarding them on later loads (a language change rebuilds
// the iframe src) would e.g. create a second "new" project, hence the `consumed` ref. With no
// params it resumes the project that was open. The planner asks to go back to Home through a
// `poc-control:navigate` postMessage (it has no router).
//
// Language: the planner reads a one-time `?lang=` query param (its own i18n takes over
// after that), so the iframe `src` is rebuilt whenever the shell's language changes.
// Theme: the planner only reads `suse_poc_planner_theme` from localStorage on load, so
// toggling the shell's theme (Layout.tsx) reloads the iframe to re-apply it — see
// THEME_EVENT there. The planner persists all of its state to localStorage continuously,
// so reloading it loses nothing in progress.
export function PlanPoc() {
  const { lang } = useLanguage();
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [acao] = useState(() => {
    const q = new URLSearchParams();
    for (const k of ["open", "new", "import", "view", "readonly", "enable"]) {
      const v = params.get(k);
      if (v) q.set(k, v);
    }
    const texto = q.toString();
    return texto ? `&${texto}` : "";
  });
  const consumida = useRef(false);

  useEffect(() => {
    const aoReceber = (e: MessageEvent) => {
      if (e.origin !== window.location.origin || e.source !== iframeRef.current?.contentWindow) return;
      if (e.data?.type === "poc-control:navigate" && typeof e.data.to === "string" && e.data.to.startsWith("/")) {
        navigate(e.data.to);
      }
    };
    window.addEventListener("message", aoReceber);
    return () => window.removeEventListener("message", aoReceber);
  }, [navigate]);

  useEffect(() => {
    const reloadForTheme = () => iframeRef.current?.contentWindow?.location.reload();
    window.addEventListener(THEME_EVENT, reloadForTheme);
    return () => window.removeEventListener(THEME_EVENT, reloadForTheme);
  }, []);

  return (
    // height: 100% here matters: the parent <main class="page-flush"> sets an explicit
    // height (calc(100vh - 56px)), but this div has none of its own, so without it the
    // iframe's height: 100% resolves against nothing and collapses to the browser's
    // default ~150px intrinsic iframe height instead of filling the page.
    <div id="planner-root" style={{ height: "100%" }}>
      <iframe
        ref={iframeRef}
        title="SUSE PoC Planner"
        src={`/planner/?lang=${lang}${consumida.current ? "" : acao}`}
        onLoad={() => {
          consumida.current = true;
        }}
        style={{ width: "100%", height: "100%", border: "none" }}
      />
    </div>
  );
}

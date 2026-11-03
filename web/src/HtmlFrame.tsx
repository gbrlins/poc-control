import { useEffect, useRef } from "react";

// Same event Layout.tsx dispatches on every theme toggle (poc-planner's own iframe listens for
// it too, to reload itself) -- duplicated as a literal here rather than imported, matching how
// PlanPoc.tsx already does it, since there's no shared constants module between the two.
const THEME_EVENT = "poc-control:theme-changed";

// Hardcoded hex, not var(--color-surface) etc.: srcDoc makes this a genuinely separate HTML
// document with its own CSSOM, so the parent page's CSS custom properties never reach it, even
// same-origin. These match the app's own dark theme values (styles.css's dark --surface/--gray-900/
// --ink) so the frame still looks consistent, they just can't be referenced live.
const DARK_CSS = "body{background:#15241f !important;color:#f3faf7 !important;} a{color:#7eecb0 !important;}";
const STYLE_ID = "poc-control-tema-escuro";

function aplicarTema(iframe: HTMLIFrameElement) {
  const doc = iframe.contentDocument;
  if (!doc) return;
  const escuro = document.documentElement.getAttribute("data-theme") === "dark";
  const existente = doc.getElementById(STYLE_ID);
  if (!escuro) {
    existente?.remove();
    return;
  }
  if (!existente) {
    const style = doc.createElement("style");
    style.id = STYLE_ID;
    style.textContent = DARK_CSS;
    doc.head?.appendChild(style);
  }
}

// Procedimento.html (hand-uploaded, or auto-synthesized from a PoC item/RFI answer -- see
// api/app/pocs/router.py::validar_anexo and api/app/rfi/router.py::_html_da_resposta_rfi; resolved
// server-side to the site's current language, possibly auto-translated -- see
// api/app/procedimentos/router.py::_html_no_idioma) has no styling of its own, so it always
// rendered as a stark white page via srcDoc, regardless of the app's theme. Applied via the DOM
// (not string-spliced into the srcDoc text) so it works whether it's a bare fragment or a full
// <html> document.
export function HtmlFrame({ html, title, className }: { html: string; title: string; className?: string }) {
  const ref = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    const iframe = ref.current;
    if (!iframe) return;
    const aplicar = () => aplicarTema(iframe);
    iframe.addEventListener("load", aplicar);
    window.addEventListener(THEME_EVENT, aplicar);
    aplicar();
    return () => {
      iframe.removeEventListener("load", aplicar);
      window.removeEventListener(THEME_EVENT, aplicar);
    };
  }, [html]);

  return <iframe ref={ref} title={title} sandbox="allow-same-origin" srcDoc={html} className={className} />;
}

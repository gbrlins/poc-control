import { OrigemConhecimento, ProcedimentoDetail } from "@/api";
import { rotuloCategoria } from "@/categorias";
import { HtmlFrame } from "@/HtmlFrame";
import { useLanguage } from "@/i18n";

// Small tag showing where a knowledge entry came from -- used by both Procedimentos.tsx (list
// row) and ProcedimentoView.tsx (detail header). Colors mirror Home's tile coding (PoC = blue,
// RFI = suse-accent); manual uploads use the plain neutral .chip with no modifier.
export function OrigemChip({ origem }: { origem: OrigemConhecimento }) {
  const { t } = useLanguage();
  const labelKey = { manual: "procedimentos.origemManual", poc: "procedimentos.origemPoc", rfi: "procedimentos.origemRfi" }[
    origem
  ];
  return <span className={`chip chip-origem-${origem}`}>{t(labelKey)}</span>;
}

// Shared between ProcedimentoView.tsx (the full-page /procedimentos/:id route -- kept for deep
// links, e.g. RFI's "Ver procedimento interno") and Procedimentos.tsx's inline-expand row, so the
// actual content rendering (info line, indexed sections, original HTML) has one source of truth.
export function ProcedimentoConteudo({ procedimento }: { procedimento: ProcedimentoDetail }) {
  const { t, lang } = useLanguage();

  return (
    <>
      <div className="card">
        <p>
          <strong>{t("procedimentoView.cliente")}</strong> {procedimento.cliente_origem ?? "—"} &nbsp;·&nbsp;{" "}
          <strong>{t("procedimentoView.versao")}</strong> {procedimento.versao}
        </p>
        <p>
          <strong>{t("procedimentoView.tags")}</strong> {procedimento.tags.join(", ") || "—"}
        </p>
        <p>
          <strong>{t("procedimentoView.categorias")}</strong>{" "}
          {procedimento.categorias.length > 0
            ? procedimento.categorias.map((c) => (
                <span key={c} className="chip" style={{ marginRight: 6 }}>
                  {c} — {rotuloCategoria(c, lang)}
                </span>
              ))
            : "—"}
        </p>
      </div>

      <div className="card">
        <h2>{t("procedimentoView.secoesIndexadas")}</h2>
        <ul className="secoes-list">
          {procedimento.secoes.map((s, i) => (
            <li key={i} className={s.heading_level === 3 ? "sub" : undefined}>
              {s.heading_title}
            </li>
          ))}
        </ul>
      </div>

      <div className="card">
        <div className="page-header" style={{ marginBottom: 8 }}>
          <h2 style={{ margin: 0 }}>{t("procedimentoView.conteudo")}</h2>
          <button type="button" className="btn btn-secondary" onClick={() => baixarHtml(procedimento)}>
            {t("procedimentoView.baixarHtml")}
          </button>
        </div>
        {procedimento.idioma_conteudo && procedimento.idioma_conteudo !== lang && (
          <p className="alert alert-error">{t("procedimentoView.falhaTraducao")}</p>
        )}
        {procedimento.idioma_conteudo === lang &&
          procedimento.idioma_original &&
          procedimento.idioma_original !== lang && (
            <p className="field-hint">
              {t("procedimentoView.traduzidoAutomaticamente")} ({procedimento.idioma_original})
            </p>
          )}
        <HtmlFrame html={procedimento.html} title={procedimento.titulo} className="html-frame" />
      </div>
    </>
  );
}

function baixarHtml(procedimento: ProcedimentoDetail) {
  const nome = procedimento.titulo.trim().replace(/[^\w\-]+/g, "_").replace(/^_+|_+$/g, "") || "procedimento";
  const blob = new Blob([procedimento.html], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${nome}.html`;
  a.click();
  URL.revokeObjectURL(url);
}

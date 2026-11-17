import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/api";
import { CODIGOS_CATEGORIA, rotuloCategoria } from "@/categorias";
import { useLanguage } from "@/i18n";
import { toggleInSet } from "@/toggleInSet";

export function ProcedimentoUpload() {
  const { t, lang } = useLanguage();
  const navigate = useNavigate();
  const [titulo, setTitulo] = useState("");
  const [tags, setTags] = useState("");
  const [categorias, setCategorias] = useState<Set<string>>(new Set());
  const [clienteOrigem, setClienteOrigem] = useState("");
  const [status, setStatus] = useState("rascunho");
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [progresso, setProgresso] = useState(0);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!arquivo) {
      setErro(t("procedimentoUpload.erroArquivo"));
      return;
    }
    setErro(null);
    setEnviando(true);
    setProgresso(0);
    try {
      const form = new FormData();
      form.append("titulo", titulo);
      form.append("tags", tags);
      form.append("categorias", [...categorias].join(","));
      form.append("cliente_origem", clienteOrigem);
      form.append("status", status);
      form.append("arquivo", arquivo);
      const criado = await api.criarProcedimentoComProgresso(form, setProgresso);
      navigate(`/procedures/${criado.id}`);
    } catch {
      setErro(t("procedimentoUpload.erroSalvar"));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1>{t("procedimentoUpload.titulo")}</h1>
      </div>

      <div className="card" style={{ marginBottom: 20 }}>
        <strong>{t("procedimentos.formatoRecomendadoTitulo")}</strong>
        <p className="field-hint">{t("procedimentos.formatoRecomendado")}</p>
        <a href="/exemplo-procedimento.html" download className="btn btn-secondary">
          {t("procedimentos.baixarModelo")}
        </a>
      </div>

      <div className="card">
        <form onSubmit={handleSubmit} className="form">
          <div className="field">
            <label htmlFor="titulo">{t("procedimentoUpload.labelTitulo")}</label>
            <input
              id="titulo"
              className="input"
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="tags">{t("procedimentoUpload.labelTags")}</label>
            <input
              id="tags"
              className="input"
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder={t("procedimentoUpload.tagsPlaceholder")}
            />
            <p className="field-hint">{t("procedimentoUpload.tagsHint")}</p>
          </div>
          <div className="field">
            <label>{t("procedimentoUpload.labelCategorias")}</label>
            <div className="chip-filter-group">
              {CODIGOS_CATEGORIA.map((codigo) => (
                <button
                  key={codigo}
                  type="button"
                  className={`chip-filter${categorias.has(codigo) ? " active" : ""}`}
                  onClick={() => setCategorias((atual) => toggleInSet(atual, codigo))}
                >
                  {codigo} — {rotuloCategoria(codigo, lang)}
                </button>
              ))}
            </div>
            <p className="field-hint">{t("procedimentoUpload.categoriasHint")}</p>
          </div>
          <div className="field">
            <label htmlFor="cliente">{t("procedimentoUpload.labelClienteOrigem")}</label>
            <input
              id="cliente"
              className="input"
              value={clienteOrigem}
              onChange={(e) => setClienteOrigem(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="status">{t("procedimentoUpload.labelStatus")}</label>
            <select
              id="status"
              className="input"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="rascunho">{t("procedimentoUpload.statusRascunho")}</option>
              <option value="validado">{t("procedimentoUpload.statusValidado")}</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="arquivo">{t("procedimentoUpload.labelArquivo")}</label>
            <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
              <label className="btn btn-outline" style={{ cursor: "pointer" }}>
                {t("common.escolherArquivo")}
                <input
                  id="arquivo"
                  type="file"
                  accept=".html,text/html"
                  hidden
                  onChange={(e) => setArquivo(e.target.files?.[0] ?? null)}
                />
              </label>
              <span className="muted">{arquivo?.name ?? t("common.nenhumArquivo")}</span>
            </div>
          </div>
          {erro && <p className="alert alert-error">{erro}</p>}
          {enviando && (
            <div style={{ margin: "4px 0 12px" }}>
              <div style={{ height: 8, borderRadius: 99, background: "var(--gray-100)", overflow: "hidden" }}>
                <div
                  style={{
                    height: "100%",
                    width: `${progresso}%`,
                    background: "var(--suse-base)",
                    transition: "width 150ms",
                  }}
                />
              </div>
              <p className="field-hint" style={{ marginTop: 4 }}>
                {t("procedimentoUpload.enviando")} {progresso}%
              </p>
            </div>
          )}
          <button type="submit" className="btn btn-primary" disabled={enviando || !arquivo}>
            {enviando ? t("procedimentoUpload.enviando") : t("procedimentoUpload.salvar")}
          </button>
        </form>
      </div>
    </div>
  );
}

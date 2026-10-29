import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/api";
import { CODIGOS_CATEGORIA, rotuloCategoria } from "@/categorias";
import { useLanguage } from "@/i18n";

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

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!arquivo) {
      setErro(t("procedimentoUpload.erroArquivo"));
      return;
    }
    setErro(null);
    setEnviando(true);
    try {
      const form = new FormData();
      form.append("titulo", titulo);
      form.append("tags", tags);
      form.append("categorias", [...categorias].join(","));
      form.append("cliente_origem", clienteOrigem);
      form.append("status", status);
      form.append("arquivo", arquivo);
      const criado = await api.criarProcedimento(form);
      navigate(`/procedimentos/${criado.id}`);
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
                  onClick={() =>
                    setCategorias((atual) => {
                      const novo = new Set(atual);
                      if (novo.has(codigo)) novo.delete(codigo);
                      else novo.add(codigo);
                      return novo;
                    })
                  }
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
            <input
              id="arquivo"
              type="file"
              accept=".html,text/html"
              onChange={(e) => setArquivo(e.target.files?.[0] ?? null)}
              required
            />
          </div>
          {erro && <p className="alert alert-error">{erro}</p>}
          <button type="submit" className="btn btn-primary" disabled={enviando}>
            {enviando ? t("procedimentoUpload.enviando") : t("procedimentoUpload.salvar")}
          </button>
        </form>
      </div>
    </div>
  );
}

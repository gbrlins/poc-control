import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/api";
import { BatchDocumentUploader } from "@/components/BatchDocumentUploader";
import { useLanguage } from "@/i18n";

type Modo = "arquivo" | "texto";

export function PocUpload() {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const [titulo, setTitulo] = useState("");
  const [cliente, setCliente] = useState("");
  const [escopo, setEscopo] = useState("");
  const [modo, setModo] = useState<Modo>("arquivo");
  const [arquivos, setArquivos] = useState<File[]>([]);
  const [texto, setTexto] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (modo === "arquivo" && arquivos.length === 0) {
      setErro(t("pocUpload.erroSelecione"));
      return;
    }
    if (modo === "texto" && !texto.trim()) {
      setErro(t("pocUpload.erroCole"));
      return;
    }
    setErro(null);
    setEnviando(true);
    try {
      const form = new FormData();
      form.append("titulo", titulo);
      form.append("cliente", cliente);
      form.append("escopo", escopo);
      if (modo === "arquivo") arquivos.forEach((a) => form.append("arquivos", a));
      if (modo === "texto") form.append("texto", texto);
      const criado = await api.criarPoc(form);
      navigate(`/pocs/${criado.id}`);
    } catch {
      setErro(t("pocUpload.erroCriar"));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1>{t("pocUpload.titulo")}</h1>
      </div>

      <div className="card">
        <form onSubmit={handleSubmit} className="form">
          <div className="field">
            <label htmlFor="titulo">{t("pocUpload.labelTitulo")}</label>
            <input
              id="titulo"
              className="input"
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
              placeholder="PoC SUSE Virtualization"
              required
            />
          </div>
          <div className="field">
            <label htmlFor="cliente">{t("pocUpload.labelCliente")}</label>
            <input
              id="cliente"
              className="input"
              value={cliente}
              onChange={(e) => setCliente(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="escopo">{t("pocUpload.labelEscopo")}</label>
            <input
              id="escopo"
              className="input"
              value={escopo}
              onChange={(e) => setEscopo(e.target.value)}
              placeholder={t("pocUpload.escopoPlaceholder")}
            />
          </div>

          <div className="field">
            <label>{t("pocUpload.planoDeTestes")}</label>
            <div className="field-toggle">
              <button
                type="button"
                className={modo === "arquivo" ? "field-toggle-btn active" : "field-toggle-btn"}
                onClick={() => setModo("arquivo")}
              >
                {t("pocUpload.arquivo")}
              </button>
              <button
                type="button"
                className={modo === "texto" ? "field-toggle-btn active" : "field-toggle-btn"}
                onClick={() => setModo("texto")}
              >
                {t("pocUpload.colarTexto")}
              </button>
            </div>

            {modo === "arquivo" ? (
              <>
                <BatchDocumentUploader
                  files={arquivos}
                  onFilesChange={setArquivos}
                  accept=".pdf,.json,.txt,.md,.xlsx,.csv,application/pdf,application/json,text/plain,text/markdown,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                  selectLabel={t("pocUpload.adicionarMais")}
                  removeLabel={t("pocUpload.remover")}
                />
                <p className="field-hint">
                  {t("pocUpload.hintArquivo1")}
                  <strong>{t("pocUpload.hintArquivoPath")}</strong>
                  {t("pocUpload.hintArquivo2")}
                </p>
              </>
            ) : (
              <>
                <textarea
                  id="texto"
                  className="input"
                  rows={10}
                  value={texto}
                  onChange={(e) => setTexto(e.target.value)}
                  placeholder={t("pocUpload.textoPlaceholder")}
                />
                <p className="field-hint">
                  {t("pocUpload.hintTexto1")}
                  <strong>{t("pocUpload.hintTextoPath")}</strong>
                  {t("pocUpload.hintTexto2")}
                </p>
              </>
            )}
          </div>

          {erro && <p className="alert alert-error">{erro}</p>}
          <button type="submit" className="btn btn-primary" disabled={enviando}>
            {enviando ? t("pocUpload.enviando") : t("pocUpload.criarPoc")}
          </button>
        </form>
      </div>
    </div>
  );
}

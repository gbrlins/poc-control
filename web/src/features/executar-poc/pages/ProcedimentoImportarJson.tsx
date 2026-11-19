import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError, PreviaItemImportacao, ResultadoImportacaoItem } from "@/api";
import { useLanguage } from "@/i18n";

type Decisao = "importar" | "pular" | "sobrescrever";

export function ProcedimentoImportarJson() {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const [texto, setTexto] = useState("");
  const [nomeArquivo, setNomeArquivo] = useState<string | null>(null);
  const [itens, setItens] = useState<unknown[] | null>(null);
  const [previa, setPrevia] = useState<PreviaItemImportacao[] | null>(null);
  const [decisoes, setDecisoes] = useState<Record<number, Decisao>>({});
  const [resultado, setResultado] = useState<ResultadoImportacaoItem[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);

  function parseEItens(): unknown[] | null {
    try {
      const parsed = JSON.parse(texto);
      // A biblioteca exportada pelo planejador ("Export library") traz os procedimentos em `procedures`; o servidor converte os campos.
      if (parsed && !Array.isArray(parsed) && parsed.kind === "suse-poc-procedure-library" && Array.isArray(parsed.procedures)) {
        return parsed.procedures;
      }
      return Array.isArray(parsed) ? parsed : [parsed];
    } catch {
      setErro(t("procedimentoImportarJson.erroJsonInvalido"));
      return null;
    }
  }

  async function validar() {
    setErro(null);
    setResultado(null);
    const lista = parseEItens();
    if (!lista) return;
    setCarregando(true);
    try {
      const p = await api.previewImportarProcedimentosJson(lista);
      setItens(lista);
      setPrevia(p);
      const iniciais: Record<number, Decisao> = {};
      p.forEach((item) => {
        iniciais[item.indice] = item.duplicado_id ? "pular" : "importar";
      });
      setDecisoes(iniciais);
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : t("procedimentoImportarJson.erroValidar"));
    } finally {
      setCarregando(false);
    }
  }

  async function importar() {
    if (!itens || !previa) return;
    setErro(null);
    setCarregando(true);
    try {
      const validos = previa.filter((p) => p.valido && decisoes[p.indice] !== "pular");
      const sobrescreverIds = previa
        .filter((p) => p.valido && decisoes[p.indice] === "sobrescrever" && p.duplicado_id)
        .map((p) => p.duplicado_id as string);
      const itensParaEnviar = validos.map((p) => itens[p.indice]);
      const r = await api.importarProcedimentosJson(itensParaEnviar, sobrescreverIds);
      setResultado(r);
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : t("procedimentoImportarJson.erroImportar"));
    } finally {
      setCarregando(false);
    }
  }

  // O arquivo escolhido vai para a caixa de texto: assim dá para conferir e ajustar o JSON antes de validar, e colar continua valendo.
  async function lerArquivo(arquivo: File | null) {
    if (!arquivo) return;
    try {
      setTexto(await arquivo.text());
      setNomeArquivo(arquivo.name);
      setErro(null);
    } catch {
      setErro(t("procedimentoImportarJson.erroLerArquivo"));
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1>{t("procedimentoImportarJson.titulo")}</h1>
      </div>

      <div className="card" style={{ marginBottom: 20 }}>
        <p className="field-hint">{t("procedimentoImportarJson.hint")}</p>
      </div>

      {!previa && (
        <div className="card">
          <div className="field">
            <label htmlFor="json-arquivo">{t("procedimentoImportarJson.labelArquivo")}</label>
            <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
              <label className="btn btn-outline" style={{ cursor: "pointer" }}>
                {t("common.escolherArquivo")}
                <input
                  id="json-arquivo"
                  type="file"
                  accept=".json,application/json"
                  hidden
                  onChange={(e) => void lerArquivo(e.target.files?.[0] ?? null)}
                />
              </label>
              <span className="muted">{nomeArquivo ?? t("common.nenhumArquivo")}</span>
            </div>
          </div>
          <div className="field">
            <label htmlFor="json-texto">{t("procedimentoImportarJson.labelTexto")}</label>
            <textarea
              id="json-texto"
              className="input"
              rows={14}
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              placeholder='[{"titulo": "...", "html_original": "<h2>...</h2>", "status": "rascunho"}]'
            />
          </div>
          {erro && <p className="alert alert-error">{erro}</p>}
          <button type="button" className="btn btn-primary" onClick={() => void validar()} disabled={carregando || !texto.trim()}>
            {carregando ? t("procedimentoImportarJson.validando") : t("procedimentoImportarJson.validar")}
          </button>
        </div>
      )}

      {previa && !resultado && (
        <div className="card">
          <h2>{t("procedimentoImportarJson.previaTitulo")}</h2>
          <ul style={{ margin: "0 0 16px", paddingLeft: 0, listStyle: "none" }}>
            {previa.map((item) => (
              <li key={item.indice} style={{ padding: "8px 0", borderTop: "1px solid var(--gray-100)" }}>
                <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                  <strong>{item.titulo || `#${item.indice + 1}`}</strong>
                  {!item.valido && <span className="pill pill-warn">{t("procedimentoImportarJson.invalido")}</span>}
                  {item.valido && item.duplicado_id && (
                    <span className="pill pill-warn">
                      {t("procedimentoImportarJson.duplicadoDe")} {item.duplicado_titulo}
                    </span>
                  )}
                  {item.valido && item.duplicado_id && (
                    <select
                      className="t-compact"
                      value={decisoes[item.indice] ?? "pular"}
                      onChange={(e) =>
                        setDecisoes((atual) => ({ ...atual, [item.indice]: e.target.value as Decisao }))
                      }
                    >
                      <option value="pular">{t("procedimentoImportarJson.pular")}</option>
                      <option value="sobrescrever">{t("procedimentoImportarJson.sobrescrever")}</option>
                    </select>
                  )}
                </div>
                {!item.valido && (
                  <ul className="text-xs" style={{ color: "var(--red-600, #dc2626)", margin: "4px 0 0 18px" }}>
                    {item.erros.map((e, i) => (
                      <li key={i}>{e}</li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
          {erro && <p className="alert alert-error">{erro}</p>}
          <div style={{ display: "flex", gap: 8 }}>
            <button type="button" className="btn btn-secondary" onClick={() => { setPrevia(null); setItens(null); }}>
              {t("common.voltar")}
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => void importar()}
              disabled={carregando || !previa.some((p) => p.valido && decisoes[p.indice] !== "pular")}
            >
              {carregando ? t("procedimentoImportarJson.importando") : t("procedimentoImportarJson.importar")}
            </button>
          </div>
        </div>
      )}

      {resultado && (
        <div className="card">
          <h2>{t("procedimentoImportarJson.resultadoTitulo")}</h2>
          <ul style={{ margin: "0 0 16px", paddingLeft: 0, listStyle: "none" }}>
            {resultado.map((item) => (
              <li key={item.indice} style={{ padding: "6px 0", borderTop: "1px solid var(--gray-100)" }}>
                <strong>{item.titulo || `#${item.indice + 1}`}</strong>{" "}
                <span
                  className={`pill ${
                    item.status === "erro" ? "pill-warn" : item.status === "pulado" ? "pill-off" : "pill-ok"
                  }`}
                >
                  {t(`procedimentoImportarJson.status.${item.status}`)}
                </span>
                {item.erro && <span className="text-xs" style={{ marginLeft: 8 }}>{item.erro}</span>}
              </li>
            ))}
          </ul>
          <button type="button" className="btn btn-primary" onClick={() => navigate("/procedures")}>
            {t("procedimentoImportarJson.verProcedimentos")}
          </button>
        </div>
      )}
    </div>
  );
}

import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "@/api";
import { BatchDocumentUploader } from "@/components/BatchDocumentUploader";
import { ProgressoEnvio } from "@/components/ProgressoEnvio";
import { useAvisoAoSair, useRascunhoState } from "@/rascunhoUpload";
import { useLanguage } from "@/i18n";

type Modo = "arquivo" | "texto";

export function RfiUpload() {
  const { t } = useLanguage();
  const navigate = useNavigate();
  // O que já foi escolhido fica na memória ao sair da tela e voltar; os arquivos só sobem quando se clica em "Criar RFI".
  const [rascunho, setRascunho, limparRascunho] = useRascunhoState<{
    titulo: string;
    orgao: string;
    modo: Modo;
    arquivos: File[];
    texto: string;
  }>("rfi-novo", { titulo: "", orgao: "", modo: "arquivo", arquivos: [], texto: "" });
  const { titulo, orgao, modo, arquivos, texto } = rascunho;
  const atualizar = (parcial: Partial<typeof rascunho>) => setRascunho({ ...rascunho, ...parcial });
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [progresso, setProgresso] = useState(0);
  useAvisoAoSair(modo === "arquivo" && arquivos.length > 0 && !enviando);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (modo === "arquivo" && arquivos.length === 0) {
      setErro(t("rfiUpload.erroSelecione"));
      return;
    }
    if (modo === "texto" && !texto.trim()) {
      setErro(t("rfiUpload.erroCole"));
      return;
    }
    setErro(null);
    setProgresso(0);
    setEnviando(true);
    try {
      const form = new FormData();
      form.append("titulo", titulo);
      form.append("orgao", orgao);
      if (modo === "arquivo") arquivos.forEach((a) => form.append("arquivos", a));
      if (modo === "texto") form.append("texto", texto);
      const criado = await api.criarRfi(form, setProgresso);
      limparRascunho();
      navigate(`/rfis/${criado.id}`);
    } catch (e) {
      // Com o motivo que o servidor deu (já traduzido para o idioma da tela), ex.: arquivo vazio ou formato que não conseguimos ler.
      setErro(e instanceof ApiError && e.message ? `${t("rfiUpload.erroCriar")}: ${e.message}` : t("rfiUpload.erroCriar"));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1>{t("rfiUpload.titulo")}</h1>
      </div>

      <div className="card">
        <form onSubmit={handleSubmit} className="form">
          <div className="field">
            <label htmlFor="titulo">{t("rfiUpload.labelTitulo")}</label>
            <input
              id="titulo"
              className="input"
              value={titulo}
              onChange={(e) => atualizar({ titulo: e.target.value })}
              placeholder={t("rfiUpload.tituloPlaceholder")}
            />
          </div>
          <div className="field">
            <label htmlFor="orgao">{t("rfiUpload.labelOrgao")}</label>
            <input id="orgao" className="input" value={orgao} onChange={(e) => atualizar({ orgao: e.target.value })} />
          </div>
          <p className="field-hint">{t("rfiUpload.hintOpcional")}</p>

          <div className="field">
            <label>{t("rfiUpload.documento")}</label>
            <div className="field-toggle">
              <button
                type="button"
                className={modo === "arquivo" ? "field-toggle-btn active" : "field-toggle-btn"}
                onClick={() => atualizar({ modo: "arquivo" })}
              >
                {t("rfiUpload.arquivo")}
              </button>
              <button
                type="button"
                className={modo === "texto" ? "field-toggle-btn active" : "field-toggle-btn"}
                onClick={() => atualizar({ modo: "texto" })}
              >
                {t("rfiUpload.colarTexto")}
              </button>
            </div>

            {modo === "arquivo" ? (
              <>
                <BatchDocumentUploader
                  files={arquivos}
                  onFilesChange={(arquivos) => atualizar({ arquivos })}
                  accept=".pdf,.docx,.xlsx,.csv,.txt,.md,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv,text/plain,text/markdown"
                  selectLabel={t("rfiUpload.adicionarMais")}
                  removeLabel={t("rfiUpload.remover")}
                  pendingHint={t("common.arquivosNaoEnviados")}
                />
                <p className="field-hint">{t("rfiUpload.hintArquivo")}</p>
              </>
            ) : (
              <>
                <textarea
                  id="texto"
                  className="input"
                  rows={10}
                  value={texto}
                  onChange={(e) => atualizar({ texto: e.target.value })}
                  placeholder={t("rfiUpload.textoPlaceholder")}
                />
                <p className="field-hint">{t("rfiUpload.hintTexto")}</p>
              </>
            )}
          </div>

          {erro && <p className="alert alert-error">{erro}</p>}
          {enviando && modo === "arquivo" && <ProgressoEnvio pct={progresso} />}
          <button type="submit" className="btn btn-primary" disabled={enviando}>
            {enviando ? t("rfiUpload.enviando") : t("rfiUpload.criarRfi")}
          </button>
        </form>
      </div>
    </div>
  );
}

import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, RfiDetail as RfiDetailData, RfiDocumentoOut, RfiItemOut, VeredictoRfi } from "@/api";
import { rotuloCategoria } from "@/categorias";
import { BatchDocumentUploader } from "@/components/BatchDocumentUploader";
import { DangerZone } from "@/components/DangerZone";
import { ProcessamentoEmLote } from "@/components/ProcessamentoEmLote";
import { useLanguage } from "@/i18n";
import { formatElapsed, useElapsedSeconds } from "@/useElapsedSeconds";

const VEREDITO_BADGE: Record<VeredictoRfi, string> = {
  atende: "badge-verde",
  atende_parcial: "badge-amarelo",
  nao_atende: "badge-vermelho",
  sem_evidencia: "badge-muted",
};

export function RfiDetail() {
  const { id } = useParams();
  const { t, lang } = useLanguage();
  const navigate = useNavigate();
  const [rfi, setRfi] = useState<RfiDetailData | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  function carregar() {
    if (!id) return;
    api
      .obterRfi(id)
      .then((data) => {
        setRfi(data);
        const aindaProcessando = data.status_extracao === "extraindo" || data.itens.some((i) => i.veredito === null);
        if (aindaProcessando) {
          pollRef.current = window.setTimeout(carregar, 3000);
        }
      })
      .catch(() => setErro(t("rfiDetail.erroCarregar")));
  }

  useEffect(() => {
    carregar();
    return () => {
      if (pollRef.current) window.clearTimeout(pollRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  function atualizarItem(atualizado: RfiItemOut) {
    setRfi((prev) =>
      prev ? { ...prev, itens: prev.itens.map((i) => (i.id === atualizado.id ? atualizado : i)) } : prev,
    );
  }

  const elapsedSeconds = useElapsedSeconds(
    rfi && rfi.status_extracao === "extraindo" ? (rfi.processamento_iniciado_em ?? rfi.created_at) : undefined,
  );

  if (erro) return <p className="alert alert-error">{erro}</p>;
  if (!rfi) return <p className="muted">{t("common.carregando")}</p>;

  const grupos: { categoria: string; itens: RfiItemOut[] }[] = [];
  for (const item of rfi.itens) {
    const categoria = item.categoria || t("rfiDetail.semCategoria");
    const ultimo = grupos[grupos.length - 1];
    if (ultimo && ultimo.categoria === categoria) ultimo.itens.push(item);
    else grupos.push({ categoria, itens: [item] });
  }

  const extraindo = rfi.status_extracao === "extraindo";
  const pct = rfi.total_itens > 0 ? Math.round((rfi.itens_avaliados / rfi.total_itens) * 100) : 0;

  return (
    <div>
      <div className="poc-header">
        <div className="poc-header-top">
          <div>
            <h1>{rfi.titulo || t("rfis.semTitulo")}</h1>
            <div className="poc-sub">
              {rfi.orgao}
              {rfi.numero_processo ? ` · ${t("rfiDetail.processo")} ${rfi.numero_processo}` : ""}
            </div>
          </div>
          <div className="poc-pct">
            <b>{pct}%</b>
            <span>
              {rfi.itens_avaliados}/{rfi.total_itens} {t("rfiDetail.avaliados")}
            </span>
          </div>
        </div>
      </div>

      {rfi.status_extracao === "erro" && <p className="alert alert-error">{rfi.erro_extracao}</p>}
      {rfi.status_extracao === "pronto" && rfi.erro_extracao && (
        <p className="alert alert-warning" style={{ whiteSpace: "pre-line" }}>
          {t("rfiDetail.avisoExtracao")}
          {"\n"}
          {rfi.erro_extracao}
        </p>
      )}
      {extraindo && (
        <ProcessamentoEmLote
          mensagemProcessando={t("rfiDetail.processando").replace("{tempo}", formatElapsed(elapsedSeconds))}
          statusLinha={
            rfi.cancelamento_solicitado
              ? t("rfiDetail.cancelando")
              : rfi.progresso
                ? t(`rfiDetail.fase.${rfi.progresso.fase}`)
                    .replace("{atual}", String(rfi.progresso.atual))
                    .replace("{total}", String(rfi.progresso.total))
                    .replace("{nome}", rfi.progresso.nome)
                : t("rfiDetail.iniciando")
          }
          cancelamentoSolicitado={rfi.cancelamento_solicitado}
          rotuloCancelar={t("rfiDetail.cancelar")}
          onCancelar={() => void api.cancelarRfi(rfi.id).then(carregar)}
        />
      )}

      {rfi.status_extracao === "pronto" && rfi.total_itens > 0 && (
        <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
          <a href={api.urlExportarRfi(rfi.id)} target="_blank" rel="noreferrer" className="btn btn-secondary">
            {t("rfiDetail.exportarHtml")}
          </a>
          <a href={api.urlExportarRfiXlsx(rfi.id)} download className="btn btn-secondary">
            {t("rfiDetail.exportarXlsx")}
          </a>
        </div>
      )}

      <RfiDocumentos rfi={rfi} bloqueado={extraindo} onMudou={carregar} />

      {rfi.status_extracao === "pronto" && rfi.total_itens === 0 && (
        <div className="card empty-state">{t("rfiDetail.nenhumItem")}</div>
      )}

      {grupos.map((grupo) => (
        <div key={grupo.categoria}>
          <div className="fase-header">
            <h3>{grupo.categoria}</h3>
          </div>
          <div className="card" style={{ padding: 0 }}>
            {grupo.itens.map((item) => (
              <RfiItemRow key={item.id} rfiId={rfi.id} item={item} onAtualizado={atualizarItem} />
            ))}
          </div>
        </div>
      ))}

      <DangerZone
        tipo="rfis"
        id={rfi.id}
        responsavelId={rfi.responsavel_id}
        responsavelEmail={rfi.responsavel_email}
        onResponsavelAtualizado={(responsavelId, responsavelEmail) =>
          setRfi({ ...rfi, responsavel_id: responsavelId, responsavel_email: responsavelEmail })
        }
        onExcluido={() => navigate("/rfis")}
      />
    </div>
  );
}

function RfiDocumentos({
  rfi,
  bloqueado,
  onMudou,
}: {
  rfi: RfiDetailData;
  bloqueado: boolean;
  onMudou: () => void;
}) {
  const { t } = useLanguage();
  const [enviando, setEnviando] = useState(false);
  const ocupado = enviando || bloqueado; // enquanto o RFI processa, a API recusa mudanças (409)
  const [erro, setErro] = useState<string | null>(null);
  const [incluirManuais, setIncluirManuais] = useState(false);
  // Arquivos escolhidos mas ainda não enviados: dá pra juntar vários (em várias seleções) e só
  // então disparar a extração, em vez de subir no instante em que o primeiro lote é escolhido.
  const [pendentes, setPendentes] = useState<File[]>([]);

  async function executar(acao: () => Promise<unknown>) {
    setEnviando(true);
    setErro(null);
    try {
      await acao();
      onMudou();
    } catch {
      setErro(t("rfiDetail.erroDocumentos"));
    } finally {
      setEnviando(false);
    }
  }

  function enviar() {
    const form = new FormData();
    pendentes.forEach((a) => form.append("arquivos", a));
    void executar(async () => {
      await api.adicionarDocumentosRfi(rfi.id, form);
      setPendentes([]);
    });
  }

  function remover(doc: RfiDocumentoOut) {
    let msg = t("rfiDetail.confirmarRemover").replace("{nome}", doc.nome_arquivo).replace("{n}", String(doc.total_itens));
    if (doc.itens_manuais > 0) msg += t("rfiDetail.confirmarRemoverManuais").replace("{m}", String(doc.itens_manuais));
    if (!window.confirm(msg)) return;
    void executar(() => api.removerDocumentoRfi(rfi.id, doc.id));
  }

  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <h3 style={{ marginTop: 0 }}>{t("rfiDetail.documentos")}</h3>
      <ul style={{ margin: "0 0 12px", paddingLeft: 0, listStyle: "none" }}>
        {rfi.documentos.map((doc) => (
          <li key={doc.id} style={{ display: "flex", gap: 12, alignItems: "center", padding: "4px 0" }}>
            <span style={{ flex: 1 }}>{doc.nome_arquivo}</span>
            <span className="muted">{t("rfiDetail.itensDoDocumento").replace("{n}", String(doc.total_itens))}</span>
            <button type="button" className="btn btn-secondary" disabled={ocupado} onClick={() => remover(doc)}>
              {t("rfiDetail.removerDocumento")}
            </button>
          </li>
        ))}
      </ul>
      <BatchDocumentUploader
        files={pendentes}
        onFilesChange={setPendentes}
        accept=".pdf,.docx,.xlsx,.csv,.txt,.md"
        disabled={ocupado}
        selectLabel={t("rfiDetail.selecionarArquivos")}
        removeLabel={t("rfiDetail.removerDocumento")}
        newBadgeLabel={t("rfiDetail.novo")}
      />
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", marginTop: 12 }}>
        {pendentes.length > 0 && (
          <button type="button" className="btn btn-primary" disabled={ocupado} onClick={enviar}>
            {enviando
              ? t("rfiDetail.adicionando")
              : t("rfiDetail.enviarPendentes").replace("{n}", String(pendentes.length))}
          </button>
        )}
        <button
          type="button"
          className="btn btn-secondary"
          disabled={ocupado || rfi.total_itens === 0}
          onClick={() => void executar(() => api.reavaliarRfi(rfi.id, incluirManuais))}
        >
          {t("rfiDetail.reavaliarTudo")}
        </button>
        {rfi.total_itens > rfi.itens_avaliados && (
          <button
            type="button"
            className="btn btn-secondary"
            disabled={ocupado}
            onClick={() => void executar(() => api.reavaliarRfi(rfi.id, false, true))}
          >
            {t("rfiDetail.avaliarPendentes").replace("{n}", String(rfi.total_itens - rfi.itens_avaliados))}
          </button>
        )}
        <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <input type="checkbox" checked={incluirManuais} onChange={(e) => setIncluirManuais(e.target.checked)} />
          {t("rfiDetail.reavaliarIncluirManuais")}
        </label>
      </div>
      {erro && <p className="alert alert-error">{erro}</p>}
    </div>
  );
}

function RfiItemRow({
  rfiId,
  item,
  onAtualizado,
}: {
  rfiId: string;
  item: RfiItemOut;
  onAtualizado: (item: RfiItemOut) => void;
}) {
  const { t, lang } = useLanguage();
  const [open, setOpen] = useState(false);
  const [editando, setEditando] = useState(false);
  const [veredito, setVeredito] = useState<VeredictoRfi>(item.veredito ?? "sem_evidencia");
  const [justificativa, setJustificativa] = useState(item.justificativa ?? "");
  const [salvando, setSalvando] = useState(false);
  const [reavaliando, setReavaliando] = useState(false);
  const [promovendo, setPromovendo] = useState(false);

  // Mirrors the server-side check in promover_item_rfi (api/app/rfi/router.py) -- a history-
  // confirmed item's justificativa is always the fixed anonymous placeholder, and an item already
  // linked to a procedure (internal match, or already promoted) has nothing new to add.
  const podePromover =
    (item.veredito === "atende" || item.veredito === "atende_parcial") &&
    !item.procedimento_id &&
    !item.confirmado_por_historico;

  const VEREDITO_LABEL: Record<VeredictoRfi, string> = {
    atende: t("rfiItemRow.atende"),
    atende_parcial: t("rfiItemRow.atendeParcial"),
    nao_atende: t("rfiItemRow.naoAtende"),
    sem_evidencia: t("rfiItemRow.semEvidencia"),
  };

  async function reavaliar() {
    setReavaliando(true);
    try {
      const atualizado = await api.reavaliarItemRfi(rfiId, item.id);
      onAtualizado(atualizado);
      setVeredito(atualizado.veredito ?? "sem_evidencia");
      setJustificativa(atualizado.justificativa ?? "");
    } finally {
      setReavaliando(false);
    }
  }

  async function salvar() {
    setSalvando(true);
    try {
      const atualizado = await api.sobrescreverVeredictoRfi(rfiId, item.id, {
        veredito,
        justificativa: justificativa || null,
      });
      onAtualizado(atualizado);
      setEditando(false);
    } finally {
      setSalvando(false);
    }
  }

  async function promover() {
    setPromovendo(true);
    try {
      const atualizado = await api.promoverItemRfi(rfiId, item.id);
      onAtualizado(atualizado);
    } finally {
      setPromovendo(false);
    }
  }

  return (
    <div className="item-row">
      <div
        style={{ display: "flex", gap: 12, alignItems: "center", padding: "10px 14px", cursor: "pointer" }}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="item-codigo">{item.codigo}</span>
        <span className="item-titulo" style={{ flex: 1 }}>
          {item.descricao}
          {item.categoria_codigo && (
            <span className="chip" style={{ marginLeft: 8 }} title={rotuloCategoria(item.categoria_codigo, lang)}>
              {item.categoria_codigo}
            </span>
          )}
        </span>
        {item.veredito ? (
          <span className={`badge ${VEREDITO_BADGE[item.veredito]}`}>{VEREDITO_LABEL[item.veredito]}</span>
        ) : (
          <span className="badge badge-info">{t("rfiItemRow.processando")}</span>
        )}
      </div>

      {open && (
        <div className="item-row-body">
          {!item.veredito && (
            <p style={{ marginTop: 0 }}>
              <b>{item.etapa ? t(`rfiItemRow.etapa.${item.etapa}`) : t("rfiItemRow.etapa.fila")}</b>
            </p>
          )}
          {item.justificativa && <p className="muted" style={{ marginTop: 0 }}>{item.justificativa}</p>}
          {item.procedimento_id && (
            <p style={{ marginTop: 0 }}>
              <Link to={`/procedimentos/${item.procedimento_id}`} className="btn btn-secondary" style={{ display: "inline-flex" }}>
                {t("rfiItemRow.verProcedimentoInterno")}
              </Link>
            </p>
          )}
          {item.confirmado_por_historico && (
            <p style={{ marginTop: 0 }}>
              <span className="badge badge-muted">{t("rfiItemRow.confirmadoHistorico")}</span>
            </p>
          )}
          {item.fontes.length > 0 && (
            <ul style={{ margin: "0 0 12px", paddingLeft: 18 }}>
              {item.fontes.map((f, i) => (
                <li key={i}>
                  <a href={f.url} target="_blank" rel="noreferrer">
                    {f.titulo}
                  </a>
                </li>
              ))}
            </ul>
          )}

          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-secondary" onClick={reavaliar} disabled={reavaliando} type="button">
              {reavaliando ? t("rfiItemRow.reavaliando") : t("rfiItemRow.reavaliar")}
            </button>
            <button className="btn btn-secondary" onClick={() => setEditando((v) => !v)} type="button">
              {editando ? t("common.cancelar") : t("rfiItemRow.sobrescrever")}
            </button>
            {podePromover && (
              <button className="btn btn-secondary" onClick={promover} disabled={promovendo} type="button">
                {promovendo ? t("rfiItemRow.promovendo") : t("rfiItemRow.promover")}
              </button>
            )}
          </div>

          {editando && (
            <div style={{ marginTop: 12, display: "grid", gap: 10 }}>
              <div className="field">
                <label>{t("rfiItemRow.veredito")}</label>
                <select
                  className="input"
                  value={veredito}
                  onChange={(e) => setVeredito(e.target.value as VeredictoRfi)}
                >
                  <option value="atende">{VEREDITO_LABEL.atende}</option>
                  <option value="atende_parcial">{VEREDITO_LABEL.atende_parcial}</option>
                  <option value="nao_atende">{VEREDITO_LABEL.nao_atende}</option>
                  <option value="sem_evidencia">{VEREDITO_LABEL.sem_evidencia}</option>
                </select>
              </div>
              <div className="field">
                <label>{t("rfiItemRow.justificativa")}</label>
                <textarea
                  className="input"
                  rows={2}
                  value={justificativa}
                  onChange={(e) => setJustificativa(e.target.value)}
                />
              </div>
              <div>
                <button className="btn btn-primary" onClick={salvar} disabled={salvando} type="button">
                  {salvando ? t("common.salvando") : t("common.salvar")}
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

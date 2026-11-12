import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError, RfiDetail as RfiDetailData, RfiDocumentoOut, RfiItemOut, VeredictoRfi } from "@/api";
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

const VEREDITO_LABEL_KEY: Record<VeredictoRfi, string> = {
  atende: "rfiItemRow.atende",
  atende_parcial: "rfiItemRow.atendeParcial",
  nao_atende: "rfiItemRow.naoAtende",
  sem_evidencia: "rfiItemRow.semEvidencia",
};

function veredictoLabels(t: (key: string) => string): Record<VeredictoRfi, string> {
  const chaves: VeredictoRfi[] = ["atende", "atende_parcial", "nao_atende", "sem_evidencia"];
  return Object.fromEntries(chaves.map((v) => [v, t(VEREDITO_LABEL_KEY[v])])) as Record<VeredictoRfi, string>;
}

function contagemVeredito(
  contagem: { atende: number; atende_parcial: number; nao_atende: number; sem_evidencia: number },
  t: (key: string) => string,
): string {
  const chaves: VeredictoRfi[] = ["atende", "atende_parcial", "nao_atende", "sem_evidencia"];
  return chaves
    .filter((v) => contagem[v] > 0)
    .map((v) => `${contagem[v]} ${t(VEREDITO_LABEL_KEY[v]).toLowerCase()}`)
    .join(" · ");
}

// Mesmo texto do início de JUSTIFICATIVA_ERRO em api/app/rfi/service.py -- deixa o feed de
// atividade (abaixo) mostrar "falhou" em vez de "sem evidência" quando o veredito só existe
// porque a avaliação deu erro (ver app/rfi/service.py::avaliar_item_rfi), não porque a pesquisa
// genuinamente não achou nada.
const MARCA_ERRO_AVALIACAO = "Não foi possível avaliar este item:";

interface FeedEntry {
  id: string;
  hora: string;
  codigo: string;
  texto?: string;
  badgeClasse?: string;
  badgeTexto?: string;
}

function horaAtual(): string {
  return new Date().toLocaleTimeString();
}

// Compara os itens recebidos no polling contra o snapshot anterior (guardado em `vistos`, um
// Map mutado aqui mesmo) e devolve as entradas novas pro feed de atividade -- é assim que a tela
// mostra "o que aconteceu" sem precisar de nenhum log novo no backend: cada poll já traz o estado
// atual de todo item, só precisa notar o que mudou desde o poll anterior. Na primeira carga
// (`primeiraCarga`) só preenche o snapshot, sem gerar entradas -- senão reabrir um RFI já pronto
// faria o feed "replay" o resultado de todos os itens de uma vez.
function diffParaFeed(
  itens: RfiItemOut[],
  vistos: Map<string, { veredito: VeredictoRfi | null; etapa: string | null }>,
  primeiraCarga: boolean,
  t: (key: string) => string,
): FeedEntry[] {
  const labels = veredictoLabels(t);
  const entradas: FeedEntry[] = [];
  for (const item of itens) {
    const anterior = vistos.get(item.id);
    if (!anterior) {
      if (!primeiraCarga) {
        entradas.push({
          id: `${item.id}-${Date.now()}-novo`,
          hora: horaAtual(),
          codigo: item.codigo,
          texto: t("rfiDetail.feedExtraido"),
        });
      }
    } else if (anterior.veredito !== item.veredito && item.veredito) {
      const comErro = (item.justificativa ?? "").startsWith(MARCA_ERRO_AVALIACAO);
      entradas.push({
        id: `${item.id}-${Date.now()}-veredito`,
        hora: horaAtual(),
        codigo: item.codigo,
        badgeClasse: comErro ? "badge-vermelho" : VEREDITO_BADGE[item.veredito],
        badgeTexto: comErro ? t("rfiDetail.feedErroBadge") : labels[item.veredito],
      });
    } else if (anterior.etapa !== item.etapa && item.etapa && !item.veredito) {
      entradas.push({
        id: `${item.id}-${Date.now()}-etapa-${item.etapa}`,
        hora: horaAtual(),
        codigo: item.codigo,
        texto: t(`rfiItemRow.etapa.${item.etapa}`),
      });
    }
    vistos.set(item.id, { veredito: item.veredito, etapa: item.etapa });
  }
  return entradas;
}

export function RfiDetail() {
  const { id } = useParams();
  const { t, lang } = useLanguage();
  const navigate = useNavigate();
  const [rfi, setRfi] = useState<RfiDetailData | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [feed, setFeed] = useState<FeedEntry[]>([]);
  const [reextraindo, setReextraindo] = useState(false);
  const pollRef = useRef<number | null>(null);
  const vistosRef = useRef<Map<string, { veredito: VeredictoRfi | null; etapa: string | null }>>(new Map());
  const primeiraCargaRef = useRef(true);

  function carregar() {
    if (!id) return;
    api
      .obterRfi(id)
      .then((data) => {
        setRfi(data);
        const novasEntradas = diffParaFeed(data.itens, vistosRef.current, primeiraCargaRef.current, t);
        primeiraCargaRef.current = false;
        if (novasEntradas.length > 0) {
          setFeed((prev) => [...novasEntradas.reverse(), ...prev].slice(0, 60));
        }
        const aindaProcessando = data.status_extracao === "extraindo" || data.itens.some((i) => i.veredito === null);
        if (aindaProcessando) {
          pollRef.current = window.setTimeout(carregar, 3000);
        }
      })
      .catch(() => setErro(t("rfiDetail.erroCarregar")));
  }

  useEffect(() => {
    vistosRef.current = new Map();
    primeiraCargaRef.current = true;
    setFeed([]);
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

  async function tentarNovamente() {
    setReextraindo(true);
    try {
      await api.reextrairRfi(rfi!.id);
      carregar();
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : t("rfiDetail.erroReextrair"));
    } finally {
      setReextraindo(false);
    }
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
  // Item que o progresso diz estar sendo avaliado agora -- junta com o `etapa` dele (já
  // atualizado pelo mesmo polling) pra mostrar o passo real na faixa de status, não só o índice
  // "3/10" (ver _etapa em api/app/rfi/service.py).
  const itemEmAndamento =
    rfi.progresso && (rfi.progresso.fase === "avaliando" || rfi.progresso.fase === "reavaliando")
      ? rfi.itens.find((i) => i.codigo === rfi.progresso?.nome)
      : undefined;

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
          <div style={{ display: "flex", gap: 24, alignItems: "flex-end" }}>
            {rfi.score !== null && (
              <div className="poc-pct">
                <b style={rfi.score >= 70 ? undefined : { color: rfi.score >= 40 ? "var(--color-warning)" : "var(--color-danger)" }}>
                  {rfi.score}%
                </b>
                <span>
                  {t("rfiDetail.atendimento")}
                  {rfi.contagem_veredito && ` · ${contagemVeredito(rfi.contagem_veredito, t)}`}
                </span>
              </div>
            )}
            <div className="poc-pct">
              <b>{pct}%</b>
              <span>
                {rfi.itens_avaliados}/{rfi.total_itens} {t("rfiDetail.avaliados")}
              </span>
            </div>
          </div>
        </div>
      </div>

      {rfi.status_extracao === "erro" && (
        <p className="alert alert-error" style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <span style={{ flex: 1 }}>{rfi.erro_extracao}</span>
          <button
            type="button"
            className="btn-icon"
            title={t("rfiDetail.tentarNovamente")}
            aria-label={t("rfiDetail.tentarNovamente")}
            disabled={reextraindo}
            onClick={() => void tentarNovamente()}
          >
            {reextraindo ? "…" : "↻"}
          </button>
        </p>
      )}
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
                    .replace("{nome}", rfi.progresso.nome) +
                  (itemEmAndamento?.etapa ? ` — ${t(`rfiItemRow.etapa.${itemEmAndamento.etapa}`)}` : "")
                : t("rfiDetail.iniciando")
          }
          cancelamentoSolicitado={rfi.cancelamento_solicitado}
          rotuloCancelar={t("rfiDetail.cancelar")}
          onCancelar={() => void api.cancelarRfi(rfi.id).then(carregar)}
        />
      )}

      {feed.length > 0 && (
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="muted" style={{ marginBottom: 8, fontSize: 13 }}>
            {t("rfiDetail.feedTitulo")}
          </div>
          <div style={{ maxHeight: 220, overflowY: "auto", display: "flex", flexDirection: "column", gap: 6 }}>
            {feed.map((entrada) => (
              <div key={entrada.id} style={{ fontSize: 13, display: "flex", gap: 8, alignItems: "baseline" }}>
                <span className="muted" style={{ fontFamily: "monospace", flexShrink: 0 }}>
                  {entrada.hora}
                </span>
                <span className="item-codigo">{entrada.codigo}</span>
                {entrada.badgeClasse ? (
                  <span className={`badge ${entrada.badgeClasse}`} style={{ fontSize: 11 }}>
                    {entrada.badgeTexto}
                  </span>
                ) : (
                  <span className="muted">{entrada.texto}</span>
                )}
              </div>
            ))}
          </div>
        </div>
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
  const [erroReavaliar, setErroReavaliar] = useState<string | null>(null);

  const VEREDITO_LABEL = veredictoLabels(t);

  async function reavaliar() {
    setReavaliando(true);
    setErroReavaliar(null);
    try {
      const atualizado = await api.reavaliarItemRfi(rfiId, item.id);
      onAtualizado(atualizado);
      setVeredito(atualizado.veredito ?? "sem_evidencia");
      setJustificativa(atualizado.justificativa ?? "");
    } catch (e) {
      // Item que já tinha um veredito confirmado: o backend preserva esse veredito e devolve o
      // erro real do Gemini (ver reavaliar_item em api/app/rfi/router.py) em vez de apagar uma
      // resposta boa por uma falha transiente -- sem isto, o botão só parava de girar e o
      // usuário não saberia que a tentativa falhou.
      setErroReavaliar(e instanceof ApiError ? e.message : t("rfiItemRow.erroReavaliar"));
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
        {item.procedimento_id && (
          <span className="badge badge-procedimento" title={item.procedimento_titulo ?? undefined}>
            {t("rfiItemRow.procedimentoInterno")}
          </span>
        )}
        {!item.procedimento_id && item.confirmado_por_historico && (
          <span className="badge badge-muted">{t("rfiItemRow.confirmadoHistoricoBadge")}</span>
        )}
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
          {erroReavaliar && <p className="alert alert-error" style={{ marginTop: 0 }}>{erroReavaliar}</p>}
          {item.procedimento_id && (
            <p style={{ marginTop: 0 }}>
              <Link to={`/procedimentos/${item.procedimento_id}`} className="btn btn-secondary" style={{ display: "inline-flex" }}>
                {t("rfiItemRow.verProcedimentoInterno")}
                {item.procedimento_titulo ? `: ${item.procedimento_titulo}` : ""}
              </Link>
            </p>
          )}
          {item.confirmado_por_historico && (
            <p style={{ marginTop: 0 }}>
              <span className="badge badge-muted">{t("rfiItemRow.confirmadoHistorico")}</span>
            </p>
          )}
          {item.fontes.length > 0 && (
            <>
              {item.procedimento_id && <p className="muted">{t("rfiItemRow.fontesComplementares")}</p>}
              <ul style={{ paddingLeft: 18, margin: 0, display: "flex", flexDirection: "column", gap: 4 }}>
                {item.fontes.map((f, i) => (
                  <li key={i} style={{ display: "list-item" }}>
                    <a href={f.url} target="_blank" rel="noreferrer">
                      {f.titulo}
                    </a>
                  </li>
                ))}
              </ul>
            </>
          )}

          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-secondary" onClick={reavaliar} disabled={reavaliando} type="button">
              {reavaliando ? t("rfiItemRow.reavaliando") : t("rfiItemRow.reavaliar")}
            </button>
            <button className="btn btn-secondary" onClick={() => setEditando((v) => !v)} type="button">
              {editando ? t("common.cancelar") : t("rfiItemRow.sobrescrever")}
            </button>
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

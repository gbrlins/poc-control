import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  api,
  CondicaoItem,
  Fase,
  FlagClassificacao,
  ItemPoc,
  PocDetail as PocDetailData,
  ProcedimentoDetail,
  ProcedimentoListItem,
  Sessao,
  StatusItem,
} from "@/api";
import { CODIGOS_CATEGORIA, rotuloCategoria } from "@/categorias";
import { DangerZone } from "@/components/DangerZone";
import { useLanguage } from "@/i18n";

const TAB_IDS = ["pre", "plano", "resumo", "andamento", "apresentacao"] as const;
type TabId = (typeof TAB_IDS)[number];

const TAB_LABEL_KEY: Record<TabId, string> = {
  plano: "pocDetail.tabPlano",
  pre: "pocDetail.tabPre",
  resumo: "pocDetail.tabResumo",
  andamento: "pocDetail.tabAndamento",
  apresentacao: "pocDetail.tabApresentacao",
};

function statusLabels(t: (k: string) => string): Record<StatusItem, string> {
  return {
    pendente: t("pocDetail.statusPendente"),
    em_andamento: t("pocDetail.statusEmAndamento"),
    concluido: t("pocDetail.statusConcluido"),
    bloqueado: t("pocDetail.statusBloqueado"),
    nao_aplicavel: t("pocDetail.statusNaoAplicavel"),
  };
}

function conducaoLabels(t: (k: string) => string): Record<CondicaoItem, string> {
  return {
    suse: t("pocDetail.conducaoSuse"),
    cliente: t("pocDetail.conducaoCliente"),
    lateral: t("pocDetail.conducaoLateral"),
  };
}

function flagLabels(t: (k: string) => string): Record<FlagClassificacao, string> {
  return {
    verde: t("pocDetail.flagVerde"),
    amarelo: t("pocDetail.flagAmarelo"),
    vermelho: t("pocDetail.flagVermelho"),
  };
}

function pct(total: number, concluidos: number) {
  if (total === 0) return 0;
  return Math.round((concluidos / total) * 100);
}

function faseTitulo(fases: Fase[], numero: number) {
  return fases.find((f) => f.numero === numero)?.titulo ?? `Fase ${numero}`;
}

function faseDescricao(fases: Fase[], numero: number) {
  return fases.find((f) => f.numero === numero)?.descricao ?? "";
}

export function PocDetail() {
  const { t } = useLanguage();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [poc, setPoc] = useState<PocDetailData | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [tab, setTab] = useState<TabId>("plano");
  const [procedimentos, setProcedimentos] = useState<ProcedimentoListItem[]>([]);
  const [classificandoLote, setClassificandoLote] = useState(false);
  const [reextraindo, setReextraindo] = useState(false);
  const [selecionados, setSelecionados] = useState<Set<string>>(new Set());
  const pollRef = useRef<number | null>(null);
  const pollLoteRef = useRef<number | null>(null);

  useEffect(() => {
    api.listarProcedimentos().then(setProcedimentos).catch(() => {});
  }, []);

  function carregar() {
    if (!id) return;
    api
      .obterPoc(id)
      .then((data) => {
        setPoc(data);
        if (data.status_extracao === "extraindo") {
          pollRef.current = window.setTimeout(carregar, 3000);
        }
      })
      .catch(() => setErro(t("pocDetail.erroCarregar")));
  }

  useEffect(() => {
    carregar();
    return () => {
      if (pollRef.current) window.clearTimeout(pollRef.current);
      if (pollLoteRef.current) window.clearTimeout(pollLoteRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  function handleItemAtualizado(atualizado: ItemPoc) {
    setPoc((atual) => (atual ? { ...atual, itens: atual.itens.map((i) => (i.id === atualizado.id ? atualizado : i)) } : atual));
  }

  async function classificarPendentes() {
    if (!id) return;
    setClassificandoLote(true);
    await api.classificarPendentes(id);

    function poll() {
      api.obterPoc(id!).then((data) => {
        setPoc(data);
        const faltam = data.itens.some((i) => !i.classificacao);
        if (faltam) {
          pollLoteRef.current = window.setTimeout(poll, 4000);
        } else {
          setClassificandoLote(false);
        }
      });
    }
    pollLoteRef.current = window.setTimeout(poll, 4000);
  }

  function handleItemRemovido(itemId: string) {
    setPoc((atual) => (atual ? { ...atual, itens: atual.itens.filter((i) => i.id !== itemId) } : atual));
    setSelecionados((atual) => {
      if (!atual.has(itemId)) return atual;
      const novo = new Set(atual);
      novo.delete(itemId);
      return novo;
    });
  }

  function toggleSelecionado(itemId: string) {
    setSelecionados((atual) => {
      const novo = new Set(atual);
      if (novo.has(itemId)) novo.delete(itemId);
      else novo.add(itemId);
      return novo;
    });
  }

  function abrirRoteiro() {
    if (!poc || selecionados.size === 0) return;
    window.open(api.urlRoteiro(poc.id, [...selecionados]), "_blank", "noreferrer");
  }

  async function tentarNovamente() {
    if (!id) return;
    setReextraindo(true);
    try {
      await api.reextrairPoc(id);
      carregar();
    } catch {
      setErro(t("pocDetail.erroReextrair"));
    } finally {
      setReextraindo(false);
    }
  }

  function handleSessaoCriada(sessao: Sessao) {
    setPoc((atual) => (atual ? { ...atual, sessoes: [...atual.sessoes, sessao] } : atual));
  }

  function handleResumoExecutivoAtualizado(texto: string) {
    setPoc((atual) => (atual ? { ...atual, resumo_executivo: texto } : atual));
  }

  function handlePrereqAtualizado(prereq: { id: string; atendido: boolean }) {
    setPoc((atual) =>
      atual
        ? {
            ...atual,
            prerequisitos: atual.prerequisitos.map((p) => (p.id === prereq.id ? { ...p, atendido: prereq.atendido } : p)),
          }
        : atual
    );
  }

  if (erro) return <p className="alert alert-error">{erro}</p>;
  if (!poc) return <p className="muted">{t("common.carregando")}</p>;

  const totalConcluido = poc.itens.filter((i) => i.status === "concluido").length;
  const porFase = new Map<number, ItemPoc[]>();
  for (const item of poc.itens) {
    const lista = porFase.get(item.fase) ?? [];
    lista.push(item);
    porFase.set(item.fase, lista);
  }
  const numerosFase = [...porFase.keys()].sort((a, b) => a - b);

  return (
    <div>
      <div className="poc-header">
        <div className="poc-header-top">
          <div>
            <h1>{poc.titulo}</h1>
            <div className="poc-sub">
              {poc.cliente} · {poc.itens.length} {t("pocDetail.itens")}
            </div>
          </div>
          <div className="poc-pct">
            <b>{pct(poc.itens.length, totalConcluido)}%</b>
            <span>{t("pocDetail.itensConcluidos")}</span>
          </div>
        </div>

        <a
          href={api.urlExportarPoc(poc.id)}
          target="_blank"
          rel="noreferrer"
          className="btn btn-secondary"
          style={{ display: "inline-block", marginTop: 12 }}
        >
          {t("pocDetail.exportarStatus")}
        </a>

        {numerosFase.length > 0 && (
          <div className="phase-strip">
            {numerosFase.map((n) => {
              const itensFase = porFase.get(n)!;
              const total = itensFase.length;
              const segs: { cor: string; pct: number }[] = [
                { cor: "var(--color-success)", pct: itensFase.filter((i) => i.status === "concluido").length },
                { cor: "var(--color-info)", pct: itensFase.filter((i) => i.status === "em_andamento").length },
                { cor: "var(--color-danger)", pct: itensFase.filter((i) => i.status === "bloqueado").length },
                {
                  cor: "rgba(255,255,255,.35)",
                  pct: itensFase.filter((i) => i.status === "pendente" || i.status === "nao_aplicavel").length,
                },
              ];
              return (
                <div className="phase-seg" key={n} title={faseTitulo(poc.fases, n)}>
                  <div className="bar">
                    {segs.map((s, i) =>
                      s.pct > 0 ? (
                        <i key={i} style={{ width: `${(s.pct / total) * 100}%`, background: s.cor }} />
                      ) : null
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {poc.status_extracao === "extraindo" && <p className="alert alert-success">{t("pocDetail.extraindo")}</p>}
      {poc.status_extracao === "pronto" && poc.modelo_extracao && (
        <p className="muted" style={{ fontSize: 13 }}>
          {t("pocDetail.extraidoCom").replace("{modelo}", poc.modelo_extracao)}
        </p>
      )}
      {poc.status_extracao === "erro" && (
        <p className="alert alert-error">
          {t("pocDetail.erroExtracao")} {poc.erro_extracao ?? t("pocDetail.erroDesconhecido")}
          <button
            className="btn btn-secondary"
            onClick={tentarNovamente}
            disabled={reextraindo}
            type="button"
            style={{ marginLeft: 12 }}
          >
            {reextraindo ? t("common.enviando") : t("pocDetail.tentarNovamente")}
          </button>
        </p>
      )}

      <div className="poc-tabs">
        {TAB_IDS.map((tid) => (
          <button
            key={tid}
            className={tab === tid ? "poc-tab active" : "poc-tab"}
            onClick={() => setTab(tid)}
          >
            {t(TAB_LABEL_KEY[tid])}
          </button>
        ))}
      </div>

      {tab === "plano" && (
        <div className="card">
          {poc.itens.length > 0 && (
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                flexWrap: "wrap",
                gap: 8,
                marginBottom: 12,
              }}
            >
              <span className="muted" style={{ fontSize: 13 }}>
                {t("pocDetail.roteiroSelecionados").replace("{n}", String(selecionados.size))}
              </span>
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  className="btn btn-primary"
                  onClick={abrirRoteiro}
                  disabled={selecionados.size === 0}
                  type="button"
                >
                  {t("pocDetail.gerarRoteiro")}
                </button>
                <button className="btn btn-secondary" onClick={classificarPendentes} disabled={classificandoLote}>
                  {classificandoLote ? t("pocDetail.classificando") : t("pocDetail.classificarPendentes")}
                </button>
              </div>
            </div>
          )}
          {poc.itens.length === 0 && <div className="empty-state">{t("pocDetail.nenhumItem")}</div>}
          {numerosFase.map((n) => (
            <div key={n}>
              <div className="fase-header">
                <span className="n">{n}</span>
                <h3>{faseTitulo(poc.fases, n)}</h3>
                {faseDescricao(poc.fases, n) && <p>{faseDescricao(poc.fases, n)}</p>}
              </div>
              {porFase
                .get(n)!
                .map((item) => (
                  <ItemRow
                    key={item.id}
                    pocId={poc.id}
                    item={item}
                    procedimentos={procedimentos}
                    sessoes={poc.sessoes}
                    selecionado={selecionados.has(item.id)}
                    onToggleSelecionado={() => toggleSelecionado(item.id)}
                    onAtualizado={handleItemAtualizado}
                    onRemovido={handleItemRemovido}
                  />
                ))}
            </div>
          ))}
        </div>
      )}

      {tab === "pre" && (
        <div className="card">
          {poc.prerequisitos.length === 0 && <div className="empty-state">{t("pocDetail.nenhumPrereq")}</div>}
          {poc.prerequisitos.map((p) => (
            <div key={p.id} className="item-row" style={{ padding: "10px 0" }}>
              <label style={{ display: "flex", gap: 10, alignItems: "flex-start", cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={p.atendido}
                  style={{ marginTop: 3 }}
                  onChange={(e) =>
                    api
                      .atualizarPrerequisito(poc.id, p.id, e.target.checked)
                      .then(handlePrereqAtualizado)
                  }
                />
                <span>
                  <strong style={{ textDecoration: p.atendido ? "line-through" : undefined }}>{p.titulo}</strong>
                  {p.descricao && <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>{p.descricao}</div>}
                </span>
              </label>
            </div>
          ))}
        </div>
      )}

      {tab === "resumo" && <ResumoTab poc={poc} porFase={porFase} numerosFase={numerosFase} />}

      {tab === "andamento" && <AndamentoTab poc={poc} onSessaoCriada={handleSessaoCriada} />}

      {tab === "apresentacao" && (
        <ApresentacaoTab poc={poc} onResumoAtualizado={handleResumoExecutivoAtualizado} />
      )}

      <DangerZone
        tipo="pocs"
        id={poc.id}
        responsavelId={poc.responsavel_id}
        responsavelEmail={poc.responsavel_email}
        onResponsavelAtualizado={(responsavelId, responsavelEmail) =>
          setPoc({ ...poc, responsavel_id: responsavelId, responsavel_email: responsavelEmail })
        }
        onExcluido={() => navigate("/pocs")}
      />
    </div>
  );
}

function ResumoTab({
  poc,
  porFase,
  numerosFase,
}: {
  poc: PocDetailData;
  porFase: Map<number, ItemPoc[]>;
  numerosFase: number[];
}) {
  const { t } = useLanguage();
  const STATUS_LABEL = statusLabels(t);
  const contagem: Record<StatusItem, number> = {
    pendente: 0,
    em_andamento: 0,
    concluido: 0,
    bloqueado: 0,
    nao_aplicavel: 0,
  };
  for (const item of poc.itens) contagem[item.status]++;
  const bloqueados = poc.itens.filter((i) => i.status === "bloqueado");

  return (
    <div>
      <div className="shortcut-grid" style={{ marginTop: 0, marginBottom: 20 }}>
        {(Object.keys(STATUS_LABEL) as StatusItem[]).map((s) => (
          <div className="card" key={s} style={{ padding: 16 }}>
            <div className="muted" style={{ fontSize: 12, textTransform: "uppercase", letterSpacing: "0.03em" }}>
              {STATUS_LABEL[s]}
            </div>
            <div style={{ fontSize: 26, fontWeight: 700, marginTop: 4 }}>{contagem[s]}</div>
          </div>
        ))}
      </div>

      <h2>{t("resumoTab.statusPorFase")}</h2>
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>{t("resumoTab.colFase")}</th>
                <th>{t("resumoTab.colItens")}</th>
                <th>{t("resumoTab.colConcluido")}</th>
                <th>{t("resumoTab.colBloqueado")}</th>
                <th>{t("resumoTab.colPendente")}</th>
              </tr>
            </thead>
            <tbody>
              {numerosFase.map((n) => {
                const itensFase = porFase.get(n)!;
                return (
                  <tr key={n}>
                    <td>{faseTitulo(poc.fases, n)}</td>
                    <td>{itensFase.length}</td>
                    <td>{itensFase.filter((i) => i.status === "concluido").length}</td>
                    <td>{itensFase.filter((i) => i.status === "bloqueado").length}</td>
                    <td>{itensFase.filter((i) => i.status === "pendente").length}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <h2>{t("resumoTab.itensBloqueados")}</h2>
      <div className="card">
        {bloqueados.length === 0 && <div className="empty-state">{t("resumoTab.nenhumBloqueado")}</div>}
        {bloqueados.length > 0 && (
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {bloqueados.map((i) => (
              <li key={i.id} style={{ marginBottom: 10 }}>
                <strong>{i.codigo}</strong> {i.titulo}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

type EntradaTimeline =
  | { tipo: "status"; created_at: string; codigo: string; anterior: StatusItem | null; novo: StatusItem }
  | { tipo: "nota"; created_at: string; codigo: string; texto: string };

function AndamentoTab({ poc, onSessaoCriada }: { poc: PocDetailData; onSessaoCriada: (s: Sessao) => void }) {
  const { t } = useLanguage();
  const STATUS_LABEL = statusLabels(t);
  const [data, setData] = useState("");
  const [participantes, setParticipantes] = useState("");
  const [agenda, setAgenda] = useState("");
  const [criando, setCriando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const [textoImportar, setTextoImportar] = useState("");
  const [importando, setImportando] = useState(false);
  const [erroImportar, setErroImportar] = useState<string | null>(null);

  const promptSugerido = `Resuma a sessão de hoje da PoC ${poc.cliente}: o que foi discutido e testado, o que foi resolvido, o que ficou com falha ou pendência, e quais são os próximos passos. Pode responder em texto corrido.`;

  async function copiarPrompt() {
    try {
      await navigator.clipboard.writeText(promptSugerido);
    } catch {
      // clipboard pode não estar disponível (ex.: contexto não seguro); segue sem copiar
    }
  }

  async function importarResumo() {
    if (!textoImportar.trim()) return;
    setErroImportar(null);
    setImportando(true);
    try {
      const sessao = await api.importarSessao(poc.id, textoImportar.trim());
      onSessaoCriada(sessao);
      setTextoImportar("");
    } catch {
      setErroImportar(t("andamentoTab.erroImportar"));
    } finally {
      setImportando(false);
    }
  }

  async function criarSessao() {
    if (!data) {
      setErro(t("andamentoTab.informeData"));
      return;
    }
    setErro(null);
    setCriando(true);
    try {
      const sessao = await api.criarSessao(poc.id, {
        data,
        participantes: participantes
          .split(",")
          .map((p) => p.trim())
          .filter(Boolean),
        agenda: agenda || null,
      });
      onSessaoCriada(sessao);
      setData("");
      setParticipantes("");
      setAgenda("");
    } catch {
      setErro(t("andamentoTab.erroCriarSessao"));
    } finally {
      setCriando(false);
    }
  }

  const porSessao = new Map<string | null, EntradaTimeline[]>();
  function registrar(sessaoId: string | null, entrada: EntradaTimeline) {
    const lista = porSessao.get(sessaoId) ?? [];
    lista.push(entrada);
    porSessao.set(sessaoId, lista);
  }
  for (const item of poc.itens) {
    for (const h of item.status_historico) {
      registrar(h.sessao_id, {
        tipo: "status",
        created_at: h.created_at,
        codigo: item.codigo,
        anterior: h.status_anterior,
        novo: h.status_novo,
      });
    }
    for (const n of item.notas) {
      registrar(n.sessao_id, { tipo: "nota", created_at: n.created_at, codigo: item.codigo, texto: n.texto });
    }
  }

  function renderEntrada(e: EntradaTimeline, i: number) {
    return (
      <li key={i} style={{ marginBottom: 4, fontSize: 13 }}>
        <strong>{e.codigo}</strong>{" "}
        {e.tipo === "status" ? (
          <>
            {t("andamentoTab.mudouDe")} {e.anterior ? STATUS_LABEL[e.anterior] : "—"} {t("andamentoTab.para")}{" "}
            {STATUS_LABEL[e.novo]}
          </>
        ) : (
          <>
            {t("andamentoTab.nota")} {e.texto}
          </>
        )}
      </li>
    );
  }

  const sessoesOrdenadas = [...poc.sessoes].sort((a, b) => (a.data < b.data ? 1 : -1));
  const semSessao = porSessao.get(null) ?? [];

  return (
    <div>
      <h2>{t("andamentoTab.sessoes")}</h2>

      <div className="card" style={{ marginBottom: 20 }}>
        <strong>{t("andamentoTab.importarResumo")}</strong>
        <p className="field-hint">{t("andamentoTab.importarHint")}</p>
        <div className="field">
          <label>{t("andamentoTab.promptSugerido")}</label>
          <textarea
            className="input"
            rows={2}
            readOnly
            value={promptSugerido}
            onClick={(e) => e.currentTarget.select()}
          />
          <button className="btn btn-secondary" onClick={copiarPrompt} type="button" style={{ marginTop: 6 }}>
            {t("andamentoTab.copiarPrompt")}
          </button>
        </div>
        <div className="field">
          <label>{t("andamentoTab.resumoDaSessao")}</label>
          <textarea
            className="input"
            rows={6}
            value={textoImportar}
            onChange={(e) => setTextoImportar(e.target.value)}
            placeholder={t("andamentoTab.resumoPlaceholder")}
          />
        </div>
        {erroImportar && <p className="alert alert-error">{erroImportar}</p>}
        <button
          className="btn btn-primary"
          onClick={importarResumo}
          disabled={importando || !textoImportar.trim()}
          type="button"
        >
          {importando ? t("andamentoTab.organizando") : t("andamentoTab.importar")}
        </button>
        {importando && <p className="muted" style={{ marginTop: 8, fontSize: 13 }}>{t("andamentoTab.podeDemorar")}</p>}
      </div>

      <div className="card" style={{ marginBottom: 20 }}>
        <strong>{t("andamentoTab.criarManual")}</strong>
        <div
          className="fields"
          style={{ marginTop: 10, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 10 }}
        >
          <div className="field">
            <label>{t("andamentoTab.data")}</label>
            <input type="date" className="input" value={data} onChange={(e) => setData(e.target.value)} />
          </div>
          <div className="field">
            <label>{t("andamentoTab.participantes")}</label>
            <input
              className="input"
              value={participantes}
              onChange={(e) => setParticipantes(e.target.value)}
              placeholder={t("andamentoTab.participantesPlaceholder")}
            />
          </div>
        </div>
        <div className="field">
          <label>{t("andamentoTab.agenda")}</label>
          <textarea className="input" rows={2} value={agenda} onChange={(e) => setAgenda(e.target.value)} />
        </div>
        {erro && <p className="alert alert-error">{erro}</p>}
        <button className="btn btn-primary" onClick={criarSessao} disabled={criando} type="button">
          {criando ? t("common.criando") : t("andamentoTab.novaSessao")}
        </button>
      </div>

      {sessoesOrdenadas.length === 0 && <div className="card empty-state">{t("andamentoTab.nenhumaSessao")}</div>}

      {sessoesOrdenadas.map((s) => {
        const entradas = (porSessao.get(s.id) ?? []).sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
        return (
          <SessaoCard key={s.id} pocId={poc.id} sessao={s} entradas={entradas} renderEntrada={renderEntrada} />
        );
      })}

      {semSessao.length > 0 && (
        <div className="card">
          <strong>{t("andamentoTab.semSessaoVinculada")}</strong>
          <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>{semSessao.map(renderEntrada)}</ul>
        </div>
      )}
    </div>
  );
}

function ApresentacaoTab({
  poc,
  onResumoAtualizado,
}: {
  poc: PocDetailData;
  onResumoAtualizado: (texto: string) => void;
}) {
  const { t } = useLanguage();
  const [resumo, setResumo] = useState(poc.resumo_executivo ?? "");
  const [gerando, setGerando] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [salvo, setSalvo] = useState(false);

  useEffect(() => {
    setResumo(poc.resumo_executivo ?? "");
  }, [poc.resumo_executivo]);

  async function gerar() {
    setGerando(true);
    try {
      const { texto } = await api.gerarResumoExecutivo(poc.id);
      setResumo(texto);
      onResumoAtualizado(texto);
    } finally {
      setGerando(false);
    }
  }

  async function salvar() {
    setSalvando(true);
    try {
      await api.salvarResumoExecutivo(poc.id, resumo);
      onResumoAtualizado(resumo);
      setSalvo(true);
      window.setTimeout(() => setSalvo(false), 2000);
    } finally {
      setSalvando(false);
    }
  }

  const totalConcluido = poc.itens.filter((i) => i.status === "concluido").length;

  return (
    <div>
      <h2>{t("apresentacaoTab.titulo")}</h2>
      <p className="field-hint">{t("apresentacaoTab.hint")}</p>

      <div className="card" style={{ marginBottom: 20 }}>
        <div
          style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}
        >
          <strong>{t("apresentacaoTab.sumarioExecutivo")}</strong>
          <button className="btn btn-secondary" onClick={gerar} disabled={gerando} type="button">
            {gerando ? t("apresentacaoTab.geminiEscrevendo") : t("apresentacaoTab.gerarIA")}
          </button>
        </div>
        <p className="field-hint">{t("apresentacaoTab.sumarioHint")}</p>
        <textarea
          className="input"
          rows={10}
          value={resumo}
          onChange={(e) => setResumo(e.target.value)}
          placeholder={t("apresentacaoTab.sumarioPlaceholder")}
        />
        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <button className="btn btn-primary" onClick={salvar} disabled={salvando || !resumo.trim()} type="button">
            {salvando ? t("common.salvando") : salvo ? t("apresentacaoTab.salvo") : t("common.salvar")}
          </button>
        </div>
      </div>

      <div className="shortcut-grid" style={{ marginBottom: 20 }}>
        <div className="card" style={{ padding: 16 }}>
          <div className="muted" style={{ fontSize: 12, textTransform: "uppercase", letterSpacing: "0.03em" }}>
            {t("apresentacaoTab.itensConcluidos")}
          </div>
          <div style={{ fontSize: 26, fontWeight: 700, marginTop: 4 }}>
            {totalConcluido}/{poc.itens.length}
          </div>
        </div>
        <div className="card" style={{ padding: 16 }}>
          <div className="muted" style={{ fontSize: 12, textTransform: "uppercase", letterSpacing: "0.03em" }}>
            {t("apresentacaoTab.sessoesRealizadas")}
          </div>
          <div style={{ fontSize: 26, fontWeight: 700, marginTop: 4 }}>{poc.sessoes.length}</div>
        </div>
      </div>

      <a href={api.urlApresentacaoPoc(poc.id)} target="_blank" rel="noreferrer" className="btn btn-primary">
        {t("apresentacaoTab.abrirApresentacao")}
      </a>
      <p className="field-hint" style={{ marginTop: 8 }}>
        {t("apresentacaoTab.imprimirHint")}
      </p>
    </div>
  );
}

function SessaoCard({
  pocId,
  sessao: s,
  entradas,
  renderEntrada,
}: {
  pocId: string;
  sessao: Sessao;
  entradas: EntradaTimeline[];
  renderEntrada: (e: EntradaTimeline, i: number) => JSX.Element;
}) {
  const { t } = useLanguage();
  const [gerando, setGerando] = useState(false);
  const [resumoEmail, setResumoEmail] = useState<string | null>(null);
  const [copiado, setCopiado] = useState(false);

  async function gerarResumo() {
    setGerando(true);
    setResumoEmail(null);
    try {
      const { texto } = await api.gerarResumoSessao(pocId, s.id);
      setResumoEmail(texto);
    } finally {
      setGerando(false);
    }
  }

  async function copiarResumo() {
    if (!resumoEmail) return;
    try {
      await navigator.clipboard.writeText(resumoEmail);
      setCopiado(true);
      window.setTimeout(() => setCopiado(false), 2000);
    } catch {
      // clipboard pode não estar disponível; segue sem copiar
    }
  }

  const temResumoImportado = s.pontos_resolvidos.length > 0 || s.pontos_falha.length > 0 || s.proximos_passos.length > 0;

  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <div>
          <strong>{new Date(s.data).toLocaleDateString("pt-BR")}</strong>
          {s.participantes.length > 0 && (
            <span className="muted" style={{ marginLeft: 8 }}>
              {s.participantes.join(", ")}
            </span>
          )}
        </div>
        <button className="btn btn-secondary" onClick={gerarResumo} disabled={gerando} type="button">
          {gerando ? t("apresentacaoTab.geminiEscrevendo") : t("sessaoCard.gerarResumoEmail")}
        </button>
      </div>

      {s.agenda && (
        <p className="muted" style={{ fontSize: 13, marginTop: 4 }}>
          {s.agenda}
        </p>
      )}

      {temResumoImportado && (
        <div style={{ marginTop: 10, display: "grid", gap: 10 }}>
          {s.pontos_resolvidos.length > 0 && (
            <div>
              <span className="badge badge-verde">{t("sessaoCard.resolvido")}</span>
              <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
                {s.pontos_resolvidos.map((p, i) => (
                  <li key={i} style={{ fontSize: 13 }}>
                    {p}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {s.pontos_falha.length > 0 && (
            <div>
              <span className="badge badge-vermelho">{t("sessaoCard.falhaPendencia")}</span>
              <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
                {s.pontos_falha.map((p, i) => (
                  <li key={i} style={{ fontSize: 13 }}>
                    {p}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {s.proximos_passos.length > 0 && (
            <div>
              <span className="badge badge-info">{t("sessaoCard.proximosPassos")}</span>
              <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
                {s.proximos_passos.map((p, i) => (
                  <li key={i} style={{ fontSize: 13 }}>
                    {p}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {entradas.length === 0 ? (
        !temResumoImportado && (
          <p className="empty-state" style={{ marginTop: 8 }}>
            {t("sessaoCard.nenhumRegistro")}
          </p>
        )
      ) : (
        <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>{entradas.map(renderEntrada)}</ul>
      )}

      {(gerando || resumoEmail !== null) && (
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--color-border)" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <strong>{t("sessaoCard.resumoParaEmail")}</strong>
            {resumoEmail && (
              <button className="btn btn-secondary" onClick={copiarResumo} type="button">
                {copiado ? t("sessaoCard.copiado") : t("sessaoCard.copiar")}
              </button>
            )}
          </div>
          {gerando ? (
            <p className="muted" style={{ marginTop: 8, fontSize: 13 }}>
              {t("andamentoTab.podeDemorar")}
            </p>
          ) : (
            <textarea className="input" rows={8} readOnly value={resumoEmail ?? ""} style={{ marginTop: 8 }} />
          )}
        </div>
      )}
    </div>
  );
}

function ProcedimentoFullscreen({ procedimentoId, onClose }: { procedimentoId: string; onClose: () => void }) {
  const { t } = useLanguage();
  const [procedimento, setProcedimento] = useState<ProcedimentoDetail | null>(null);

  useEffect(() => {
    setProcedimento(null);
    api.obterProcedimento(procedimentoId).then(setProcedimento);
  }, [procedimentoId]);

  return (
    <div className="procedimento-fullscreen">
      <div className="procedimento-fullscreen-head">
        <strong>{procedimento?.titulo ?? t("common.carregando")}</strong>
        <button className="btn btn-secondary" onClick={onClose} type="button">
          {t("common.fechar")}
        </button>
      </div>
      {procedimento && (
        <iframe
          title={procedimento.titulo}
          sandbox="allow-same-origin"
          srcDoc={procedimento.html_original}
          className="html-frame html-frame-fullscreen"
        />
      )}
    </div>
  );
}

function ItemRow({
  pocId,
  item,
  procedimentos,
  sessoes,
  selecionado,
  onToggleSelecionado,
  onAtualizado,
  onRemovido,
}: {
  pocId: string;
  item: ItemPoc;
  procedimentos: ProcedimentoListItem[];
  sessoes: Sessao[];
  selecionado: boolean;
  onToggleSelecionado: () => void;
  onAtualizado: (item: ItemPoc) => void;
  onRemovido: (itemId: string) => void;
}) {
  const { t, lang } = useLanguage();
  const STATUS_LABEL = statusLabels(t);
  const CONDUCAO_LABEL = conducaoLabels(t);
  const FLAG_LABEL = flagLabels(t);

  const [open, setOpen] = useState(false);
  const [editandoModal, setEditandoModal] = useState(false);
  const [titulo, setTitulo] = useState(item.titulo);
  const [descricao, setDescricao] = useState(item.descricao ?? "");
  const [criterio, setCriterio] = useState(item.criterio_aceite ?? "");
  const [categoria, setCategoria] = useState(item.categoria ?? "");
  const [categoriaCodigo, setCategoriaCodigo] = useState(item.categoria_codigo ?? "");
  const [fase, setFase] = useState(item.fase);
  const [conducao, setConducao] = useState<CondicaoItem | "">(item.conducao ?? "");
  const [salvando, setSalvando] = useState(false);
  const [reavaliando, setReavaliando] = useState(false);
  const [editandoManual, setEditandoManual] = useState(false);
  const [flagManual, setFlagManual] = useState<FlagClassificacao>(item.classificacao?.flag ?? "amarelo");
  const [procedimentoManual, setProcedimentoManual] = useState(item.classificacao?.procedimento_id ?? "");
  const [justificativaManual, setJustificativaManual] = useState(item.classificacao?.justificativa ?? "");
  const [salvandoManual, setSalvandoManual] = useState(false);
  const [maisOpcoes, setMaisOpcoes] = useState(false);

  const [importando, setImportando] = useState(false);
  const [sugestoes, setSugestoes] = useState<ProcedimentoListItem[] | null>(null);
  const [carregandoSugestoes, setCarregandoSugestoes] = useState(false);
  const [linkando, setLinkando] = useState(false);
  const [verProcedimento, setVerProcedimento] = useState(false);

  const [textoNota, setTextoNota] = useState("");
  const [salvandoNota, setSalvandoNota] = useState(false);

  const [sessaoAnexoId, setSessaoAnexoId] = useState("");
  const [arquivoAnexo, setArquivoAnexo] = useState<File | null>(null);
  const [enviandoAnexo, setEnviandoAnexo] = useState(false);
  const [validandoAnexoId, setValidandoAnexoId] = useState<string | null>(null);

  async function adicionarNota() {
    if (!textoNota.trim()) return;
    setSalvandoNota(true);
    try {
      const atualizado = await api.criarNota(pocId, item.id, null, textoNota.trim());
      onAtualizado(atualizado);
      setTextoNota("");
    } finally {
      setSalvandoNota(false);
    }
  }

  async function abrirImportar() {
    const abrindo = !importando;
    setImportando(abrindo);
    if (abrindo && sugestoes === null) {
      setCarregandoSugestoes(true);
      try {
        const lista = await api.sugerirProcedimentos(pocId, item.id);
        setSugestoes(lista);
      } catch {
        setSugestoes([]);
      } finally {
        setCarregandoSugestoes(false);
      }
    }
  }

  async function linkarProcedimento(procedimentoId: string) {
    if (!procedimentoId) return;
    setLinkando(true);
    try {
      const atualizado = await api.sobrescreverClassificacao(pocId, item.id, {
        flag: "verde",
        procedimento_id: procedimentoId,
        justificativa: null,
      });
      onAtualizado(atualizado);
      setImportando(false);
    } finally {
      setLinkando(false);
    }
  }

  async function excluirNota(notaId: string) {
    const atualizado = await api.removerNota(pocId, item.id, notaId);
    onAtualizado(atualizado);
  }

  async function enviarAnexo() {
    if (!arquivoAnexo) return;
    setEnviandoAnexo(true);
    try {
      const form = new FormData();
      form.append("arquivo", arquivoAnexo);
      if (sessaoAnexoId) form.append("sessao_id", sessaoAnexoId);
      const atualizado = await api.criarAnexo(pocId, item.id, form);
      onAtualizado(atualizado);
      setArquivoAnexo(null);
    } finally {
      setEnviandoAnexo(false);
    }
  }

  async function excluirAnexo(anexoId: string) {
    const atualizado = await api.removerAnexo(pocId, item.id, anexoId);
    onAtualizado(atualizado);
  }

  async function validarAnexo(anexoId: string) {
    setValidandoAnexoId(anexoId);
    try {
      const atualizado = await api.validarAnexo(pocId, item.id, anexoId);
      onAtualizado(atualizado);
    } finally {
      setValidandoAnexoId(null);
    }
  }

  async function reavaliar() {
    setReavaliando(true);
    try {
      const atualizado = await api.classificarItem(pocId, item.id);
      onAtualizado(atualizado);
      setFlagManual(atualizado.classificacao?.flag ?? "amarelo");
      setProcedimentoManual(atualizado.classificacao?.procedimento_id ?? "");
      setJustificativaManual(atualizado.classificacao?.justificativa ?? "");
    } finally {
      setReavaliando(false);
    }
  }

  async function salvarClassificacaoManual() {
    setSalvandoManual(true);
    try {
      const atualizado = await api.sobrescreverClassificacao(pocId, item.id, {
        flag: flagManual,
        procedimento_id: flagManual === "verde" ? procedimentoManual || null : null,
        justificativa: justificativaManual || null,
      });
      onAtualizado(atualizado);
      setEditandoManual(false);
    } finally {
      setSalvandoManual(false);
    }
  }

  const procedimentoVinculado = item.classificacao?.procedimento_id
    ? procedimentos.find((p) => p.id === item.classificacao!.procedimento_id)
    : undefined;
  const validados = procedimentos.filter((p) => p.status === "validado");

  async function salvar() {
    setSalvando(true);
    try {
      const atualizado = await api.atualizarItem(pocId, item.id, {
        titulo,
        descricao,
        criterio_aceite: criterio,
        categoria,
        categoria_codigo: categoriaCodigo || null,
        fase,
        conducao: conducao || null,
      });
      onAtualizado(atualizado);
      setEditandoModal(false);
    } finally {
      setSalvando(false);
    }
  }

  async function mudarStatus(status: StatusItem) {
    const atualizado = await api.atualizarItem(pocId, item.id, { status });
    onAtualizado(atualizado);
  }

  async function remover() {
    await api.removerItem(pocId, item.id);
    onRemovido(item.id);
  }

  return (
    <div className={open ? "item-row open" : "item-row"}>
      <div className="item-row-head" onClick={() => setOpen(!open)}>
        <input
          type="checkbox"
          checked={selecionado}
          title={t("pocDetail.selecionarParaRoteiro")}
          onClick={(e) => e.stopPropagation()}
          onChange={onToggleSelecionado}
          style={{ marginRight: 4 }}
        />
        <span className="item-codigo">{item.codigo}</span>
        <span className="item-titulo">
          {item.titulo}
          {item.categoria && <span className="muted" style={{ marginLeft: 8, fontSize: 12 }}>{item.categoria}</span>}
          {item.categoria_codigo && (
            <span className="chip" style={{ marginLeft: 8 }} title={rotuloCategoria(item.categoria_codigo, lang)}>
              {item.categoria_codigo}
            </span>
          )}
        </span>
        <button
          className="icon-btn"
          title={t("common.editar")}
          onClick={(e) => {
            e.stopPropagation();
            setEditandoModal(true);
          }}
          type="button"
        >
          <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
        {item.conducao && <span className={`chip chip-${item.conducao}`}>{CONDUCAO_LABEL[item.conducao]}</span>}
        <span className={`badge badge-${item.classificacao?.flag ?? "muted"}`}>
          {item.classificacao ? FLAG_LABEL[item.classificacao.flag] : t("itemRow.semSemaforo")}
        </span>
        <span className={`badge badge-${item.status}`}>{STATUS_LABEL[item.status]}</span>
      </div>

      {open && (
        <div className="item-row-body">
          <div className="field" style={{ maxWidth: 220 }}>
            <label>{t("itemRow.status")}</label>
            <select
              className="input"
              value={item.status}
              onChange={(e) => mudarStatus(e.target.value as StatusItem)}
            >
              {(Object.keys(STATUS_LABEL) as StatusItem[]).map((s) => (
                <option key={s} value={s}>
                  {STATUS_LABEL[s]}
                </option>
              ))}
            </select>
          </div>

          {editandoModal && (
            <div className="modal-backdrop" onClick={() => setEditandoModal(false)}>
              <div className="modal-janela" onClick={(e) => e.stopPropagation()}>
              <div className="field">
                <label>{t("itemRow.titulo")}</label>
                <input className="input" value={titulo} onChange={(e) => setTitulo(e.target.value)} />
              </div>
              <div className="field">
                <label>{t("itemRow.descricao")}</label>
                <textarea className="input" rows={3} value={descricao} onChange={(e) => setDescricao(e.target.value)} />
              </div>
              <div className="field">
                <label>{t("itemRow.criterioAceite")}</label>
                <textarea className="input" rows={2} value={criterio} onChange={(e) => setCriterio(e.target.value)} />
              </div>
              <div className="fields" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 10 }}>
                <div className="field">
                  <label>{t("itemRow.categoria")}</label>
                  <input className="input" value={categoria} onChange={(e) => setCategoria(e.target.value)} />
                </div>
                <div className="field">
                  <label>{t("itemRow.categoriaCodigo")}</label>
                  <select className="input" value={categoriaCodigo} onChange={(e) => setCategoriaCodigo(e.target.value)}>
                    <option value="">{t("itemRow.categoriaCodigoNenhuma")}</option>
                    {CODIGOS_CATEGORIA.map((codigo) => (
                      <option key={codigo} value={codigo}>
                        {codigo} — {rotuloCategoria(codigo, lang)}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label>{t("itemRow.fase")}</label>
                  <input
                    type="number"
                    min={1}
                    className="input"
                    value={fase}
                    onChange={(e) => setFase(Number(e.target.value))}
                  />
                </div>
                <div className="field">
                  <label>{t("itemRow.conducao")}</label>
                  <select className="input" value={conducao} onChange={(e) => setConducao(e.target.value as CondicaoItem | "")}>
                    <option value="">—</option>
                    <option value="suse">{CONDUCAO_LABEL.suse}</option>
                    <option value="cliente">{CONDUCAO_LABEL.cliente}</option>
                    <option value="lateral">{CONDUCAO_LABEL.lateral}</option>
                  </select>
                </div>
              </div>
              {item.ref && (
                <p className="field-hint">
                  {t("itemRow.referencia")} {item.ref}
                </p>
              )}
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn btn-primary" onClick={salvar} disabled={salvando}>
                  {salvando ? t("common.salvando") : t("common.salvar")}
                </button>
                <button className="btn btn-secondary" onClick={remover} type="button">
                  {t("itemRow.removerItem")}
                </button>
                <button className="btn btn-secondary" onClick={() => setEditandoModal(false)} type="button">
                  {t("common.fechar")}
                </button>
              </div>
              </div>
            </div>
          )}

          <div style={{ marginTop: 16, paddingTop: 16, borderTop: "1px solid var(--color-border)" }}>
            <strong>{t("itemRow.procedimento")}</strong>

            <div style={{ marginTop: 10, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              {procedimentoVinculado ? (
                <>
                  <span>
                    {t("itemRow.procedimentoLabel")}{" "}
                    <Link to={`/procedimentos/${procedimentoVinculado.id}`}>{procedimentoVinculado.titulo}</Link>
                  </span>
                  <button className="btn btn-secondary" onClick={() => setVerProcedimento(true)} type="button">
                    {t("itemRow.abrirTelaCheia")}
                  </button>
                </>
              ) : (
                <span className="empty-state">{t("itemRow.nenhumProcedimentoVinculado")}</span>
              )}
              <button className="btn btn-secondary" onClick={abrirImportar} type="button">
                {importando ? t("common.cancelar") : t("itemRow.importarProcedimento")}
              </button>
            </div>

            {importando && (
              <div style={{ marginTop: 10 }}>
                {carregandoSugestoes ? (
                  <p className="muted" style={{ fontSize: 13 }}>
                    {t("itemRow.carregandoSugestoes")}
                  </p>
                ) : (
                  <>
                    <p className="field-hint">{t("itemRow.sugestoesSimilares")}</p>
                    {sugestoes && sugestoes.length > 0 ? (
                      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                        {sugestoes.map((s) => (
                          <button
                            key={s.id}
                            className="btn btn-secondary"
                            style={{ textAlign: "left" }}
                            onClick={() => linkarProcedimento(s.id)}
                            disabled={linkando}
                            type="button"
                          >
                            {s.titulo}
                          </button>
                        ))}
                      </div>
                    ) : (
                      <p className="empty-state">{t("itemRow.semSugestoes")}</p>
                    )}
                  </>
                )}
                <div className="field" style={{ marginTop: 10 }}>
                  <label>{t("itemRow.escolherOutro")}</label>
                  <select
                    className="input"
                    value=""
                    disabled={linkando}
                    onChange={(e) => linkarProcedimento(e.target.value)}
                  >
                    <option value="">—</option>
                    {validados.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.titulo}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            )}
          </div>

          <div style={{ marginTop: 16, paddingTop: 16, borderTop: "1px solid var(--color-border)" }}>
            <strong>{t("itemRow.notas")}</strong>
            {item.notas.length === 0 ? (
              <p className="empty-state" style={{ marginTop: 8 }}>
                {t("itemRow.nenhumaNota")}
              </p>
            ) : (
              <ul style={{ margin: "8px 0", paddingLeft: 18 }}>
                {item.notas.map((n) => (
                  <li key={n.id} style={{ marginBottom: 6, fontSize: 13 }}>
                    {n.texto}{" "}
                    <button
                      className="btn btn-secondary"
                      style={{ fontSize: 11, padding: "1px 6px" }}
                      onClick={() => excluirNota(n.id)}
                      type="button"
                    >
                      {t("itemRow.remover")}
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <div style={{ display: "flex", gap: 8, alignItems: "flex-start", flexWrap: "wrap" }}>
              <textarea
                className="input"
                rows={1}
                style={{ flex: 1, minWidth: 160 }}
                value={textoNota}
                onChange={(e) => setTextoNota(e.target.value)}
                placeholder={t("itemRow.novaNotaPlaceholder")}
              />
              <button
                className="btn btn-secondary"
                onClick={adicionarNota}
                disabled={salvandoNota || !textoNota.trim()}
                type="button"
              >
                {t("itemRow.adicionar")}
              </button>
            </div>
          </div>

          <button className="btn btn-secondary" onClick={() => setMaisOpcoes((v) => !v)} type="button" style={{ marginTop: 16 }}>
            {maisOpcoes ? t("common.cancelar") : t("itemRow.maisOpcoes")}
          </button>

          {maisOpcoes && (
          <div style={{ marginTop: 16, paddingTop: 16, borderTop: "1px solid var(--color-border)" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
              <strong>{t("itemRow.classificacao")}</strong>
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn btn-secondary" onClick={reavaliar} disabled={reavaliando} type="button">
                  {reavaliando ? t("itemRow.reavaliando") : t("itemRow.reavaliar")}
                </button>
                <button className="btn btn-secondary" onClick={() => setEditandoManual((v) => !v)} type="button">
                  {editandoManual ? t("common.cancelar") : t("itemRow.sobrescrever")}
                </button>
              </div>
            </div>

            {item.classificacao ? (
              <div className="muted" style={{ fontSize: 13, marginTop: 8 }}>
                <div>
                  <span className={`badge badge-${item.classificacao.flag}`}>
                    {FLAG_LABEL[item.classificacao.flag]}
                  </span>{" "}
                  <span>
                    ({item.classificacao.origem === "manual" ? t("itemRow.ajustadoManualmente") : t("itemRow.automatico")})
                  </span>
                  {item.classificacao.modelo && (
                    <span> — {t("itemRow.respondidoPorModelo").replace("{modelo}", item.classificacao.modelo)}</span>
                  )}
                </div>
                {item.classificacao.justificativa && <p style={{ marginTop: 6 }}>{item.classificacao.justificativa}</p>}
                {item.classificacao.fontes.length > 0 && (
                  <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                    {item.classificacao.fontes.map((f, i) => (
                      <li key={i}>
                        <a href={f.url} target="_blank" rel="noreferrer">
                          {f.titulo}
                        </a>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ) : (
              <p className="empty-state" style={{ marginTop: 8 }}>
                {t("itemRow.naoClassificado")}
              </p>
            )}

            {editandoManual && (
              <div className="fields" style={{ marginTop: 12, display: "grid", gap: 10 }}>
                <div className="field">
                  <label>{t("itemRow.semaforo")}</label>
                  <select
                    className="input"
                    value={flagManual}
                    onChange={(e) => setFlagManual(e.target.value as FlagClassificacao)}
                  >
                    <option value="verde">{FLAG_LABEL.verde}</option>
                    <option value="amarelo">{FLAG_LABEL.amarelo}</option>
                    <option value="vermelho">{FLAG_LABEL.vermelho}</option>
                  </select>
                </div>
                {flagManual === "verde" && (
                  <div className="field">
                    <label>{t("itemRow.procedimentoVinculado")}</label>
                    <select
                      className="input"
                      value={procedimentoManual}
                      onChange={(e) => setProcedimentoManual(e.target.value)}
                    >
                      <option value="">—</option>
                      {validados.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.titulo}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                <div className="field">
                  <label>{t("itemRow.justificativa")}</label>
                  <textarea
                    className="input"
                    rows={2}
                    value={justificativaManual}
                    onChange={(e) => setJustificativaManual(e.target.value)}
                  />
                </div>
                <div>
                  <button
                    className="btn btn-primary"
                    onClick={salvarClassificacaoManual}
                    disabled={salvandoManual}
                    type="button"
                  >
                    {salvandoManual ? t("common.salvando") : t("itemRow.salvarClassificacaoManual")}
                  </button>
                </div>
              </div>
            )}
          </div>
          )}

          {maisOpcoes && (
          <div style={{ marginTop: 16, paddingTop: 16, borderTop: "1px solid var(--color-border)" }}>
            <strong>{t("itemRow.anexos")}</strong>
            {item.anexos.length === 0 ? (
              <p className="empty-state" style={{ marginTop: 8 }}>
                {t("itemRow.nenhumAnexo")}
              </p>
            ) : (
              <ul style={{ margin: "8px 0", paddingLeft: 18 }}>
                {item.anexos.map((a) => (
                  <li key={a.id} style={{ marginBottom: 6, fontSize: 13, display: "flex", alignItems: "center", gap: 8 }}>
                    <a href={api.urlAnexo(pocId, item.id, a.id)} target="_blank" rel="noreferrer">
                      {a.nome_arquivo}
                    </a>
                    {/\.(html?|txt|md)$/i.test(a.nome_arquivo) && (
                      <label style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                        <input
                          type="checkbox"
                          checked={a.procedimento_id != null}
                          disabled={a.procedimento_id != null || validandoAnexoId === a.id}
                          onChange={() => validarAnexo(a.id)}
                        />
                        {t("itemRow.validado")}
                      </label>
                    )}
                    <button
                      className="btn btn-secondary"
                      style={{ fontSize: 11, padding: "1px 6px" }}
                      onClick={() => excluirAnexo(a.id)}
                      type="button"
                    >
                      {t("itemRow.remover")}
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              {sessoes.length > 0 && (
                <select
                  className="input"
                  style={{ maxWidth: 160 }}
                  value={sessaoAnexoId}
                  onChange={(e) => setSessaoAnexoId(e.target.value)}
                >
                  <option value="">{t("itemRow.semSessao")}</option>
                  {sessoes.map((s) => (
                    <option key={s.id} value={s.id}>
                      {new Date(s.data).toLocaleDateString("pt-BR")}
                    </option>
                  ))}
                </select>
              )}
              <input type="file" onChange={(e) => setArquivoAnexo(e.target.files?.[0] ?? null)} />
              <button
                className="btn btn-secondary"
                onClick={enviarAnexo}
                disabled={enviandoAnexo || !arquivoAnexo}
                type="button"
              >
                {enviandoAnexo ? t("common.enviando") : t("itemRow.enviarAnexo")}
              </button>
            </div>
          </div>
          )}
        </div>
      )}

      {verProcedimento && procedimentoVinculado && (
        <ProcedimentoFullscreen procedimentoId={procedimentoVinculado.id} onClose={() => setVerProcedimento(false)} />
      )}
    </div>
  );
}

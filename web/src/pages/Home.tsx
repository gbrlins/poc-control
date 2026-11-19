import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { api, LicitacaoOut, PocListItem, ProcedimentoListItem, RfiListItem } from "@/api";
import { useLanguage } from "@/i18n";
import { traduzirMensagemServidor } from "@/mensagensServidor";
import { Icon } from "@/Icon";
import { ProjetosCard } from "./HomeProjetos";

const RECENTES = 5;
const RESULTADOS_BUSCA = 8;

interface HistoryRow {
  id: string;
  href: string;
  titulo: string;
  subtitulo: string;
  createdAt: string;
  // Lowercased blob of every field the card's search box should match against (título/nome do
  // projeto, cliente/órgão, responsável atual e quem criou) -- built once per row instead of
  // re-deriving it on every keystroke.
  busca: string;
}

function ordenarPorRecente<T extends { created_at: string }>(itens: T[] | null): T[] {
  if (!itens) return [];
  return [...itens].sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
}

function normalizar(s: string): string {
  return s.toLowerCase();
}

// "/", the app's entry point. A hub, not a feature screen itself: a hero + one action tile per
// functionality (Planejar PoC, RFI Analyser, Procedimentos), plus a compact, searchable "most
// recent" list per area below -- replaces the previous version, which embedded the full
// filterable PoC table directly here (that table/filter combo still exists, unchanged, at /pocs;
// see poc-planner/docs/design-unification.md §8 requirement 2). Modeled on the planner's own
// dashboard (poc-planner/index.html renderDashboard/renderProjectsList): icon badge + title +
// subtitle, then actions, then history.
export function Home() {
  const { t, lang } = useLanguage();
  const [pocs, setPocs] = useState<PocListItem[] | null>(null);
  const [rfis, setRfis] = useState<RfiListItem[] | null>(null);
  const [procedimentos, setProcedimentos] = useState<ProcedimentoListItem[] | null>(null);
  const [licitacoes, setLicitacoes] = useState<LicitacaoOut[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  useEffect(() => {
    Promise.all([api.listarPocs(), api.listarRfis(), api.listarProcedimentos(), api.listarLicitacoes()])
      .then(([p, r, proc, lic]) => {
        setPocs(p);
        setRfis(r);
        setProcedimentos(proc);
        setLicitacoes(lic);
      })
      .catch(() => setErro(t("pocs.erroCarregar")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // The full lists (not just the top 5) so each card's search box can look beyond "recent" --
  // api.listarPocs()/listarRfis()/listarProcedimentos() already fetch everything in one shot.
  const rfisOrdenados: HistoryRow[] = ordenarPorRecente(rfis).map((r) => ({
    id: r.id,
    href: `/rfis/${r.id}`,
    titulo: traduzirMensagemServidor(r.titulo, lang) || r.orgao,
    subtitulo: r.orgao,
    createdAt: r.created_at,
    busca: normalizar([r.titulo, r.orgao, r.responsavel_email, r.criado_por_email].filter(Boolean).join(" ")),
  }));
  const procedimentosOrdenados: HistoryRow[] = ordenarPorRecente(procedimentos).map((p) => ({
    id: p.id,
    href: `/procedures/${p.id}`,
    titulo: p.titulo,
    subtitulo: p.cliente_origem ?? "",
    createdAt: p.created_at,
    busca: normalizar(
      [p.titulo, p.cliente_origem, p.responsavel_email, p.criado_por_email].filter(Boolean).join(" "),
    ),
  }));

  return (
    <div className="home-hub">
      <div className="home-hero">
        <div className="home-hero-icon">
          <Icon name="layout" />
        </div>
        <h1>{t("home.title")}</h1>
        <p className="page-subtitle">{t("home.subtitle")}</p>
      </div>

      {erro && <p className="alert alert-error">{erro}</p>}

      <div className="home-actions">
        <Link to="/plan?new=1" className="home-action home-action-primary">
          <Icon name="plus" />
          <div>
            <strong>{t("home.actionPlanejar")}</strong>
            <span>{t("home.actionPlanejarDesc")}</span>
          </div>
        </Link>
        {/* A lista (com o botão "Novo RFI"), como as telas de Procedimentos e Licitações: dá pra ver os RFIs que já existem antes de criar outro. */}
        <Link to="/rfis" className="home-action home-action-rfi">
          <Icon name="eye" />
          <div>
            <strong>{t("home.analisarRfi")}</strong>
            <span>{t("home.actionRfiDesc")}</span>
          </div>
        </Link>
        <Link to="/procedures" className="home-action home-action-procedimentos">
          <Icon name="book" />
          <div>
            <strong>{t("nav.procedimentos")}</strong>
            <span>{t("home.actionProcedimentosDesc")}</span>
          </div>
        </Link>
        <Link to="/tenders" className="home-action home-action-licitacoes">
          <Icon name="broadcast" />
          <div>
            <strong>
              {t("home.actionLicitacoes")} <span className="beta-tag">{t("licitacoes.beta")}</span>
            </strong>
            <span>{t("home.actionLicitacoesDesc")}</span>
          </div>
        </Link>
      </div>

      <ProjetosCard pocs={pocs} />

      <div className="home-history-grid">
        <HistoryCard
          titulo={t("home.recentesRfis")}
          vazio={t("rfis.nenhumRfi")}
          verTodosHref="/rfis"
          verTodosLabel={t("home.verRfis")}
          carregando={rfis === null}
          itens={rfisOrdenados}
        />
        <HistoryCard
          titulo={t("home.recentesProcedimentos")}
          vazio={t("procedimentos.nenhum")}
          verTodosHref="/procedures"
          verTodosLabel={t("home.verProcedimentos")}
          carregando={procedimentos === null}
          itens={procedimentosOrdenados}
        />
      </div>

      <LicitacoesCard carregando={licitacoes === null} itens={licitacoes ?? []} />
    </div>
  );
}

// Card largo (não entra na grade de 4 colunas de HistoryCard acima -- "Licitações ao vivo" tem
// mais metadado por linha, por isso o pedido original foi por um card maior, não mais um da
// mesma grade) com as licitações mais recentes do beta (ver Licitacoes.tsx pra tela cheia e pro
// painel de admin dos termos de busca).
function LicitacoesCard({ carregando, itens }: { carregando: boolean; itens: LicitacaoOut[] }) {
  const { t } = useLanguage();
  const recentes = [...itens]
    .sort((a, b) => (a.data_publicacao < b.data_publicacao ? 1 : -1))
    .slice(0, RESULTADOS_BUSCA);

  return (
    <div className="card home-licitacoes-card">
      <h3>
        <Icon name="broadcast" /> {t("home.recentesLicitacoes")} <span className="beta-tag">{t("licitacoes.beta")}</span>
      </h3>
      {carregando && <p className="muted">{t("common.carregando")}</p>}
      {!carregando && recentes.length === 0 && <p className="empty-state">{t("licitacoes.nenhuma")}</p>}
      {!carregando &&
        recentes.map((lic) => (
          <div key={lic.id} className="history-row licitacao-row">
            <Link to="/tenders" className="licitacao-row-main">
              <div className="history-row-title">{lic.objeto}</div>
              <div className="history-row-sub">
                {lic.orgao_nome}
                {lic.uf ? ` · ${lic.uf}` : ""} · {lic.modalidade_nome ?? "—"} ·{" "}
                {new Date(lic.data_publicacao).toLocaleDateString()}
              </div>
            </Link>
            <a href={lic.link_pncp} target="_blank" rel="noreferrer" className="btn btn-secondary">
              {t("licitacoes.verEdital")}
            </a>
          </div>
        ))}
      {!carregando && itens.length > 0 && (
        <Link to="/tenders" className="history-row-all">
          {t("home.verLicitacoes")}
        </Link>
      )}
    </div>
  );
}

function HistoryCard({
  titulo,
  vazio,
  verTodosHref,
  verTodosLabel,
  carregando,
  itens,
}: {
  titulo: string;
  vazio: string;
  verTodosHref: string;
  verTodosLabel: string;
  carregando: boolean;
  itens: HistoryRow[];
}) {
  const { t } = useLanguage();
  const [busca, setBusca] = useState("");

  const termo = normalizar(busca.trim());
  const filtrados = termo ? itens.filter((it) => it.busca.includes(termo)) : itens;
  const exibidos = filtrados.slice(0, termo ? RESULTADOS_BUSCA : RECENTES);

  return (
    <div className="card home-history-card">
      <h3>
        <Icon name="folder" /> {titulo}
      </h3>
      {!carregando && (
        <input
          className="input history-search"
          type="text"
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
          placeholder={t("home.buscaPlaceholder")}
        />
      )}
      {carregando && <p className="muted">{t("common.carregando")}</p>}
      {!carregando && exibidos.length === 0 && (
        <p className="empty-state">{termo ? t("home.buscaSemResultado") : vazio}</p>
      )}
      {!carregando &&
        exibidos.map((it) => (
          <Link key={it.id} to={it.href} className="history-row">
            <div>
              <div className="history-row-title">{it.titulo}</div>
              <div className="history-row-sub">
                {it.subtitulo ? `${it.subtitulo} · ` : ""}
                {new Date(it.createdAt).toLocaleDateString()}
              </div>
            </div>
            <Icon name="chevronR" />
          </Link>
        ))}
      {!carregando && itens.length > 0 && (
        <Link to={verTodosHref} className="history-row-all">
          {verTodosLabel}
        </Link>
      )}
    </div>
  );
}

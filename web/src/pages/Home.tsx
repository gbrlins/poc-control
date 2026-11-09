import { Link, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { api, LicitacaoOut, PocListItem, ProcedimentoListItem, RfiListItem } from "@/api";
import { useLanguage } from "@/i18n";
import { Icon } from "@/Icon";

const RECENTES = 5;
const RESULTADOS_BUSCA = 8;

// Same-origin localStorage keys poc-planner/index.html uses for its own project list (see
// PROJECTS_INDEX_KEY/ACTIVE_PROJECT_KEY/projectKey there) -- read directly here instead of going
// through the embedded iframe, since the planner's "Meus Projetos" never reaches the server (see
// poc-control/CLAUDE.md "O planejador como tela inicial").
const PLANNER_PROJECTS_INDEX_KEY = "suse_poc_planner_projects";
const PLANNER_ACTIVE_PROJECT_KEY = "suse_poc_planner_active";
const plannerProjectKey = (id: string) => `suse_poc_planner_project_${id}`;

interface RascunhoLocal {
  id: string;
  titulo: string;
  updatedAt: number | null;
}

// Drafts already linked to a server PoC (state.pocControlId set, from the planner's "Habilitar
// execução") are excluded here -- they already show up in "PoCs recentes" above, so listing them
// again would duplicate the same project under two names.
function lerRascunhosLocais(semNome: string): RascunhoLocal[] {
  let indice: Array<{ id: string; name?: string; updatedAt?: number }> = [];
  try {
    indice = JSON.parse(localStorage.getItem(PLANNER_PROJECTS_INDEX_KEY) || "[]") || [];
  } catch {
    return [];
  }
  return indice
    .filter((entrada) => {
      try {
        const raw = localStorage.getItem(plannerProjectKey(entrada.id));
        const projeto = raw ? JSON.parse(raw) : null;
        return !projeto?.pocControlId;
      } catch {
        return true;
      }
    })
    .map((entrada) => ({
      id: entrada.id,
      titulo: entrada.name || semNome,
      updatedAt: entrada.updatedAt ?? null,
    }))
    .sort((a, b) => (b.updatedAt ?? 0) - (a.updatedAt ?? 0));
}

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
  const { t } = useLanguage();
  const navigate = useNavigate();
  const [pocs, setPocs] = useState<PocListItem[] | null>(null);
  const [rfis, setRfis] = useState<RfiListItem[] | null>(null);
  const [procedimentos, setProcedimentos] = useState<ProcedimentoListItem[] | null>(null);
  const [licitacoes, setLicitacoes] = useState<LicitacaoOut[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  // Re-read on every mount (e.g. coming back from /planejar) rather than once ever, since the
  // planner's localStorage can change without poc-control's own React tree re-rendering.
  const [rascunhos] = useState<RascunhoLocal[]>(() => lerRascunhosLocais(t("home.rascunhoSemNome")));

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
  const pocsOrdenados: HistoryRow[] = ordenarPorRecente(pocs).map((p) => ({
    id: p.id,
    href: `/pocs/${p.id}`,
    titulo: p.titulo,
    subtitulo: p.cliente,
    createdAt: p.created_at,
    busca: normalizar([p.titulo, p.cliente, p.responsavel_email, p.criado_por_email].filter(Boolean).join(" ")),
  }));
  const rfisOrdenados: HistoryRow[] = ordenarPorRecente(rfis).map((r) => ({
    id: r.id,
    href: `/rfis/${r.id}`,
    titulo: r.titulo || r.orgao,
    subtitulo: r.orgao,
    createdAt: r.created_at,
    busca: normalizar([r.titulo, r.orgao, r.responsavel_email, r.criado_por_email].filter(Boolean).join(" ")),
  }));
  const procedimentosOrdenados: HistoryRow[] = ordenarPorRecente(procedimentos).map((p) => ({
    id: p.id,
    href: `/procedimentos/${p.id}`,
    titulo: p.titulo,
    subtitulo: p.cliente_origem ?? "",
    createdAt: p.created_at,
    busca: normalizar(
      [p.titulo, p.cliente_origem, p.responsavel_email, p.criado_por_email].filter(Boolean).join(" "),
    ),
  }));

  // Mirrors what poc-planner/index.html's own switchProject() does to its localStorage (set the
  // active-project pointer, force that project's saved view back to "dashboard") before handing
  // off to the iframe route -- Home has no handle into the already-mounted iframe, only into the
  // same-origin localStorage it reads on its next load.
  function abrirRascunho(id: string) {
    try {
      localStorage.setItem(PLANNER_ACTIVE_PROJECT_KEY, id);
      const raw = localStorage.getItem(plannerProjectKey(id));
      if (raw) {
        const projeto = JSON.parse(raw);
        projeto.view = "dashboard";
        localStorage.setItem(plannerProjectKey(id), JSON.stringify(projeto));
      }
    } catch {
      // localStorage indisponível ou corrompido: ainda assim navega, o planejador cai no fallback dele.
    }
    navigate("/planejar");
  }

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
        <Link to="/planejar" className="home-action home-action-primary">
          <Icon name="plus" />
          <div>
            <strong>{t("home.actionPlanejar")}</strong>
            <span>{t("home.actionPlanejarDesc")}</span>
          </div>
        </Link>
        <Link to="/rfis/novo" className="home-action home-action-rfi">
          <Icon name="eye" />
          <div>
            <strong>{t("home.analisarRfi")}</strong>
            <span>{t("home.actionRfiDesc")}</span>
          </div>
        </Link>
        <Link to="/procedimentos" className="home-action home-action-procedimentos">
          <Icon name="book" />
          <div>
            <strong>{t("nav.procedimentos")}</strong>
            <span>{t("home.actionProcedimentosDesc")}</span>
          </div>
        </Link>
        <Link to="/licitacoes" className="home-action home-action-licitacoes">
          <Icon name="broadcast" />
          <div>
            <strong>
              {t("home.actionLicitacoes")} <span className="beta-tag">{t("licitacoes.beta")}</span>
            </strong>
            <span>{t("home.actionLicitacoesDesc")}</span>
          </div>
        </Link>
      </div>

      <div className="home-history-grid">
        <HistoryCard
          titulo={t("home.recentesPocs")}
          vazio={t("pocs.nenhumaPoc")}
          verTodosHref="/pocs"
          verTodosLabel={t("home.verTodasPocs")}
          carregando={pocs === null}
          itens={pocsOrdenados}
        />
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
          verTodosHref="/procedimentos"
          verTodosLabel={t("home.verProcedimentos")}
          carregando={procedimentos === null}
          itens={procedimentosOrdenados}
        />
        <DraftsCard itens={rascunhos} onAbrir={abrirRascunho} />
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
            <Link to="/licitacoes" className="licitacao-row-main">
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
        <Link to="/licitacoes" className="history-row-all">
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

// Local-only counterpart to HistoryCard: rows come from the planner's own localStorage (see
// lerRascunhosLocais above), not from the server, so there's no "carregando"/erro state and no
// href -- opening one needs a localStorage write first (abrirRascunho), not a plain navigation.
function DraftsCard({ itens, onAbrir }: { itens: RascunhoLocal[]; onAbrir: (id: string) => void }) {
  const { t } = useLanguage();

  return (
    <div className="card home-history-card">
      <h3>
        <Icon name="folder" /> {t("home.rascunhosLocais")}
      </h3>
      <p className="muted home-drafts-desc">{t("home.rascunhosLocaisDesc")}</p>
      {itens.length === 0 && <p className="empty-state">{t("home.nenhumRascunho")}</p>}
      {itens.map((it) => (
        <button key={it.id} type="button" className="history-row history-row-button" onClick={() => onAbrir(it.id)}>
          <div>
            <div className="history-row-title">{it.titulo}</div>
            {it.updatedAt && <div className="history-row-sub">{new Date(it.updatedAt).toLocaleDateString()}</div>}
          </div>
          <Icon name="chevronR" />
        </button>
      ))}
    </div>
  );
}

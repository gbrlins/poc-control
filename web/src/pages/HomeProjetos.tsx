import { useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { PocListItem } from "@/api";
import { Lang, useLanguage } from "@/i18n";
import { traduzirMensagemServidor } from "@/mensagensServidor";
import { Icon } from "@/Icon";
import {
  deixarImportacaoPendente,
  listarProjetosLocais,
  removerProjetoLocal,
} from "@/features/planejar-poc/plannerStore";

interface ProjetoRow {
  key: string;
  nome: string;
  cliente: string;
  // Planner project id (this browser only) / server PoC id; a row can have either or both
  // (state.pocControlId links them -- the planner's "Habilitar execução").
  localId: string | null;
  pocId: string | null;
  atualizadoEm: number;
  progresso: string | null;
  responsavel: string;
  modificadoPor: string;
  revisao: number;
}

type SortKey = "nome" | "cliente" | "etapa" | "data";

// One list for both phases: every planner project in this browser (linked ones included -- that
// is what makes the planning phase reachable again after "Habilitar execução") plus every server
// PoC that has no local project here (uploaded directly, or planned in another browser).
function montarLinhas(pocs: PocListItem[], semNome: string, lang: Lang): ProjetoRow[] {
  const locais = listarProjetosLocais();
  const pocsPorId = new Map(pocs.map((p) => [p.id, p]));
  const vinculados = new Set<string>();
  const linhas: ProjetoRow[] = locais.map((l) => {
    const poc = l.pocId ? pocsPorId.get(l.pocId) : undefined;
    if (poc) vinculados.add(poc.id);
    return {
      key: `local-${l.id}`,
      nome: l.nome || poc?.titulo || semNome,
      cliente: l.cliente || poc?.cliente || "",
      localId: l.id,
      pocId: poc ? poc.id : null,
      atualizadoEm: l.atualizadoEm,
      progresso: poc ? `${poc.itens_concluidos}/${poc.total_itens}` : null,
      responsavel: poc?.responsavel_email ?? "",
      modificadoPor: l.modificadoPor,
      revisao: l.revisao,
    };
  });
  for (const poc of pocs) {
    if (vinculados.has(poc.id)) continue;
    linhas.push({
      key: `poc-${poc.id}`,
      nome: traduzirMensagemServidor(poc.titulo, lang),
      cliente: poc.cliente,
      localId: null,
      pocId: poc.id,
      atualizadoEm: new Date(poc.created_at).getTime(),
      progresso: `${poc.itens_concluidos}/${poc.total_itens}`,
      responsavel: poc.responsavel_email ?? "",
      modificadoPor: "",
      revisao: 0,
    });
  }
  return linhas;
}

export function ProjetosCard({ pocs }: { pocs: PocListItem[] | null }) {
  const { t, lang } = useLanguage();
  const navigate = useNavigate();
  const fileRef = useRef<HTMLInputElement>(null);
  // Re-read on every mount (coming back from /plan) and whenever a draft is deleted.
  const [versao, setVersao] = useState(0);
  const [busca, setBusca] = useState("");
  const [ordem, setOrdem] = useState<{ chave: SortKey; asc: boolean }>({ chave: "data", asc: false });
  const [erro, setErro] = useState<string | null>(null);

  const linhas = useMemo(
    () => montarLinhas(pocs ?? [], t("home.rascunhoSemNome"), lang),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [pocs, versao, lang],
  );

  const termo = busca.trim().toLowerCase();
  const filtradas = termo
    ? linhas.filter((l) => [l.nome, l.cliente, l.responsavel, l.modificadoPor].join(" ").toLowerCase().includes(termo))
    : linhas;
  const etapa = (l: ProjetoRow) => (l.pocId ? 1 : 0);
  const ordenadas = [...filtradas].sort((a, b) => {
    let c = 0;
    if (ordem.chave === "nome") c = a.nome.localeCompare(b.nome);
    else if (ordem.chave === "cliente") c = a.cliente.localeCompare(b.cliente);
    else if (ordem.chave === "etapa") c = etapa(a) - etapa(b);
    else c = a.atualizadoEm - b.atualizadoEm;
    return ordem.asc ? c : -c;
  });

  function ordenarPor(chave: SortKey) {
    setOrdem((o) => (o.chave === chave ? { chave, asc: !o.asc } : { chave, asc: chave !== "data" }));
  }
  const seta = (chave: SortKey) => (ordem.chave === chave ? (ordem.asc ? " ▲" : " ▼") : "");

  function excluirRascunho(l: ProjetoRow) {
    if (!l.localId || l.pocId) return;
    if (!window.confirm(t("home.confirmarExcluirProjeto"))) return;
    removerProjetoLocal(l.localId);
    setVersao((v) => v + 1);
  }

  // The planner reads a JSON file only through its own FileReader flow, which needs a user
  // gesture inside the iframe. So the shell reads the file, leaves the text in sessionStorage
  // (same origin as the iframe) and opens /plan?import=project, which the planner consumes once.
  function importarArquivo(arquivo: File | undefined) {
    if (!arquivo) return;
    setErro(null);
    arquivo.text().then((texto) => {
      try {
        const dados = JSON.parse(texto);
        if (!dados || typeof dados !== "object") throw new Error("invalid");
        deixarImportacaoPendente(texto);
      } catch {
        setErro(t("home.importarInvalido"));
        return;
      }
      navigate("/plan?import=project");
    });
    if (fileRef.current) fileRef.current.value = "";
  }

  return (
    <div className="card home-projetos-card">
      <div className="home-projetos-head">
        <div>
          <h3>
            <Icon name="folder" /> {t("home.projetosTitulo")}
          </h3>
          <p className="muted home-drafts-desc">{t("home.projetosDesc")}</p>
        </div>
        <div className="home-projetos-actions">
          <Link to="/plan?new=1" className="btn btn-primary">
            <Icon name="plus" /> {t("home.btnNovoProjeto")}
          </Link>
          <button type="button" className="btn btn-secondary" onClick={() => fileRef.current?.click()}>
            <Icon name="upload" /> {t("home.btnImportarProjeto")}
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".json,application/json"
            hidden
            onChange={(e) => importarArquivo(e.target.files?.[0])}
          />
          <Link to="/plan?import=doc" className="btn btn-secondary">
            <Icon name="upload" /> {t("home.btnImportarDocumento")}
          </Link>
          <Link to="/plan?view=library" className="btn btn-secondary">
            <Icon name="book" /> {t("home.btnBiblioteca")}
          </Link>
        </div>
      </div>
      {erro && <p className="alert alert-error">{erro}</p>}
      {pocs === null ? (
        <p className="muted">{t("common.carregando")}</p>
      ) : (
        <>
          <input
            className="input history-search"
            type="text"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            placeholder={t("home.projetosBusca")}
          />
          {ordenadas.length === 0 ? (
            <p className="empty-state">{termo ? t("home.buscaSemResultado") : t("home.projetosVazio")}</p>
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <SortTh onClick={() => ordenarPor("nome")}>
                      {t("home.colProjeto")}
                      {seta("nome")}
                    </SortTh>
                    <SortTh onClick={() => ordenarPor("cliente")}>
                      {t("home.colCliente")}
                      {seta("cliente")}
                    </SortTh>
                    <SortTh onClick={() => ordenarPor("etapa")}>
                      {t("home.colEtapa")}
                      {seta("etapa")}
                    </SortTh>
                    <SortTh onClick={() => ordenarPor("data")}>
                      {t("home.colAtualizado")}
                      {seta("data")}
                    </SortTh>
                    <th>{t("home.colModificadoPor")}</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {ordenadas.map((l) => (
                    <tr key={l.key}>
                      <td>
                        <strong>{l.nome}</strong>
                      </td>
                      <td>{l.cliente || "—"}</td>
                      <td>
                        <span className={l.pocId ? "badge badge-ok" : "badge"}>
                          {l.pocId ? t("home.etapaExecucao") : t("home.etapaPlanejamento")}
                        </span>
                        {l.progresso && <span className="muted"> {l.progresso}</span>}
                      </td>
                      <td>{l.atualizadoEm ? new Date(l.atualizadoEm).toLocaleString() : "—"}</td>
                      <td>
                        {l.modificadoPor || "—"}
                        {l.revisao > 0 && <span className="muted"> v{l.revisao}</span>}
                      </td>
                      <td className="home-projetos-row-actions">
                        {l.localId && !l.pocId && (
                          <Link to={`/plan?open=${encodeURIComponent(l.localId)}`} className="btn btn-secondary">
                            <Icon name="layout" /> {t("home.acaoPlanejar")}
                          </Link>
                        )}
                        {l.localId && l.pocId && (
                          // Once execution is enabled the plan is shown read-only (edit stays one click away in the planner's banner).
                          <Link
                            to={`/plan?open=${encodeURIComponent(l.localId)}&readonly=1`}
                            className="btn btn-secondary"
                            title={t("home.acaoVerPlanoDica")}
                          >
                            <Icon name="eye" /> {t("home.acaoVerPlano")}
                          </Link>
                        )}
                        {l.pocId && (
                          <Link to={`/pocs/${l.pocId}`} className="btn btn-secondary">
                            <Icon name="activity" /> {t("home.acaoExecutar")}
                          </Link>
                        )}
                        {l.localId && !l.pocId && (
                          // No server execution yet: the planner (which strips credentials and builds the payload) creates it and opens it.
                          <button
                            type="button"
                            className="btn btn-primary"
                            title={t("home.acaoExecutarCriarDica")}
                            onClick={() => {
                              if (window.confirm(t("home.confirmarExecucao"))) navigate(`/plan?open=${encodeURIComponent(l.localId!)}&enable=1`);
                            }}
                          >
                            <Icon name="activity" /> {t("home.acaoExecutar")}
                          </button>
                        )}
                        {l.localId && !l.pocId && (
                          <button
                            type="button"
                            className="btn btn-secondary"
                            title={t("home.acaoExcluir")}
                            aria-label={t("home.acaoExcluir")}
                            onClick={() => excluirRascunho(l)}
                          >
                            <Icon name="trash" />
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <Link to="/pocs" className="history-row-all">
            {t("home.verTodasPocs")}
          </Link>
        </>
      )}
    </div>
  );
}

function SortTh({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <th onClick={onClick} style={{ cursor: "pointer", userSelect: "none" }}>
      {children}
    </th>
  );
}

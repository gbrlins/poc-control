import { FormEvent, useEffect, useState } from "react";
import { useCurrentUser } from "@/auth";
import { api, LicitacaoOut, TermoBuscaOut } from "@/api";
import { useLanguage } from "@/i18n";

function formatarValor(valor: number | null): string {
  if (valor === null) return "—";
  return valor.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export function Licitacoes() {
  const { t } = useLanguage();
  const user = useCurrentUser();
  const [itens, setItens] = useState<LicitacaoOut[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [atualizando, setAtualizando] = useState(false);
  const [mensagem, setMensagem] = useState<string | null>(null);

  function carregar() {
    api
      .listarLicitacoes()
      .then(setItens)
      .catch(() => setErro(t("licitacoes.erroCarregar")));
  }

  useEffect(carregar, []);

  async function atualizar() {
    setAtualizando(true);
    setMensagem(null);
    setErro(null);
    try {
      const resultado = await api.atualizarLicitacoes();
      setMensagem(t("licitacoes.atualizadoMsg").replace("{n}", String(resultado.novas)));
      carregar();
    } catch {
      setErro(t("licitacoes.erroAtualizar"));
    } finally {
      setAtualizando(false);
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1>
          {t("licitacoes.titulo")} <span className="beta-tag">{t("licitacoes.beta")}</span>
        </h1>
        <button type="button" className="btn btn-primary" onClick={atualizar} disabled={atualizando}>
          {atualizando ? t("licitacoes.atualizando") : t("licitacoes.atualizarAgora")}
        </button>
      </div>
      <p className="page-subtitle">{t("licitacoes.subtitulo")}</p>

      {mensagem && <p className="alert alert-success">{mensagem}</p>}
      {erro && <p className="alert alert-error">{erro}</p>}

      {itens === null && !erro && <p className="muted">{t("common.carregando")}</p>}
      {itens && itens.length === 0 && <div className="card empty-state">{t("licitacoes.nenhuma")}</div>}

      {itens && itens.length > 0 && (
        <div className="card">
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>{t("licitacoes.colObjeto")}</th>
                  <th>{t("licitacoes.colOrgao")}</th>
                  <th>{t("licitacoes.colModalidade")}</th>
                  <th>{t("licitacoes.colValor")}</th>
                  <th>{t("licitacoes.colData")}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {itens.map((lic) => (
                  <tr key={lic.id}>
                    <td>
                      {lic.objeto}
                      {lic.termos_encontrados.length > 0 && (
                        <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
                          {t("licitacoes.termosLabel")} {lic.termos_encontrados.join(", ")}
                        </div>
                      )}
                    </td>
                    <td className="muted">
                      {lic.orgao_nome}
                      {lic.uf ? ` · ${lic.uf}` : ""}
                    </td>
                    <td className="muted">{lic.modalidade_nome ?? "—"}</td>
                    <td className="muted">{formatarValor(lic.valor_estimado)}</td>
                    <td className="muted">{new Date(lic.data_publicacao).toLocaleDateString()}</td>
                    <td>
                      <a href={lic.link_pncp} target="_blank" rel="noreferrer" className="btn btn-secondary">
                        {t("licitacoes.verEdital")}
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {user.is_admin && <TermosBusca />}
    </div>
  );
}

function TermosBusca() {
  const { t } = useLanguage();
  const [aberto, setAberto] = useState(false);
  const [termos, setTermos] = useState<TermoBuscaOut[] | null>(null);
  const [novoTermo, setNovoTermo] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  function carregar() {
    api
      .listarTermosBusca()
      .then(setTermos)
      .catch(() => setErro(t("licitacoes.erroCarregarTermos")));
  }

  // Carrega só quando aberto pela primeira vez -- a maior parte do tempo ninguém abre este
  // painel, não faz sentido pedir a lista de termos toda vez que a página carrega.
  useEffect(() => {
    if (aberto && termos === null) carregar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aberto]);

  async function adicionar(e: FormEvent) {
    e.preventDefault();
    const termo = novoTermo.trim();
    if (!termo) return;
    setEnviando(true);
    setErro(null);
    try {
      await api.criarTermoBusca(termo);
      setNovoTermo("");
      carregar();
    } catch {
      setErro(t("licitacoes.erroCriarTermo"));
    } finally {
      setEnviando(false);
    }
  }

  async function alternar(id: string) {
    await api.alternarTermoBusca(id);
    carregar();
  }

  async function remover(id: string) {
    await api.removerTermoBusca(id);
    carregar();
  }

  return (
    <div className="card" style={{ marginTop: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h3 style={{ margin: 0 }}>{t("licitacoes.termosTitulo")}</h3>
        <button type="button" className="btn btn-secondary" onClick={() => setAberto((v) => !v)}>
          {aberto ? t("common.fechar") : t("licitacoes.gerenciarTermos")}
        </button>
      </div>

      {aberto && (
        <div style={{ marginTop: 14 }}>
          <p className="muted">{t("licitacoes.termosDesc")}</p>
          {erro && <p className="alert alert-error">{erro}</p>}
          {termos === null && <p className="muted">{t("common.carregando")}</p>}
          {termos && (
            <ul style={{ margin: "0 0 12px", paddingLeft: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 6 }}>
              {termos.map((termo) => (
                <li key={termo.id} style={{ display: "flex", gap: 12, alignItems: "center" }}>
                  <span className={`badge ${termo.ativo ? "badge-verde" : "badge-muted"}`}>
                    {termo.categoria_codigo ?? "—"}
                  </span>
                  <span style={{ flex: 1 }}>{termo.termo}</span>
                  <button type="button" className="btn btn-secondary" onClick={() => alternar(termo.id)}>
                    {termo.ativo ? t("licitacoes.desativar") : t("licitacoes.ativar")}
                  </button>
                  <button type="button" className="btn btn-secondary" onClick={() => remover(termo.id)}>
                    {t("licitacoes.removerTermo")}
                  </button>
                </li>
              ))}
            </ul>
          )}
          <form onSubmit={adicionar} style={{ display: "flex", gap: 8 }}>
            <input
              className="input"
              value={novoTermo}
              onChange={(e) => setNovoTermo(e.target.value)}
              placeholder={t("licitacoes.novoTermoPlaceholder")}
            />
            <button type="submit" className="btn btn-secondary" disabled={enviando}>
              {t("licitacoes.adicionarTermo")}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}

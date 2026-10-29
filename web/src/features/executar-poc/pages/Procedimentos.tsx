import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, ProcedimentoListItem } from "@/api";
import { CODIGOS_CATEGORIA, rotuloCategoria } from "@/categorias";
import { useLanguage } from "@/i18n";

export function Procedimentos() {
  const { t, lang } = useLanguage();
  const [itens, setItens] = useState<ProcedimentoListItem[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [filtroCategorias, setFiltroCategorias] = useState<Set<string>>(new Set());

  useEffect(() => {
    api
      .listarProcedimentos()
      .then(setItens)
      .catch(() => setErro(t("procedimentos.erroCarregar")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function alternarFiltro(codigo: string) {
    setFiltroCategorias((atual) => {
      const novo = new Set(atual);
      if (novo.has(codigo)) novo.delete(codigo);
      else novo.add(codigo);
      return novo;
    });
  }

  const filtrados = useMemo(() => {
    if (!itens) return [];
    if (filtroCategorias.size === 0) return itens;
    return itens.filter((p) => p.categorias.some((c) => filtroCategorias.has(c)));
  }, [itens, filtroCategorias]);

  return (
    <div>
      <div className="page-header">
        <h1>{t("procedimentos.titulo")}</h1>
        <Link to="/procedimentos/novo" className="btn btn-primary">
          {t("procedimentos.novoProcedimento")}
        </Link>
      </div>

      {erro && <p className="alert alert-error">{erro}</p>}
      {itens === null && !erro && <p className="muted">{t("common.carregando")}</p>}

      {itens && itens.length > 0 && (
        <div className="card" style={{ marginBottom: 20 }}>
          <label style={{ display: "block", marginBottom: 8 }}>{t("procedimentos.filtroCategoria")}</label>
          <div className="chip-filter-group">
            {CODIGOS_CATEGORIA.map((codigo) => (
              <button
                key={codigo}
                type="button"
                className={`chip-filter${filtroCategorias.has(codigo) ? " active" : ""}`}
                onClick={() => alternarFiltro(codigo)}
              >
                {codigo} — {rotuloCategoria(codigo, lang)}
              </button>
            ))}
          </div>
        </div>
      )}

      {itens && itens.length === 0 && <div className="card empty-state">{t("procedimentos.nenhum")}</div>}

      {itens && itens.length > 0 && (
        <div className="card">
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>{t("procedimentos.colTitulo")}</th>
                  <th>{t("procedimentos.colCategorias")}</th>
                  <th>{t("procedimentos.colTags")}</th>
                  <th>{t("procedimentos.colCliente")}</th>
                  <th>{t("procedimentos.colStatus")}</th>
                  <th>{t("procedimentos.colVersao")}</th>
                  <th>{t("procedimentos.colDono")}</th>
                </tr>
              </thead>
              <tbody>
                {filtrados.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <Link to={`/procedimentos/${p.id}`}>{p.titulo}</Link>
                    </td>
                    <td className="muted">
                      {p.categorias.length > 0
                        ? p.categorias.map((c) => (
                            <span key={c} className="chip" style={{ marginRight: 4 }} title={rotuloCategoria(c, lang)}>
                              {c}
                            </span>
                          ))
                        : "—"}
                    </td>
                    <td className="muted">{p.tags.join(", ") || "—"}</td>
                    <td>{p.cliente_origem ?? "—"}</td>
                    <td>
                      <span className={`badge badge-${p.status}`}>{p.status}</span>
                    </td>
                    <td>{p.versao}</td>
                    <td className="muted">{p.responsavel_email ?? t("procedimentos.semDono")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

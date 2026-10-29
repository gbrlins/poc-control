import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, RfiListItem } from "@/api";
import { useLanguage } from "@/i18n";

export function Rfis() {
  const { t } = useLanguage();
  const [itens, setItens] = useState<RfiListItem[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [filtroUsuario, setFiltroUsuario] = useState("");
  const [filtroDe, setFiltroDe] = useState("");
  const [filtroAte, setFiltroAte] = useState("");

  const STATUS_LABEL: Record<string, string> = {
    extraindo: t("rfis.extraindo"),
    pronto: t("rfis.pronto"),
    erro: t("rfis.erroExtracao"),
  };

  useEffect(() => {
    api
      .listarRfis()
      .then(setItens)
      .catch(() => setErro(t("rfis.erroCarregar")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const usuarios = useMemo(() => {
    const vistos = new Set<string>();
    (itens ?? []).forEach((r) => vistos.add(r.criado_por_email));
    return [...vistos].sort();
  }, [itens]);

  const filtrados = useMemo(() => {
    if (!itens) return [];
    return itens.filter((r) => {
      if (filtroUsuario && r.criado_por_email !== filtroUsuario) return false;
      const data = r.created_at.slice(0, 10);
      if (filtroDe && data < filtroDe) return false;
      if (filtroAte && data > filtroAte) return false;
      return true;
    });
  }, [itens, filtroUsuario, filtroDe, filtroAte]);

  return (
    <div>
      <div className="page-header">
        <h1>{t("rfis.titulo")}</h1>
        <Link to="/rfis/novo" className="btn btn-primary">
          {t("rfis.novoRfi")}
        </Link>
      </div>

      {erro && <p className="alert alert-error">{erro}</p>}
      {itens === null && !erro && <p className="muted">{t("common.carregando")}</p>}

      {itens && itens.length > 0 && (
        <div className="card" style={{ marginBottom: 20 }}>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
            <div className="field" style={{ minWidth: 200 }}>
              <label>{t("rfis.filtroUsuario")}</label>
              <select className="input" value={filtroUsuario} onChange={(e) => setFiltroUsuario(e.target.value)}>
                <option value="">{t("rfis.filtroTodos")}</option>
                {usuarios.map((u) => (
                  <option key={u} value={u}>
                    {u}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>{t("rfis.filtroDe")}</label>
              <input
                type="date"
                className="input"
                value={filtroDe}
                onChange={(e) => setFiltroDe(e.target.value)}
              />
            </div>
            <div className="field">
              <label>{t("rfis.filtroAte")}</label>
              <input
                type="date"
                className="input"
                value={filtroAte}
                onChange={(e) => setFiltroAte(e.target.value)}
              />
            </div>
          </div>
        </div>
      )}

      {itens && itens.length === 0 && <div className="card empty-state">{t("rfis.nenhumRfi")}</div>}

      {itens && itens.length > 0 && (
        <div className="card">
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>{t("rfis.colTitulo")}</th>
                  <th>{t("rfis.colProcesso")}</th>
                  <th>{t("rfis.colCriadoPor")}</th>
                  <th>{t("rfis.colDono")}</th>
                  <th>{t("rfis.colData")}</th>
                  <th>{t("rfis.colStatus")}</th>
                  <th>{t("rfis.colProgresso")}</th>
                </tr>
              </thead>
              <tbody>
                {filtrados.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <Link to={`/rfis/${r.id}`}>{r.titulo || t("rfis.semTitulo")}</Link>
                      {r.orgao && <div className="muted" style={{ fontSize: 12 }}>{r.orgao}</div>}
                    </td>
                    <td className="muted">{r.numero_processo || "—"}</td>
                    <td className="muted">{r.criado_por_email}</td>
                    <td className="muted">{r.responsavel_email ?? t("rfis.semDono")}</td>
                    <td className="muted">{new Date(r.created_at).toLocaleDateString()}</td>
                    <td>
                      <span className={`badge badge-${r.status_extracao === "pronto" ? "muted" : r.status_extracao === "erro" ? "vermelho" : "info"}`}>
                        {STATUS_LABEL[r.status_extracao] ?? r.status_extracao}
                      </span>
                    </td>
                    <td className="muted">
                      {r.total_itens > 0 ? `${r.itens_avaliados}/${r.total_itens}` : "—"}
                    </td>
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

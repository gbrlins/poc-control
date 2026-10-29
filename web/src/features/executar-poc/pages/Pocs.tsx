import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, PocListItem } from "@/api";
import { useLanguage } from "@/i18n";

function pct(poc: PocListItem) {
  if (poc.total_itens === 0) return 0;
  return Math.round((poc.itens_concluidos / poc.total_itens) * 100);
}

export function Pocs() {
  const { t } = useLanguage();
  const [itens, setItens] = useState<PocListItem[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const STATUS_LABEL: Record<string, string> = {
    ativa: t("pocs.statusAtiva"),
    concluida: t("pocs.statusConcluida"),
    suspensa: t("pocs.statusSuspensa"),
  };

  useEffect(() => {
    api
      .listarPocs()
      .then(setItens)
      .catch(() => setErro(t("pocs.erroCarregar")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div>
      <div className="page-header">
        <h1>{t("pocs.titulo")}</h1>
        <Link to="/pocs/novo" className="btn btn-primary">
          {t("pocs.novaPoc")}
        </Link>
      </div>

      {erro && <p className="alert alert-error">{erro}</p>}
      {itens === null && !erro && <p className="muted">{t("common.carregando")}</p>}

      {itens && itens.length === 0 && <div className="card empty-state">{t("pocs.nenhumaPoc")}</div>}

      {itens && itens.length > 0 && (
        <div className="card">
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>{t("pocs.colTitulo")}</th>
                  <th>{t("pocs.colCliente")}</th>
                  <th>{t("pocs.colStatus")}</th>
                  <th>{t("pocs.colExtracao")}</th>
                  <th>{t("pocs.colProgresso")}</th>
                  <th>{t("pocs.colDono")}</th>
                </tr>
              </thead>
              <tbody>
                {itens.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <Link to={`/pocs/${p.id}`}>{p.titulo}</Link>
                    </td>
                    <td>{p.cliente}</td>
                    <td>
                      <span className="badge badge-muted">{STATUS_LABEL[p.status] ?? p.status}</span>
                    </td>
                    <td>
                      {p.status_extracao === "extraindo" && (
                        <span className="badge badge-info">{t("pocs.extraindo")}</span>
                      )}
                      {p.status_extracao === "erro" && (
                        <span className="badge badge-vermelho">{t("pocs.erroExtracao")}</span>
                      )}
                      {p.status_extracao === "pronto" && <span className="muted">—</span>}
                    </td>
                    <td className="muted">
                      {p.total_itens > 0 ? `${pct(p)}% (${p.itens_concluidos}/${p.total_itens})` : "—"}
                    </td>
                    <td className="muted">{p.responsavel_email ?? t("pocs.semDono")}</td>
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

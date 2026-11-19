import { Link } from "react-router-dom";
import { PocListItem } from "@/api";
import { useLanguage } from "@/i18n";
import { traduzirMensagemServidor } from "@/mensagensServidor";
import { rotuloCategoria } from "@/categorias";

function pct(poc: PocListItem) {
  if (poc.total_itens === 0) return 0;
  return Math.round((poc.itens_concluidos / poc.total_itens) * 100);
}

// The full, filterable table at /pocs (see Pocs.tsx). Home's hub shows its own compact
// "PoCs recentes" list instead (pages/Home.tsx's HistoryCard) -- this one used to also be
// embedded there before the hub redesign, hence PocFiltros.tsx living alongside it.
export function PocsTable({ itens }: { itens: PocListItem[] }) {
  const { t, lang } = useLanguage();

  const STATUS_LABEL: Record<string, string> = {
    ativa: t("pocs.statusAtiva"),
    concluida: t("pocs.statusConcluida"),
    suspensa: t("pocs.statusSuspensa"),
  };

  if (itens.length === 0) {
    return <div className="card empty-state">{t("pocs.nenhumaPoc")}</div>;
  }

  return (
    <div className="card">
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>{t("pocs.colTitulo")}</th>
              <th>{t("pocs.colCliente")}</th>
              <th>{t("home.filtroProduto")}</th>
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
                  <Link to={`/pocs/${p.id}`}>{traduzirMensagemServidor(p.titulo, lang)}</Link>
                </td>
                <td>{p.cliente}</td>
                <td className="muted">
                  {p.produtos.length > 0 ? p.produtos.map((c) => rotuloCategoria(c, lang)).join(", ") : "—"}
                </td>
                <td>
                  <span className="badge badge-muted">{STATUS_LABEL[p.status] ?? p.status}</span>
                </td>
                <td>
                  {p.status_extracao === "extraindo" && <span className="badge badge-info">{t("pocs.extraindo")}</span>}
                  {p.status_extracao === "erro" && <span className="badge badge-vermelho">{t("pocs.erroExtracao")}</span>}
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
  );
}

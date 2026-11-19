import { useState } from "react";
import { Fonte } from "@/api";
import { useLanguage } from "@/i18n";

type Chave = "titulo" | "url";

// The sources of ONE evaluation, shown openly (not as a row of domain names): full URL, sortable by
// either column, with a Copy button beside each. The page-level table at the bottom of the RFI
// aggregates the same URLs across every item.
export function FontesItemTable({ fontes, complementares }: { fontes: Fonte[]; complementares: boolean }) {
  const { t } = useLanguage();
  const [ordem, setOrdem] = useState<{ chave: Chave; asc: boolean } | null>(null);
  const [copiado, setCopiado] = useState<string | null>(null);

  const linhas = ordem
    ? [...fontes].sort((a, b) => {
        const c = (a[ordem.chave] ?? "").localeCompare(b[ordem.chave] ?? "", undefined, { sensitivity: "base" });
        return ordem.asc ? c : -c;
      })
    : fontes;

  function ordenarPor(chave: Chave) {
    setOrdem((o) => (o && o.chave === chave ? { chave, asc: !o.asc } : { chave, asc: true }));
  }
  const seta = (chave: Chave) => (ordem?.chave === chave ? (ordem.asc ? " ▲" : " ▼") : "");

  async function copiar(texto: string, marca: string) {
    try {
      await navigator.clipboard.writeText(texto);
      setCopiado(marca);
      window.setTimeout(() => setCopiado((atual) => (atual === marca ? null : atual)), 2000);
    } catch {
      // clipboard unavailable (insecure context / permissions)
    }
  }

  return (
    <div style={{ margin: "8px 0 12px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <span className="muted">
          {complementares ? t("rfiItemRow.fontesComplementares") : t("rfiItemRow.fontes")} ({fontes.length})
        </span>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => copiar(linhas.map((f) => f.url).join("\n"), "todas")}
        >
          {copiado === "todas" ? t("rfiDetail.copiado") : t("rfiDetail.copiarTodas")}
        </button>
      </div>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th onClick={() => ordenarPor("titulo")} style={{ cursor: "pointer", userSelect: "none" }}>
                {t("rfiDetail.fontesColFonte")}
                {seta("titulo")}
              </th>
              <th onClick={() => ordenarPor("url")} style={{ cursor: "pointer", userSelect: "none" }}>
                URL{seta("url")}
              </th>
              <th />
            </tr>
          </thead>
          <tbody>
            {linhas.map((f) => (
              <tr key={f.url}>
                <td style={{ whiteSpace: "nowrap" }}>{f.titulo}</td>
                <td style={{ wordBreak: "break-all" }}>
                  <a href={f.url} target="_blank" rel="noreferrer">
                    {f.url}
                  </a>
                </td>
                <td>
                  <button type="button" className="btn btn-secondary" onClick={() => copiar(f.url, f.url)}>
                    {copiado === f.url ? t("rfiDetail.copiado") : t("rfiDetail.copiar")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

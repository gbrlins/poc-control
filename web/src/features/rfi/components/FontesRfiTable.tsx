import { useMemo, useState } from "react";
import { RfiItemOut } from "@/api";
import { useLanguage } from "@/i18n";

interface LinhaFonte {
  url: string;
  titulo: string;
  itens: string[];
}

type Chave = "titulo" | "url" | "itens";

// Every distinct source URL cited across the RFI's items, shown openly as a table instead of only
// as links inside each item. The stored URL is the resolved one (api/app/url_real.py turns Google's
// grounding redirects into the real page address when the item is evaluated).
export function FontesRfiTable({ itens }: { itens: RfiItemOut[] }) {
  const { t } = useLanguage();
  const [ordem, setOrdem] = useState<{ chave: Chave; asc: boolean }>({ chave: "itens", asc: false });
  const [copiado, setCopiado] = useState<string | null>(null);

  const linhas = useMemo(() => {
    const porUrl = new Map<string, LinhaFonte>();
    for (const item of itens) {
      for (const f of item.fontes) {
        const atual = porUrl.get(f.url) ?? { url: f.url, titulo: f.titulo || f.url, itens: [] };
        if (!atual.itens.includes(item.codigo)) atual.itens.push(item.codigo);
        porUrl.set(f.url, atual);
      }
    }
    return [...porUrl.values()];
  }, [itens]);

  if (linhas.length === 0) return null;

  const ordenadas = [...linhas].sort((a, b) => {
    const c =
      ordem.chave === "itens"
        ? a.itens.length - b.itens.length
        : a[ordem.chave].localeCompare(b[ordem.chave], undefined, { sensitivity: "base" });
    return ordem.asc ? c : -c;
  });

  function ordenarPor(chave: Chave) {
    setOrdem((o) => (o.chave === chave ? { chave, asc: !o.asc } : { chave, asc: chave !== "itens" }));
  }
  const seta = (chave: Chave) => (ordem.chave === chave ? (ordem.asc ? " ▲" : " ▼") : "");

  async function copiar(texto: string, marca: string) {
    try {
      await navigator.clipboard.writeText(texto);
      setCopiado(marca);
      window.setTimeout(() => setCopiado((atual) => (atual === marca ? null : atual)), 2000);
    } catch {
      // clipboard blocked (insecure context / permissions): nothing to confirm.
    }
  }

  return (
    <div className="card" style={{ marginTop: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <h3 style={{ margin: 0 }}>
          {t("rfiDetail.fontesTitulo")} <span className="muted">({linhas.length})</span>
        </h3>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => copiar(ordenadas.map((l) => l.url).join("\n"), "todas")}
        >
          {copiado === "todas" ? t("rfiDetail.copiado") : t("rfiDetail.copiarTodas")}
        </button>
      </div>
      <div className="table-wrap" style={{ marginTop: 12 }}>
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
              <th onClick={() => ordenarPor("itens")} style={{ cursor: "pointer", userSelect: "none" }}>
                {t("rfiDetail.fontesColItens")}
                {seta("itens")}
              </th>
              <th />
            </tr>
          </thead>
          <tbody>
            {ordenadas.map((l) => (
              <tr key={l.url}>
                <td>{l.titulo}</td>
                <td style={{ wordBreak: "break-all" }}>
                  <a href={l.url} target="_blank" rel="noreferrer">
                    {l.url}
                  </a>
                </td>
                <td title={l.itens.join(", ")}>{l.itens.length}</td>
                <td>
                  <button type="button" className="btn btn-secondary" onClick={() => copiar(l.url, l.url)}>
                    {copiado === l.url ? t("rfiDetail.copiado") : t("rfiDetail.copiar")}
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

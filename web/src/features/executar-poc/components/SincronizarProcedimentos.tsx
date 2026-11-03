import { useEffect, useState } from "react";
import { api, ProcedimentoListItem, ResultadoSincronizacao } from "@/api";
import { useLanguage } from "@/i18n";
import { toggleInSet } from "@/toggleInSet";

type Aba = "baixar" | "enviar";

// Lado a lado com uma outra instância do poc-control (ex.: local <-> servidor de produção, ver
// app/sync/ no backend): baixar procedimentos selecionados do servidor pra cá, ou subir os daqui
// selecionados pro servidor (que só apaga localmente depois do servidor confirmar que salvou).
export function SincronizarProcedimentos({
  locais,
  onClose,
  onMudou,
}: {
  locais: ProcedimentoListItem[];
  onClose: () => void;
  onMudou: () => void;
}) {
  const { t } = useLanguage();
  const [aba, setAba] = useState<Aba>("baixar");
  const [remotos, setRemotos] = useState<ProcedimentoListItem[] | null>(null);
  const [erroRemotos, setErroRemotos] = useState<string | null>(null);
  const [selecionados, setSelecionados] = useState<Set<string>>(new Set());
  const [processando, setProcessando] = useState(false);
  const [resultados, setResultados] = useState<ResultadoSincronizacao[] | null>(null);

  useEffect(() => {
    if (aba !== "baixar" || remotos !== null) return;
    api
      .listarProcedimentosRemotos()
      .then(setRemotos)
      .catch(() => setErroRemotos(t("syncProcedimentos.erroListar")));
  }, [aba, remotos, t]);

  function mudarAba(nova: Aba) {
    setAba(nova);
    setSelecionados(new Set());
    setResultados(null);
  }

  const lista = aba === "baixar" ? remotos : locais;

  async function executar() {
    if (selecionados.size === 0) return;
    setProcessando(true);
    setResultados(null);
    try {
      const ids = [...selecionados];
      const resposta =
        aba === "baixar"
          ? await api.baixarProcedimentosDoServidor(ids)
          : await api.enviarProcedimentosParaServidor(ids);
      setResultados(resposta);
      setSelecionados(new Set());
      onMudou();
      if (aba === "baixar") setRemotos(null); // recarrega a lista remota (não precisa sumir dela, mas evita confusão de estado velho)
    } finally {
      setProcessando(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-janela" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 640 }}>
        <div className="page-header" style={{ marginBottom: 0 }}>
          <h2 style={{ margin: 0 }}>{t("syncProcedimentos.titulo")}</h2>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            {t("common.fechar")}
          </button>
        </div>

        <div className="field-toggle" style={{ marginTop: 12 }}>
          <button
            type="button"
            className={aba === "baixar" ? "field-toggle-btn active" : "field-toggle-btn"}
            onClick={() => mudarAba("baixar")}
          >
            {t("syncProcedimentos.baixar")}
          </button>
          <button
            type="button"
            className={aba === "enviar" ? "field-toggle-btn active" : "field-toggle-btn"}
            onClick={() => mudarAba("enviar")}
          >
            {t("syncProcedimentos.enviar")}
          </button>
        </div>

        {aba === "baixar" && erroRemotos && <p className="alert alert-error">{erroRemotos}</p>}
        {aba === "baixar" && remotos === null && !erroRemotos && <p className="muted">{t("common.carregando")}</p>}

        {lista && lista.length === 0 && <div className="empty-state">{t("syncProcedimentos.nenhum")}</div>}

        {lista && lista.length > 0 && (
          <ul style={{ margin: "12px 0", paddingLeft: 0, listStyle: "none", maxHeight: 320, overflowY: "auto" }}>
            {lista.map((p) => (
              <li key={p.id} style={{ display: "flex", gap: 10, alignItems: "center", padding: "4px 0" }}>
                <input
                  type="checkbox"
                  checked={selecionados.has(p.id)}
                  onChange={() => setSelecionados((atual) => toggleInSet(atual, p.id))}
                  disabled={processando}
                />
                <span style={{ flex: 1 }}>{p.titulo}</span>
                <span className="muted" style={{ fontSize: 12 }}>
                  {p.cliente_origem ?? "—"}
                </span>
                <span className={`badge badge-${p.status}`}>{p.status}</span>
              </li>
            ))}
          </ul>
        )}

        {resultados && (
          <ul style={{ margin: "0 0 12px", paddingLeft: 0, listStyle: "none" }}>
            {resultados.map((r) => (
              <li key={r.id} style={{ display: "flex", gap: 10, alignItems: "center", padding: "4px 0" }}>
                <span style={{ flex: 1 }}>{r.titulo}</span>
                {r.status === "erro" ? (
                  <span className="alert alert-error" style={{ padding: "2px 8px", margin: 0 }}>
                    {r.erro}
                  </span>
                ) : (
                  <span className="badge badge-validado">{t(`syncProcedimentos.status.${r.status}`)}</span>
                )}
              </li>
            ))}
          </ul>
        )}

        <button
          type="button"
          className="btn btn-primary"
          disabled={selecionados.size === 0 || processando}
          onClick={() => void executar()}
        >
          {processando
            ? t("common.enviando")
            : aba === "baixar"
              ? t("syncProcedimentos.baixarSelecionados").replace("{n}", String(selecionados.size))
              : t("syncProcedimentos.enviarSelecionados").replace("{n}", String(selecionados.size))}
        </button>
      </div>
    </div>
  );
}

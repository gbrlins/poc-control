import { useLanguage } from "@/i18n";

// Barra de progresso do envio de arquivos (XMLHttpRequest, ver api.ts::uploadComProgresso). Em 100% o corpo já subiu mas o servidor ainda
// grava os documentos e põe a análise na fila: a mensagem diz isso em vez de ficar parada em "100%".
export function ProgressoEnvio({ pct }: { pct: number }) {
  const { t } = useLanguage();
  const concluido = pct >= 100;
  return (
    <div role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} style={{ margin: "4px 0 12px" }}>
      <div style={{ height: 8, borderRadius: 99, background: "var(--gray-100)", overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${pct}%`, background: "var(--suse-base)", transition: "width 150ms" }} />
      </div>
      <p className="field-hint" style={{ marginTop: 4 }}>
        {concluido ? t("common.envioConcluidoFila") : `${t("common.enviandoArquivos")} ${pct}%`}
      </p>
    </div>
  );
}

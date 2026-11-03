// Faixa de "processando em segundo plano" com botão de cancelar -- extraída do bloco que já
// existia hardcoded em RfiDetail.tsx (fila de documentos: extração + avaliação) e agora também usada
// por PocDetail.tsx (fila de documentos: extração). Cada tela resolve sua própria mensagem de
// status (depende do namespace de i18n e das fases que ela tem — RFI tem "avaliando"/"reavaliando"
// além de "lendo", a PoC só tem "lendo"), este componente só desenha a faixa.
export function ProcessamentoEmLote({
  mensagemProcessando,
  statusLinha,
  cancelamentoSolicitado,
  rotuloCancelar,
  onCancelar,
}: {
  mensagemProcessando: string;
  statusLinha: string;
  cancelamentoSolicitado: boolean;
  rotuloCancelar: string;
  onCancelar: () => void;
}) {
  return (
    <div className="alert alert-warning" style={{ display: "flex", gap: 12, alignItems: "center" }}>
      <div style={{ flex: 1 }}>
        <div>{mensagemProcessando}</div>
        <div>
          <b>{statusLinha}</b>
        </div>
      </div>
      <button type="button" className="btn btn-secondary" disabled={cancelamentoSolicitado} onClick={onCancelar}>
        {rotuloCancelar}
      </button>
    </div>
  );
}

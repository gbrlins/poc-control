import { ChangeEvent } from "react";

// Seleção múltipla (clique ou arraste) + lista do que foi escolhido mas ainda não foi enviado --
// dá pra juntar vários arquivos em várias seleções/arrastadas e só então disparar o envio, em vez
// de subir no instante em que o primeiro lote é escolhido. Quem usa decide o que fazer com os
// arquivos (criarPoc/criarRfi na criação, adicionarDocumentos* num registro existente); este
// componente só cuida da escolha e da lista pendente. Extraído do que já existia hardcoded em
// RfiUpload.tsx e em RfiDocumentos (RfiDetail.tsx).
export function BatchDocumentUploader({
  files,
  onFilesChange,
  accept,
  disabled = false,
  selectLabel,
  removeLabel,
  newBadgeLabel,
}: {
  files: File[];
  onFilesChange: (files: File[]) => void;
  accept: string;
  disabled?: boolean;
  selectLabel: string;
  removeLabel: string;
  newBadgeLabel?: string;
}) {
  function adicionar(novos: File[]) {
    onFilesChange([
      ...files,
      ...novos.filter((n) => !files.some((p) => p.name === n.name && p.size === n.size)),
    ]);
  }

  function escolher(e: ChangeEvent<HTMLInputElement>) {
    adicionar(Array.from(e.target.files ?? []));
    e.target.value = "";
  }

  function soltar(e: React.DragEvent<HTMLLabelElement>) {
    e.preventDefault();
    if (disabled) return;
    adicionar(Array.from(e.dataTransfer.files ?? []));
  }

  function remover(index: number) {
    onFilesChange(files.filter((_, i) => i !== index));
  }

  return (
    <div>
      {files.length > 0 && (
        <ul style={{ margin: "0 0 12px", paddingLeft: 0, listStyle: "none" }}>
          {files.map((a, i) => (
            <li key={`${a.name}-${i}`} style={{ display: "flex", gap: 12, alignItems: "center", padding: "4px 0" }}>
              <span style={{ flex: 1 }}>
                {a.name} {newBadgeLabel && <span className="muted">({newBadgeLabel})</span>}
              </span>
              <button type="button" className="btn btn-secondary" disabled={disabled} onClick={() => remover(i)}>
                {removeLabel}
              </button>
            </li>
          ))}
        </ul>
      )}
      <label
        className="btn btn-secondary"
        style={{ cursor: disabled ? "default" : "pointer" }}
        onDragOver={(e) => e.preventDefault()}
        onDrop={soltar}
      >
        {selectLabel}
        <input type="file" multiple hidden disabled={disabled} accept={accept} onChange={escolher} />
      </label>
    </div>
  );
}

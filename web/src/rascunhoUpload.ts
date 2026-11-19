import { useEffect, useState } from "react";

// O que a pessoa já escolheu num formulário de envio (arquivos, título...) fica na memória da página: sair para outra tela e voltar não
// perde a seleção. Some ao recarregar a página (um File não sobrevive a isso). Os arquivos só sobem quando a pessoa confirma o envio.
const guardados = new Map<string, unknown>();

export function useRascunhoState<T>(chave: string, vazio: T): [T, (valor: T) => void, () => void] {
  const [valor, setValorLocal] = useState<T>(() => (guardados.has(chave) ? (guardados.get(chave) as T) : vazio));
  function setValor(novo: T) {
    guardados.set(chave, novo);
    setValorLocal(novo);
  }
  function limpar() {
    guardados.delete(chave);
  }
  return [valor, setValor, limpar];
}

// Recarregar ou fechar a aba perde os arquivos escolhidos e ainda não enviados: pede confirmação enquanto houver algum.
export function useAvisoAoSair(ativo: boolean): void {
  useEffect(() => {
    if (!ativo) return;
    const aviso = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", aviso);
    return () => window.removeEventListener("beforeunload", aviso);
  }, [ativo]);
}

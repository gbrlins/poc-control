export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const isFormData = init?.body instanceof FormData;

  const res = await fetch(path, {
    credentials: "include",
    ...init,
    headers: isFormData ? undefined : { "Content-Type": "application/json" },
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, body?.detail ?? "Erro inesperado");
  }

  return res.json() as Promise<T>;
}

export interface User {
  id: string;
  email: string;
  is_admin: boolean;
  tem_gemini_key: boolean;
  gemini_model: string | null;
}

export interface UsuarioListItem {
  id: string;
  email: string;
  is_admin: boolean;
  created_at: string;
  ultimo_login: string | null;
  tem_gemini_key: boolean;
}

export interface ProcedimentoListItem {
  id: string;
  titulo: string;
  tags: string[];
  categorias: string[];
  cliente_origem: string | null;
  status: "rascunho" | "validado";
  versao: number;
  data_origem: string | null;
  created_at: string;
  responsavel_id: string | null;
  responsavel_email: string | null;
}

export interface Secao {
  heading_level: number;
  heading_title: string;
  parent_heading_title: string | null;
  order_index: number;
}

export interface ProcedimentoDetail extends ProcedimentoListItem {
  html_original: string;
  secoes: Secao[];
}

export type StatusExtracao = "extraindo" | "pronto" | "erro";
export type StatusPoc = "ativa" | "concluida" | "suspensa";
export type StatusItem = "pendente" | "em_andamento" | "concluido" | "bloqueado" | "nao_aplicavel";
export type CondicaoItem = "suse" | "cliente" | "lateral";

export interface PocListItem {
  id: string;
  titulo: string;
  cliente: string;
  status: StatusPoc;
  status_extracao: StatusExtracao;
  created_at: string;
  total_itens: number;
  itens_concluidos: number;
  responsavel_id: string | null;
  responsavel_email: string | null;
}

export interface Fase {
  numero: number;
  titulo: string;
  descricao: string;
}

export type FlagClassificacao = "verde" | "amarelo" | "vermelho";
export type OrigemClassificacao = "auto" | "manual";

export interface Fonte {
  titulo: string;
  url: string;
}

export interface ModeloGemini {
  nome: string;
  nome_exibicao: string;
}

export interface Classificacao {
  flag: FlagClassificacao;
  origem: OrigemClassificacao;
  justificativa: string | null;
  fontes: Fonte[];
  procedimento_id: string | null;
  modelo: string | null;
  created_at: string;
}

export interface Sessao {
  id: string;
  data: string;
  participantes: string[];
  agenda: string | null;
  resumo_bruto: string | null;
  pontos_resolvidos: string[];
  pontos_falha: string[];
  proximos_passos: string[];
  created_at: string;
}

export interface SessaoPayload {
  data: string;
  participantes: string[];
  agenda?: string | null;
}

export interface Nota {
  id: string;
  sessao_id: string | null;
  texto: string;
  created_at: string;
}

export interface Anexo {
  id: string;
  sessao_id: string | null;
  nome_arquivo: string;
  procedimento_id: string | null;
  created_at: string;
}

export interface StatusHistoricoEntry {
  id: string;
  sessao_id: string | null;
  status_anterior: StatusItem | null;
  status_novo: StatusItem;
  created_at: string;
}

export interface ItemPoc {
  id: string;
  codigo: string;
  titulo: string;
  descricao: string | null;
  criterio_aceite: string | null;
  categoria: string | null;
  categoria_codigo: string | null;
  fase: number;
  ref: string | null;
  conducao: CondicaoItem | null;
  status: StatusItem;
  ordem: number;
  classificacao: Classificacao | null;
  notas: Nota[];
  anexos: Anexo[];
  status_historico: StatusHistoricoEntry[];
}

export interface ClassificacaoManualPayload {
  flag: FlagClassificacao;
  procedimento_id?: string | null;
  justificativa?: string | null;
}

export interface PrerequisitoPoc {
  id: string;
  titulo: string;
  descricao: string | null;
  atendido: boolean;
  ordem: number;
}

export interface ParametrosTecnicos {
  origem: string;
  projeto: { nome: string | null; organizacao: string | null; responsavel: string | null };
  produtos_selecionados: string[];
  rede: {
    cidr_gerenciamento: string | null;
    gateway: string | null;
    vip_cluster: string | null;
    pool_ip_inicio: string | null;
    pool_ip_fim: string | null;
    vms: Array<Record<string, unknown>>;
  };
  infra: Record<string, unknown>;
  portas_concluidas: number;
  portas_total: number;
}

export interface PocDetail extends PocListItem {
  escopo: string | null;
  erro_extracao: string | null;
  modelo_extracao: string | null;
  resumo_executivo: string | null;
  parametros_tecnicos: ParametrosTecnicos | null;
  fases: Fase[];
  itens: ItemPoc[];
  prerequisitos: PrerequisitoPoc[];
  sessoes: Sessao[];
}

export interface ItemUpdatePayload {
  titulo?: string;
  descricao?: string;
  criterio_aceite?: string;
  categoria?: string;
  categoria_codigo?: string | null;
  fase?: number;
  ref?: string;
  conducao?: CondicaoItem | null;
  status?: StatusItem;
  sessao_id?: string | null;
}

export type VeredictoRfi = "atende" | "atende_parcial" | "nao_atende" | "sem_evidencia";

export interface RfiItemOut {
  id: string;
  codigo: string;
  categoria: string | null;
  categoria_codigo: string | null;
  descricao: string;
  ordem: number;
  veredito: VeredictoRfi | null;
  justificativa: string | null;
  fontes: Fonte[];
  origem: OrigemClassificacao | null;
  procedimento_id: string | null;
  modelo: string | null;
  created_at: string;
}

export interface RfiListItem {
  id: string;
  titulo: string;
  orgao: string;
  numero_processo: string | null;
  status_extracao: StatusExtracao;
  criado_por_email: string;
  created_at: string;
  total_itens: number;
  itens_avaliados: number;
  responsavel_id: string | null;
  responsavel_email: string | null;
}

export interface RfiDetail extends RfiListItem {
  erro_extracao: string | null;
  modelo_extracao: string | null;
  nome_arquivo: string;
  itens: RfiItemOut[];
}

export interface RfiItemManualPayload {
  veredito: VeredictoRfi;
  justificativa?: string | null;
}

export type TipoRecurso = "pocs" | "rfis" | "procedimentos";

export interface VinculoResource {
  id: string;
  titulo: string;
  tipo?: "poc" | "rfi";
}

export interface PreviaExclusao {
  titulo: string;
  podeExcluir: boolean;
  semDono: boolean;
  contagens: Record<string, number>;
  procedimentosQuePermanecem: VinculoResource[];
  vinculosQuePerdemProcedimento: VinculoResource[];
}

export interface UsuarioLookup {
  id: string;
  email: string;
}

export const api = {
  login: (email: string, password: string) =>
    request<User>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  logout: () => request<{ status: string }>("/api/auth/logout", { method: "POST" }),
  me: () => request<User>("/api/auth/me"),
  salvarChaveGemini: (apiKey: string) =>
    request<User>("/api/auth/me/gemini-key", { method: "PUT", body: JSON.stringify({ api_key: apiKey }) }),
  removerChaveGemini: () => request<User>("/api/auth/me/gemini-key", { method: "DELETE" }),
  salvarModeloGemini: (model: string) =>
    request<User>("/api/auth/me/gemini-model", { method: "PUT", body: JSON.stringify({ model }) }),
  removerModeloGemini: () => request<User>("/api/auth/me/gemini-model", { method: "DELETE" }),
  listarModelosGemini: () => request<ModeloGemini[]>("/api/auth/me/gemini-models"),

  listarProcedimentos: () => request<ProcedimentoListItem[]>("/api/procedimentos"),
  obterProcedimento: (id: string) => request<ProcedimentoDetail>(`/api/procedimentos/${id}`),
  criarProcedimento: (form: FormData) =>
    request<ProcedimentoListItem>("/api/procedimentos", { method: "POST", body: form }),

  listarUsuarios: () => request<UsuarioListItem[]>("/api/users"),
  criarUsuario: (email: string, password: string, isAdmin: boolean) =>
    request<UsuarioListItem>("/api/users", {
      method: "POST",
      body: JSON.stringify({ email, password, is_admin: isAdmin }),
    }),
  alterarAdmin: (usuarioId: string, isAdmin: boolean) =>
    request<UsuarioListItem>(`/api/users/${usuarioId}/admin`, {
      method: "PATCH",
      body: JSON.stringify({ is_admin: isAdmin }),
    }),

  listarPocs: () => request<PocListItem[]>("/api/pocs"),
  obterPoc: (id: string) => request<PocDetail>(`/api/pocs/${id}`),
  criarPoc: (form: FormData) => request<PocListItem>("/api/pocs", { method: "POST", body: form }),
  reextrairPoc: (pocId: string) =>
    request<{ status: string }>(`/api/pocs/${pocId}/reextrair`, { method: "POST" }),
  atualizarItem: (pocId: string, itemId: string, payload: ItemUpdatePayload) =>
    request<ItemPoc>(`/api/pocs/${pocId}/itens/${itemId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  removerItem: (pocId: string, itemId: string) =>
    fetch(`/api/pocs/${pocId}/itens/${itemId}`, { method: "DELETE", credentials: "include" }).then((res) => {
      if (!res.ok) throw new ApiError(res.status, "Não foi possível remover o item");
    }),
  atualizarPrerequisito: (pocId: string, prereqId: string, atendido: boolean) =>
    request<PrerequisitoPoc>(`/api/pocs/${pocId}/prerequisitos/${prereqId}`, {
      method: "PATCH",
      body: JSON.stringify({ atendido }),
    }),

  classificarItem: (pocId: string, itemId: string) =>
    request<ItemPoc>(`/api/pocs/${pocId}/itens/${itemId}/classificar`, { method: "POST" }),
  sobrescreverClassificacao: (pocId: string, itemId: string, payload: ClassificacaoManualPayload) =>
    request<ItemPoc>(`/api/pocs/${pocId}/itens/${itemId}/classificacao`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  classificarPendentes: (pocId: string) =>
    request<{ status: string }>(`/api/pocs/${pocId}/classificar-pendentes`, { method: "POST" }),

  criarSessao: (pocId: string, payload: SessaoPayload) =>
    request<Sessao>(`/api/pocs/${pocId}/sessoes`, { method: "POST", body: JSON.stringify(payload) }),
  importarSessao: (pocId: string, texto: string) =>
    request<Sessao>(`/api/pocs/${pocId}/sessoes/importar`, { method: "POST", body: JSON.stringify({ texto }) }),
  gerarResumoSessao: (pocId: string, sessaoId: string) =>
    request<{ texto: string }>(`/api/pocs/${pocId}/sessoes/${sessaoId}/resumo`, { method: "POST" }),
  urlExportarPoc: (pocId: string) => `/api/pocs/${pocId}/export`,
  urlApresentacaoPoc: (pocId: string) => `/api/pocs/${pocId}/apresentacao`,
  urlRoteiro: (pocId: string, itemIds: string[]) =>
    `/api/pocs/${pocId}/roteiro?${itemIds.map((id) => `item_ids=${encodeURIComponent(id)}`).join("&")}`,
  gerarResumoExecutivo: (pocId: string) =>
    request<{ texto: string }>(`/api/pocs/${pocId}/apresentacao/resumo`, { method: "POST" }),
  salvarResumoExecutivo: (pocId: string, texto: string) =>
    request<{ texto: string }>(`/api/pocs/${pocId}/apresentacao/resumo`, {
      method: "PATCH",
      body: JSON.stringify({ resumo_executivo: texto }),
    }),

  criarNota: (pocId: string, itemId: string, sessaoId: string | null, texto: string) =>
    request<ItemPoc>(`/api/pocs/${pocId}/itens/${itemId}/notas`, {
      method: "POST",
      body: JSON.stringify({ sessao_id: sessaoId, texto }),
    }),
  removerNota: (pocId: string, itemId: string, notaId: string) =>
    request<ItemPoc>(`/api/pocs/${pocId}/itens/${itemId}/notas/${notaId}`, { method: "DELETE" }),

  criarAnexo: (pocId: string, itemId: string, form: FormData) =>
    request<ItemPoc>(`/api/pocs/${pocId}/itens/${itemId}/anexos`, { method: "POST", body: form }),
  removerAnexo: (pocId: string, itemId: string, anexoId: string) =>
    request<ItemPoc>(`/api/pocs/${pocId}/itens/${itemId}/anexos/${anexoId}`, { method: "DELETE" }),
  urlAnexo: (pocId: string, itemId: string, anexoId: string) =>
    `/api/pocs/${pocId}/itens/${itemId}/anexos/${anexoId}`,
  validarAnexo: (pocId: string, itemId: string, anexoId: string) =>
    request<ItemPoc>(`/api/pocs/${pocId}/itens/${itemId}/anexos/${anexoId}/validar`, { method: "POST" }),

  sugerirProcedimentos: (pocId: string, itemId: string) =>
    request<ProcedimentoListItem[]>(`/api/pocs/${pocId}/itens/${itemId}/sugestoes-procedimento`),

  listarRfis: () => request<RfiListItem[]>("/api/rfis"),
  obterRfi: (id: string) => request<RfiDetail>(`/api/rfis/${id}`),
  criarRfi: (form: FormData) => request<RfiListItem>("/api/rfis", { method: "POST", body: form }),
  sobrescreverVeredictoRfi: (rfiId: string, itemId: string, payload: RfiItemManualPayload) =>
    request<RfiItemOut>(`/api/rfis/${rfiId}/itens/${itemId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  reavaliarItemRfi: (rfiId: string, itemId: string) =>
    request<RfiItemOut>(`/api/rfis/${rfiId}/itens/${itemId}/reavaliar`, { method: "POST" }),
  urlExportarRfi: (rfiId: string) => `/api/rfis/${rfiId}/export`,
  urlExportarRfiXlsx: (rfiId: string) => `/api/rfis/${rfiId}/export.xlsx`,

  lookupUsuario: (email: string) =>
    request<UsuarioLookup>(`/api/auth/usuarios/lookup?email=${encodeURIComponent(email)}`),

  previaExclusao: (tipo: TipoRecurso, id: string) => request<PreviaExclusao>(`/api/${tipo}/${id}/exclusao`),
  definirResponsavel: (tipo: TipoRecurso, id: string, responsavelId: string) =>
    request<{ id: string; responsavel_id: string }>(`/api/${tipo}/${id}/responsavel`, {
      method: "PUT",
      body: JSON.stringify({ responsavel_id: responsavelId }),
    }),
  excluir: (tipo: TipoRecurso, id: string, confirmar: string) =>
    fetch(`/api/${tipo}/${id}`, {
      method: "DELETE",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmar }),
    }).then(async (res) => {
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new ApiError(res.status, body?.detail ?? "Não foi possível excluir");
      }
    }),
};

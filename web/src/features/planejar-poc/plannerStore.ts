// The ONE place the shell touches the planner's browser-local project storage. Everything here
// mirrors poc-planner/index.html's own registry (PROJECTS_INDEX_KEY / ACTIVE_PROJECT_KEY /
// projectKey / PENDING_IMPORT_KEY / USER_KEY, and ProjectMeta there). Planner projects live only
// in localStorage today; when they move to the database, replace the bodies below (keep the
// signatures) and the Home list and the "who last modified" columns need no other change.

const INDEX_KEY = "suse_poc_planner_projects";
const ACTIVE_KEY = "suse_poc_planner_active";
const PENDING_IMPORT_KEY = "suse_poc_planner_import_pending";
const USER_KEY = "suse_poc_planner_user";
const projectKey = (id: string) => `suse_poc_planner_project_${id}`;

export interface ProjetoLocal {
  id: string;
  nome: string;
  cliente: string;
  // Server PoC linked through the planner's "Habilitar execução" (state.pocControlId), if any.
  pocId: string | null;
  atualizadoEm: number;
  // Who last saved it and the revision (edit-session counter), stamped by ProjectMeta in the planner.
  modificadoPor: string;
  revisao: number;
}

export function listarProjetosLocais(): ProjetoLocal[] {
  let indice: Array<{ id: string; name?: string; updatedAt?: number; modifiedBy?: string; rev?: number }> = [];
  try {
    indice = JSON.parse(localStorage.getItem(INDEX_KEY) || "[]") || [];
  } catch {
    return [];
  }
  return indice.map((entrada) => {
    let cliente = "";
    let pocId: string | null = null;
    try {
      const raw = localStorage.getItem(projectKey(entrada.id));
      const projeto = raw ? JSON.parse(raw) : null;
      cliente = projeto?.project?.clientOrganization ?? "";
      pocId = projeto?.pocControlId || null;
    } catch {
      // corrupted project: still listed, just without customer/link.
    }
    return {
      id: entrada.id,
      nome: entrada.name || "",
      cliente,
      pocId,
      atualizadoEm: entrada.updatedAt ?? 0,
      modificadoPor: entrada.modifiedBy ?? "",
      revisao: entrada.rev ?? 0,
    };
  });
}

// The planner project (in THIS browser) that was linked to a server PoC by "Habilitar execução", if any.
export function acharProjetoDaPoc(pocId: string): string | null {
  return listarProjetosLocais().find((p) => p.pocId === pocId)?.id ?? null;
}

export function removerProjetoLocal(id: string): void {
  try {
    localStorage.removeItem(projectKey(id));
    const indice = JSON.parse(localStorage.getItem(INDEX_KEY) || "[]") || [];
    localStorage.setItem(INDEX_KEY, JSON.stringify(indice.filter((p: { id: string }) => p.id !== id)));
    if (localStorage.getItem(ACTIVE_KEY) === id) localStorage.removeItem(ACTIVE_KEY);
  } catch {
    // localStorage unavailable: nothing to delete.
  }
}

// Text of an exported project JSON, handed to the planner for ?import=project (it consumes it once).
export function deixarImportacaoPendente(texto: string): void {
  sessionStorage.setItem(PENDING_IMPORT_KEY, texto);
}

// The planner stamps each save with this name (it has no login of its own).
export function registrarUsuario(email: string): void {
  try {
    localStorage.setItem(USER_KEY, email);
  } catch {
    // localStorage unavailable: saves are just stamped without a user.
  }
}

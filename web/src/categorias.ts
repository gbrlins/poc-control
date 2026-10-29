// Taxonomia fixa de áreas do portfólio SUSE (espelha api/app/categorias.py). Usada para marcar
// Procedimentos (pode ter mais de um código) e mostrar a afinidade de um item de PoC/RFI.
export const CODIGOS_CATEGORIA = ["VIRT", "K8S", "STR", "SEC", "OBS", "OS", "EDGE", "IA"] as const;

export type CodigoCategoria = (typeof CODIGOS_CATEGORIA)[number];

type Rotulos = Record<CodigoCategoria, string>;

const ROTULOS: Record<"pt" | "en" | "es", Rotulos> = {
  pt: {
    VIRT: "Virtualização",
    K8S: "Kubernetes",
    STR: "Storage",
    SEC: "Segurança",
    OBS: "Observabilidade",
    OS: "Sistema operacional",
    EDGE: "Edge computing",
    IA: "Inteligência artificial",
  },
  en: {
    VIRT: "Virtualization",
    K8S: "Kubernetes",
    STR: "Storage",
    SEC: "Security",
    OBS: "Observability",
    OS: "Operating system",
    EDGE: "Edge computing",
    IA: "Artificial intelligence",
  },
  es: {
    VIRT: "Virtualización",
    K8S: "Kubernetes",
    STR: "Almacenamiento",
    SEC: "Seguridad",
    OBS: "Observabilidad",
    OS: "Sistema operativo",
    EDGE: "Edge computing",
    IA: "Inteligencia artificial",
  },
};

export function rotuloCategoria(codigo: string, idioma: "pt" | "en" | "es" = "pt"): string {
  const rotulos = ROTULOS[idioma] ?? ROTULOS.pt;
  return (rotulos as Record<string, string>)[codigo] ?? codigo;
}

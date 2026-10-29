"""Taxonomia fixa de áreas do portfólio SUSE, usada para marcar Procedimentos (pode ter mais de
uma) e Itens de PoC/RFI (uma só, a mais específica) com um código curto e padronizado. Objetivo:
restringir a busca vetorial de procedimentos ao subconjunto certo antes de rankear por
similaridade — mais rápido e mais barato em tokens do que varrer a base inteira a cada item.

Fonte única: as mesmas 8 áreas já usadas em gemini.py::_EXTRACAO_RFI_PROMPT (antes hardcoded só
ali). String livre validada aqui em Python, não ENUM do Postgres — mesmo padrão de
Procedimento.tags e Item.categoria (texto livre), para a lista poder crescer sem migração."""

CATEGORIAS: dict[str, str] = {
    "VIRT": "Virtualização de servidores / hipervisor (SUSE Virtualization/Harvester, HCI, vMotion, DRS)",
    "K8S": "Kubernetes / orquestração de containers (Rancher, RKE2/K3s, CNI, Ingress, GitOps, Helm)",
    "STR": "Armazenamento definido por software / storage (Longhorn, CSI, replicação, snapshots)",
    "SEC": "Segurança de containers/cluster (NeuVector, scan de vulnerabilidade, políticas de rede, RBAC)",
    "OBS": "Observabilidade (métricas, logs, Prometheus/Grafana, alertas)",
    "OS": "Sistema operacional Linux corporativo (SUSE Linux Enterprise Server, patches, compliance)",
    "EDGE": "Edge computing / dispositivos distribuídos",
    "IA": "Inteligência artificial / MLOps em infraestrutura on-premise",
}

CODIGOS_VALIDOS: tuple[str, ...] = tuple(CATEGORIAS)


def descricoes_formatadas() -> str:
    """Lista "- CÓDIGO: descrição" usada dentro dos prompts do Gemini (extração de PoC e de RFI)."""
    return "\n".join(f"- {codigo}: {descricao}" for codigo, descricao in CATEGORIAS.items())


def normalizar(codigo: str | None) -> str | None:
    """Converte o que o Gemini (ou um formulário) devolveu para um código válido ou None — nunca
    deixa passar um código inventado para o banco/filtro de busca."""
    if not codigo:
        return None
    codigo = codigo.strip().upper()
    return codigo if codigo in CATEGORIAS else None

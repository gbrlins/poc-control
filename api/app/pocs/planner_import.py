import json
from typing import Any


def extrair_parametros_tecnicos(texto: str) -> dict[str, Any] | None:
    """Se o texto de entrada for o JSON exportado pelo Planejar PoC (botão "Exportar Projeto"
    na etapa Resumo do SUSE PoC Planner), extrai os parâmetros técnicos direto da estrutura
    conhecida do JSON — produtos selecionados, rede e infraestrutura — sem passar pelo Gemini,
    para não arriscar o LLM alucinar ou perder um IP/hostname. Usado depois para montar o
    roteiro do dia (app/pocs/roteiro.py) e a seção "Ambiente técnico" da apresentação final.

    Nunca inclui o bloco `credentials` do planejador: credenciais não entram nem no roteiro
    nem em nenhum relatório gerado a partir daqui.

    Devolve None se o texto não for esse formato (ex.: PDF/texto livre de escopo), e quem
    chamar simplesmente não grava `parametros_tecnicos` na PoC.
    """
    try:
        dados = json.loads(texto)
    except (ValueError, TypeError):
        return None
    if not isinstance(dados, dict):
        return None

    # v2 do Planejar PoC (schema 2) exporta {schema, planner, eib, poc_markdown}, com o estado
    # de verdade dentro de `planner` -- antes (v1) era o estado solto, direto na raiz do JSON.
    # Aceita os dois formatos: se tiver `planner`, usa ele; senão assume que já é o estado.
    estado = dados.get("planner") if isinstance(dados.get("planner"), dict) else dados
    if "selectedProducts" not in estado:
        return None

    projeto = estado.get("project") or {}
    produtos_selecionados = sorted(k for k, v in (estado.get("selectedProducts") or {}).items() if v)
    rede = estado.get("network") or {}
    portas = estado.get("ports") or {}

    return {
        "origem": "planejador",
        "projeto": {
            "nome": projeto.get("projectName"),
            "organizacao": projeto.get("clientOrganization") or projeto.get("organization"),
            "responsavel": projeto.get("leadEngineer"),
        },
        "produtos_selecionados": produtos_selecionados,
        "rede": {
            "cidr_gerenciamento": rede.get("managementCidr"),
            "gateway": rede.get("gatewayIp"),
            "vip_cluster": rede.get("clusterVip"),
            "pool_ip_inicio": rede.get("ipPoolStart"),
            "pool_ip_fim": rede.get("ipPoolEnd"),
            "vms": rede.get("vms") or [],
        },
        "infra": estado.get("infra") or {},
        "portas_concluidas": sum(1 for v in (portas.get("checked") or {}).values() if v),
        "portas_total": len(portas.get("checked") or {}),
    }


# Produto do planejador -> código da taxonomia fixa (app/categorias.py), pra todo item importado do catálogo já
# nascer com afinidade de categoria, sem precisar de uma chamada ao Gemini pra isso (este caminho não usa Gemini).
_CATEGORIA_CODIGO_DO_PRODUTO = {
    "virtualization": "VIRT",
    "rancher": "K8S",
    "security": "SEC",
    "storage": "STR",
    "observability": "OBS",
    "registry": "K8S",
    "appcollection": "K8S",
    "manager": "OS",
}

# Mapeamentos dos valores do planejador para os do servidor (ADR 1). `result` -> estado do fluxo; `led` -> condução.
_STATUS_DO_RESULTADO = {
    "pending": "pendente", "scheduled": "em_andamento", "running": "em_andamento",
    "pass": "concluido", "partial": "concluido", "fail": "concluido", "na": "nao_aplicavel",
}
_CONDUCAO_DO_LED = {"suse": "suse", "client": "cliente", "partner": "parceiro", "side": "lateral"}
_RESULTADOS = tuple(_STATUS_DO_RESULTADO)
# `fitSource` do planejador (de onde a aderência aceita veio) -> `aderencia_origem`; vazio = marcada à mão.
_ORIGEM_DA_ADERENCIA = {"web": "web", "history": "historico"}
_ADERENCIAS = ("native", "config", "rancher", "third", "validate", "gap")
_LIMITE_TESTES = 1000


def _s(v: Any, limite: int) -> str:
    return " ".join(v.split())[:limite] if isinstance(v, str) else ""


def itens_do_planejador(texto: str) -> dict[str, Any] | None:
    """Se o texto for o JSON do planejador que traz a lista plana `tests` (poc-planner/docs/design-unification.md, contrato
    "vínculo com a execução"), devolve `{titulo, cliente, fases, itens}` para criar os itens DIRETO, sem pedir ao Gemini
    que os adivinhe: os testes do catálogo chegam com `catalogId`, título e resultado esperado já resolvidos.
    Devolve None para qualquer outro formato (o fluxo antigo, com Gemini, continua valendo para ele)."""
    try:
        dados = json.loads(texto)
    except (ValueError, TypeError):
        return None
    if not isinstance(dados, dict) or not isinstance(dados.get("tests"), list):
        return None
    estado = dados.get("planner") if isinstance(dados.get("planner"), dict) else {}
    projeto = estado.get("project") if isinstance(estado.get("project"), dict) else {}

    fases: list[dict[str, Any]] = []
    numero_da_fase: dict[str, int] = {}
    contagem: dict[int, int] = {}
    itens: list[dict[str, Any]] = []
    for t in dados["tests"][:_LIMITE_TESTES]:
        if not isinstance(t, dict):
            continue
        titulo = _s(t.get("title"), 500)
        if not titulo:
            continue
        produto = _s(t.get("product"), 40) or "outros"
        if produto not in numero_da_fase:
            numero_da_fase[produto] = len(fases) + 1
            fases.append({"numero": numero_da_fase[produto], "titulo": _s(t.get("productName"), 120) or produto, "descricao": ""})
        fase = numero_da_fase[produto]
        contagem[fase] = contagem.get(fase, 0) + 1
        resultado = t.get("result") if t.get("result") in _RESULTADOS else "pending"
        aderencia = t.get("fit") if t.get("fit") in _ADERENCIAS else None
        itens.append({
            "codigo": f"{fase}.{contagem[fase]}",
            "titulo": titulo,
            "criterio_aceite": _s(t.get("expected"), 2000) or None,
            "categoria": fases[fase - 1]["titulo"],
            "categoria_codigo": _CATEGORIA_CODIGO_DO_PRODUTO.get(produto),
            "fase": fase,
            "catalogo_id": _s(t.get("catalogId"), 80) or None,
            "planner_id": _s(t.get("id"), 40) or None,
            "resultado": resultado,
            "status": _STATUS_DO_RESULTADO[resultado],
            "prioridade": t.get("priority") if t.get("priority") in ("must", "nice") else None,
            "aderencia": aderencia,
            "aderencia_origem": _ORIGEM_DA_ADERENCIA.get(t.get("fitSource"), "manual") if aderencia else None,
            "conducao": _CONDUCAO_DO_LED.get(t.get("led")),
            "responsavel": _s(t.get("owner"), 255) or None,
        })
    if not itens:
        return None
    return {
        "titulo": _s(projeto.get("projectName"), 255) or "PoC sem título",
        "cliente": _s(projeto.get("clientOrganization") or projeto.get("organization"), 255),
        "fases": fases,
        "itens": itens,
    }

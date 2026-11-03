import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func

from app.categorias import normalizar as normalizar_categoria
from app.db import SessionLocal
from app.gemini import (
    extrair_itens_poc,
    extrair_projeto_planejador,
    interpretar_erro_gemini,
    modelo_efetivo,
)
from app.models import (
    AderenciaItem,
    AderenciaOrigem,
    CondicaoItem,
    Item,
    Poc,
    PocDocumento,
    PrioridadeItem,
    Prerequisito,
    ResultadoItem,
    StatusExtracao,
    StatusItem,
)
from app.classificacao.tasks import classificar_pendentes
from app.pocs.documentos import carregar_documento
from app.pocs.planner_import import itens_do_planejador
from app.pocs.resultados import sincronizar_resultado_catalogo

logger = logging.getLogger(__name__)

_PRODUTOS_PLANEJADOR = (
    "virtualization",
    "rancher",
    "security",
    "storage",
    "observability",
    "registry",
    "appcollection",
    "manager",
)


def iniciar_processamento(poc: Poc) -> None:
    """Marca a PoC como em processamento (também é o que vai bloquear endpoints de
    documento/reavaliação concorrentes, igual ao RFI). Quem chama faz o commit."""
    poc.status_extracao = StatusExtracao.extraindo
    poc.erro_extracao = None
    poc.processamento_iniciado_em = datetime.now(timezone.utc)
    poc.progresso = None
    poc.cancelamento_solicitado = False


def _cancelado(db, poc_id: uuid.UUID) -> bool:
    db.expire_all()  # lê o valor atual do banco, não o da sessão
    return bool(db.query(Poc.cancelamento_solicitado).filter(Poc.id == poc_id).scalar())


def _progresso(db, poc: Poc, fase: str, atual: int, total: int, nome: str) -> None:
    poc.progresso = {"fase": fase, "atual": atual, "total": total, "nome": nome}
    db.commit()


def _finalizar(db, poc_id: uuid.UUID, erro: bool = False) -> None:
    poc = db.get(Poc, poc_id)
    if poc is not None:
        poc.status_extracao = StatusExtracao.erro if erro else StatusExtracao.pronto
        poc.progresso = None
        poc.cancelamento_solicitado = False
        db.commit()


def _proxima_ordem(db, modelo, poc_id: uuid.UUID) -> int:
    # `or -1` quebraria quando o maior ordem existente for 0 (0 é falsy em Python, cairia no -1 do
    # fallback e repetiria ordem=0 no 2º documento) -- comparação explícita com None.
    maior = db.query(func.max(modelo.ordem)).filter(modelo.poc_id == poc_id).scalar()
    return 0 if maior is None else maior + 1


def _deslocar_fases(poc: Poc, fases_do_documento: list[dict]) -> int:
    """Soma as fases deste documento às já existentes na PoC (em vez de sobrescrever, como um
    segundo documento faria com o `poc.fases = ...` de antes) -- devolve o deslocamento aplicado,
    pra cada item desse documento somar no próprio número de fase e não colidir com a fase 1, 2...
    de um documento processado antes."""
    base = max((f["numero"] for f in (poc.fases or [])), default=0)
    poc.fases = [*(poc.fases or []), *({**f, "numero": f["numero"] + base} for f in fases_do_documento)]
    return base


def _aplicar_extracao_gemini(
    db,
    poc: Poc,
    documento_id: uuid.UUID,
    pdf_bytes: bytes | None,
    texto: str | None,
    api_key: str | None,
    model: str | None,
    hidratar_planejador: bool,
) -> None:
    if hidratar_planejador:
        extraido = extrair_projeto_planejador(pdf_bytes=pdf_bytes, texto=texto, api_key=api_key, model=model)
    else:
        extraido = extrair_itens_poc(pdf_bytes=pdf_bytes, texto=texto, api_key=api_key, model=model)

    base_fase = _deslocar_fases(poc, [f.model_dump() for f in extraido.fases])

    proxima_ordem = _proxima_ordem(db, Item, poc.id)
    for item in extraido.itens:
        db.add(
            Item(
                poc_id=poc.id,
                documento_id=documento_id,
                codigo=item.codigo,
                titulo=item.titulo,
                descricao=item.descricao,
                criterio_aceite=item.criterio_aceite,
                categoria=item.categoria,
                categoria_codigo=normalizar_categoria(item.categoria_codigo),
                fase=item.fase + base_fase,
                ref=item.ref or None,
                ordem=proxima_ordem,
            )
        )
        proxima_ordem += 1

    proxima_ordem_prereq = _proxima_ordem(db, Prerequisito, poc.id)
    for pre in extraido.prerequisitos:
        db.add(Prerequisito(poc_id=poc.id, titulo=pre.titulo, descricao=pre.descricao, ordem=proxima_ordem_prereq))
        proxima_ordem_prereq += 1

    # Só nesse fluxo (import a partir do planejador) título/cliente podem ter ficado em branco na
    # criação -- no fluxo normal (criar_poc) o usuário já os preenche antes do upload, então isso
    # nunca sobrescreve o que a pessoa digitou. hidratar_planejador só é usado com 1 documento
    # (importar_planejador), então não há risco de um 2º documento repetir esta parte.
    if hidratar_planejador:
        if not poc.titulo:
            poc.titulo = extraido.titulo_sugerido or "PoC sem título"
        if not poc.cliente:
            poc.cliente = extraido.cliente_sugerido or ""

        h = extraido.hidratacao
        produtos_detectados = set(h.produtos_detectados) & set(_PRODUTOS_PLANEJADOR)
        poc.parametros_tecnicos = {
            **(poc.parametros_tecnicos or {}),
            "hidratacao_planejador": {
                "responsavel": h.responsavel_sugerido,
                "email": h.email_responsavel_sugerido,
                "produtos": {p: (p in produtos_detectados) for p in _PRODUTOS_PLANEJADOR},
                "rede": {
                    "managementCidr": h.rede_cidr_gerenciamento,
                    "gatewayIp": h.rede_gateway,
                    "clusterVip": h.rede_vip_cluster,
                    "ipPoolStart": h.rede_pool_ip_inicio,
                    "ipPoolEnd": h.rede_pool_ip_fim,
                },
            },
        }


def _aplicar_planejador(db, poc: Poc, documento_id: uuid.UUID, planejador: dict) -> None:
    """Cria direto (sem Gemini) os itens de um documento no formato `tests` exportado pelo
    planejador -- ver app/pocs/planner_import.py::itens_do_planejador."""
    poc.modelo_extracao = poc.modelo_extracao or "planejador (sem IA)"
    base_fase = _deslocar_fases(poc, planejador["fases"])
    if not poc.titulo:
        poc.titulo = planejador["titulo"]
    if not poc.cliente:
        poc.cliente = planejador["cliente"]

    proxima_ordem = _proxima_ordem(db, Item, poc.id)
    criados: list[Item] = []
    for d in planejador["itens"]:
        item = Item(
            poc_id=poc.id,
            documento_id=documento_id,
            codigo=d["codigo"],
            titulo=d["titulo"],
            criterio_aceite=d["criterio_aceite"],
            categoria=d["categoria"],
            categoria_codigo=d.get("categoria_codigo"),
            fase=d["fase"] + base_fase,
            ordem=proxima_ordem,
            catalogo_id=d["catalogo_id"],
            planner_id=d["planner_id"],
            status=StatusItem(d["status"]),
            resultado=ResultadoItem(d["resultado"]),
            prioridade=PrioridadeItem(d["prioridade"]) if d["prioridade"] else None,
            aderencia=AderenciaItem(d["aderencia"]) if d["aderencia"] else None,
            aderencia_origem=AderenciaOrigem(d["aderencia_origem"]) if d["aderencia_origem"] else None,
            conducao=CondicaoItem(d["conducao"]) if d["conducao"] else None,
            responsavel=d["responsavel"],
        )
        proxima_ordem += 1
        db.add(item)
        criados.append(item)
    db.flush()  # dá id aos itens; o histórico só grava resultados terminais
    for item in criados:
        sincronizar_resultado_catalogo(db, item)


def _processar_documento(
    db,
    poc: Poc,
    documento_id: uuid.UUID,
    pdf_bytes: bytes | None,
    texto: str | None,
    api_key: str | None,
    model: str | None,
    hidratar_planejador: bool,
) -> None:
    planejador = itens_do_planejador(texto) if texto else None
    if planejador is not None:
        _aplicar_planejador(db, poc, documento_id, planejador)
        return
    _aplicar_extracao_gemini(db, poc, documento_id, pdf_bytes, texto, api_key, model, hidratar_planejador)


def processar_poc(
    poc_id: uuid.UUID,
    documento_ids: list[uuid.UUID],
    api_key: str | None = None,
    model: str | None = None,
    hidratar_planejador: bool = False,
) -> None:
    """Extrai os itens dos documentos indicados, um por vez (cada um numa chamada ao Gemini --
    mais robusto que um prompt gigante, e permite adicionar/remover um documento depois sem
    refazer os outros). Fases e a ordem de itens/pré-requisitos são acumuladas entre documentos
    (cada documento desloca a numeração das fases que ele próprio gerou, pra não colidir com a
    fase 1, 2... de um documento já processado). Chamado na criação da PoC (todos os documentos,
    inclusive pela importação do planejador, sempre com 1 só) e quando documentos são adicionados
    depois (só os novos). Pode ser interrompido (Poc.cancelamento_solicitado) entre documentos.
    Mesmo desenho de app/rfi/tasks.py::processar_rfi."""
    db = SessionLocal()
    try:
        poc = db.get(Poc, poc_id)
        if poc is None:
            return
        poc.modelo_extracao = modelo_efetivo(model)
        db.commit()

        erros: list[str] = []
        tentados = 0
        for n, doc_id in enumerate(documento_ids, start=1):
            if _cancelado(db, poc_id):
                break
            poc = db.get(Poc, poc_id)
            doc = db.get(PocDocumento, doc_id)
            if poc is None:
                return
            if doc is None:  # removido enquanto esperava na fila
                continue
            _progresso(db, poc, "lendo", n, len(documento_ids), doc.nome_arquivo)
            tentados += 1
            try:
                pdf_bytes, texto = carregar_documento(doc)
                _processar_documento(db, poc, doc.id, pdf_bytes, texto, api_key, model, hidratar_planejador)
                db.commit()
            except Exception as exc:  # noqa: BLE001 - não pode travar o lote por um documento com erro
                logger.exception("Falha ao extrair itens do documento %s da PoC %s (modelo=%s)", doc_id, poc_id, model)
                db.rollback()
                erros.append(f"{doc.nome_arquivo}: {interpretar_erro_gemini(exc)}")

        poc = db.get(Poc, poc_id)
        if poc is None:
            return
        if not poc.titulo:
            poc.titulo = "PoC sem título"
        # Só vira `erro` se NENHUM documento deu certo; se algum falhou e outro não, a PoC fica
        # `pronto` com a mensagem em erro_extracao (o front mostra como aviso) -- igual ao RFI.
        poc.erro_extracao = "\n".join(erros) or None
        db.commit()
        if erros and len(erros) == tentados:
            _finalizar(db, poc_id, erro=True)
            return
        _finalizar(db, poc_id)
    finally:
        db.close()

    # Encadeia a classificação item a item logo após a extração, igual o RFI já faz -- mesmo
    # espírito de "cada resultado aparece assim que fica pronto" em vez de depender do clique
    # manual em "Classificar pendentes" (que continua funcionando, pra reprocessar itens
    # adicionados/editados depois ou que falharam na primeira passada).
    classificar_pendentes(poc_id, api_key=api_key, model=model)

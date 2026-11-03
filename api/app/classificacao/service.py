import uuid

from sqlalchemy.orm import Session

from app.gemini import (
    CandidatoProcedimento,
    classificar_viabilidade,
    confirmar_match,
    embed_query,
    modelo_efetivo,
    pesquisar_viabilidade_web,
)
from app.models import (
    Classificacao,
    FlagClassificacao,
    Item,
    OrigemClassificacao,
    Procedimento,
    ProcedimentoChunk,
    RfiItem,
    StatusProcedimento,
    VeredictoRfi,
)
from app.pocs.resultados import item_executado_sem_problemas

TOP_K = 5

# Compartilhado entre o semáforo de PoC (classificar_item) e o RFI Analyser
# (app/rfi/service.py::_avaliar_por_historico) -- nunca o texto de um item real, pra nunca vazar
# qual cliente/PoC/edital originou o match (mesma anonimidade da ADR 1).
JUSTIFICATIVA_HISTORICO = (
    "Confirmado por execução/resposta anterior equivalente já confirmada (histórico anônimo, "
    "sem procedimento documentado ainda)."
)


def texto_item(item: Item) -> str:
    partes = [item.titulo]
    if item.descricao:
        partes.append(item.descricao)
    if item.criterio_aceite:
        partes.append(f"Critério de aceite: {item.criterio_aceite}")
    return "\n".join(partes)


def _texto_rfi_item(item: RfiItem) -> str:
    """Mirrors app/rfi/service.py::texto_item_rfi -- duplicated, not imported: rfi/service.py
    already imports from this module, so the reverse import would be circular."""
    partes = [item.codigo]
    if item.categoria:
        partes.append(item.categoria)
    partes.append(item.descricao)
    return " — ".join(partes)


def _buscar_candidatos(
    db: Session, vetor: list[float], categorias_afinidade: list[str] | None = None, limit: int = TOP_K
) -> list[ProcedimentoChunk]:
    """Busca vetorial nos procedimentos validados. Quando o item tem uma categoria da taxonomia
    fixa (app/categorias.py), restringe primeiro aos procedimentos marcados com ela -- mais rápido
    e mais barato em tokens do que rankear a base inteira a cada item. Se essa busca restrita não
    achar nada (a categoria ainda não tem nenhum procedimento cadastrado), refaz sem o filtro: uma
    lacuna de tagueamento nunca pode custar um match que existiria de outro jeito."""
    base = db.query(ProcedimentoChunk).join(Procedimento).filter(Procedimento.status == StatusProcedimento.validado)

    if categorias_afinidade:
        restrita = (
            base.filter(Procedimento.categorias.overlap(categorias_afinidade))
            .order_by(ProcedimentoChunk.embedding.cosine_distance(vetor))
            .limit(limit)
            .all()
        )
        if restrita:
            return restrita

    return base.order_by(ProcedimentoChunk.embedding.cosine_distance(vetor)).limit(limit).all()


def _buscar_candidatos_historico(
    db: Session, vetor: list[float], categorias_afinidade: list[str] | None = None, limit: int = TOP_K
) -> list[str]:
    """Mesma lógica de _buscar_candidatos, mas sobre itens de PoC (Item.embedding) e itens de RFI
    (RfiItem.embedding) que já viraram evidência confirmada -- ver atualizar_embedding_historico e
    atualizar_embedding_historico_rfi -- não sobre os Procedimentos. É a base de histórico
    compartilhada entre o semáforo de PoC (classificar_item) e o RFI Analyser
    (app/rfi/service.py::_avaliar_por_historico): "isto já foi confirmado antes", sem apontar qual
    cliente/PoC/edital (quem chama nunca recebe a linha original, só o texto renderizado, e a
    justificativa fica sempre em JUSTIFICATIVA_HISTORICO). Devolve texto já pronto, não as linhas
    do banco, porque as duas tabelas têm formatos diferentes (Item x RfiItem) e cada top-k é
    buscado separadamente -- pgvector/SQLAlchemy não faz um ORDER BY por distância através de duas
    tabelas mapeadas numa query só -- e concatenado antes de ir para a confirmação do Gemini, que já
    avalia a lista inteira de uma vez."""

    def _topo(query, coluna):
        return query.order_by(coluna.cosine_distance(vetor)).limit(limit).all()

    base_itens = db.query(Item).filter(Item.embedding.is_not(None))
    base_rfi = db.query(RfiItem).filter(RfiItem.embedding.is_not(None))

    if categorias_afinidade:
        itens = _topo(base_itens.filter(Item.categoria_codigo.in_(categorias_afinidade)), Item.embedding)
        rfi_itens = _topo(base_rfi.filter(RfiItem.categoria_codigo.in_(categorias_afinidade)), RfiItem.embedding)
        if itens or rfi_itens:
            return [texto_item(i) for i in itens] + [_texto_rfi_item(r) for r in rfi_itens]

    itens = _topo(base_itens, Item.embedding)
    rfi_itens = _topo(base_rfi, RfiItem.embedding)
    return [texto_item(i) for i in itens] + [_texto_rfi_item(r) for r in rfi_itens]


def atualizar_embedding_historico(db: Session, item: Item, api_key: str | None) -> None:
    """Mantém Item.embedding em sincronia com "este item é hoje um sucesso validado?"
    (item_executado_sem_problemas) -- chamado junto com sincronizar_resultado_catalogo em
    app/pocs/router.py::atualizar_item (PATCH de status/resultado/aderência), mas é uma função
    independente dela: uma cuida do histórico anônimo por catálogo (ADR 1), esta cuida do texto
    buscável para a base de histórico compartilhada (ver _buscar_candidatos_historico). Best-
    effort: uma falha ao chamar o Gemini aqui nunca pode quebrar a atualização do item em si.

    Não é chamada na importação em lote de itens do planejador
    (app/pocs/tasks.py::_aplicar_planejador) -- aquele caminho é deliberadamente sem
    Gemini; itens de lá só ganham embedding na próxima vez que algo no PATCH acima mudar (ex.:
    reabrir e fechar o item de novo), não no momento da importação."""
    if not item_executado_sem_problemas(db, item):
        item.embedding = None
        return
    if item.embedding is not None:
        return  # já calculado; editar título/descrição depois de um sucesso é raro o bastante pra ignorar
    try:
        item.embedding = embed_query(texto_item(item), api_key=api_key)
    except Exception:
        pass


def atualizar_embedding_historico_rfi(db: Session, rfi_item: RfiItem, api_key: str | None) -> None:
    """Lado RFI de atualizar_embedding_historico: um item de RFI vira evidência buscável assim que
    chega a `atende`, fechando o ciclo -- uma PoC pode confirmar um RFI, um RFI pode confirmar uma
    PoC ou outro RFI. Sem o conceito de resultado/bloqueado do PoC: o próprio veredito já é o
    sinal. Best-effort, mesma lógica de retry/silêncio da versão de PoC."""
    if rfi_item.veredito != VeredictoRfi.atende:
        rfi_item.embedding = None
        return
    if rfi_item.embedding is not None:
        return
    try:
        rfi_item.embedding = embed_query(_texto_rfi_item(rfi_item), api_key=api_key)
    except Exception:
        pass


def sugerir_procedimentos(
    db: Session, item: Item, api_key: str | None = None, limite: int = 5
) -> list[Procedimento]:
    """Procedimentos validados mais parecidos com o item, por similaridade semântica (mesma
    busca vetorial usada em classificar_item, já restrita por afinidade de categoria quando o
    item tem uma) — sem a confirmação do Gemini nem a busca web, só o ranking, pra alimentar o
    seletor de "Importar procedimento validado" na UI."""
    texto = texto_item(item)
    chunks = _buscar_candidatos(
        db,
        embed_query(texto, api_key=api_key),
        categorias_afinidade=[item.categoria_codigo] if item.categoria_codigo else None,
        limit=limite * 3,
    )
    vistos: dict[uuid.UUID, Procedimento] = {}
    for c in chunks:
        if c.procedimento_id not in vistos:
            vistos[c.procedimento_id] = c.procedimento
        if len(vistos) >= limite:
            break
    return list(vistos.values())


def _salvar_auto(
    db: Session,
    item: Item,
    *,
    flag: FlagClassificacao,
    justificativa: str,
    fontes: list[dict],
    procedimento_id: uuid.UUID | None,
    modelo: str,
    confirmado_por_historico: bool = False,
) -> Classificacao:
    classificacao = item.classificacao
    if classificacao is None:
        classificacao = Classificacao(item_id=item.id)
        db.add(classificacao)

    classificacao.flag = flag
    classificacao.origem = OrigemClassificacao.auto
    classificacao.justificativa = justificativa
    classificacao.fontes = fontes
    classificacao.procedimento_id = procedimento_id
    classificacao.confirmado_por_historico = confirmado_por_historico
    classificacao.modelo = modelo

    db.commit()
    db.refresh(classificacao)
    return classificacao


def classificar_item(
    db: Session, item: Item, api_key: str | None = None, model: str | None = None
) -> Classificacao:
    """Semáforo, em 3 passos (mesma ordem do RFI Analyser, ver app/rfi/service.py::avaliar_item_rfi):
    busca vetorial nos procedimentos validados → confirmação pelo Gemini → histórico compartilhado
    de respostas já confirmadas (PoC ou RFI) → só se nenhum dos dois confirmar, pesquisa de
    viabilidade na web com grounding do Google Search."""
    texto = texto_item(item)
    modelo_usado = modelo_efetivo(model)
    categorias_afinidade = [item.categoria_codigo] if item.categoria_codigo else None
    # Um embedding só, reaproveitado nas duas buscas vetoriais abaixo -- antes cada uma chamava
    # embed_query(texto) de novo, uma chamada ao Gemini inteiramente desperdiçada (mesmo texto,
    # mesmo vetor) sempre que a busca por procedimento não confirmava nada.
    vetor = embed_query(texto, api_key=api_key)

    chunks = _buscar_candidatos(db, vetor, categorias_afinidade=categorias_afinidade)
    if chunks:
        candidatos = [
            CandidatoProcedimento(
                titulo_procedimento=c.procedimento.titulo,
                heading_title=c.heading_title,
                content_text=c.content_text,
            )
            for c in chunks
        ]
        confirmacao = confirmar_match(texto, candidatos, api_key=api_key, model=model)
        if confirmacao.atende and 0 <= confirmacao.indice_candidato < len(chunks):
            procedimento = chunks[confirmacao.indice_candidato].procedimento
            return _salvar_auto(
                db,
                item,
                flag=FlagClassificacao.verde,
                justificativa=confirmacao.justificativa,
                fontes=[],
                procedimento_id=procedimento.id,
                modelo=modelo_usado,
            )

    textos_historico = _buscar_candidatos_historico(db, vetor, categorias_afinidade=categorias_afinidade)
    if textos_historico:
        candidatos_historico = [
            CandidatoProcedimento(titulo_procedimento="Execução/resposta anterior", heading_title="Item", content_text=t)
            for t in textos_historico
        ]
        confirmacao = confirmar_match(texto, candidatos_historico, api_key=api_key, model=model)
        if confirmacao.atende and 0 <= confirmacao.indice_candidato < len(textos_historico):
            return _salvar_auto(
                db,
                item,
                flag=FlagClassificacao.verde,
                justificativa=JUSTIFICATIVA_HISTORICO,
                fontes=[],
                procedimento_id=None,
                modelo=modelo_usado,
                confirmado_por_historico=True,
            )

    texto_pesquisa, fontes = pesquisar_viabilidade_web(texto, api_key=api_key, model=model)
    avaliacao = classificar_viabilidade(texto_pesquisa, api_key=api_key, model=model)
    fontes_dump = [f.model_dump() for f in fontes]

    if avaliacao.nao_suportado:
        flag = FlagClassificacao.vermelho
        justificativa = avaliacao.justificativa
    elif avaliacao.evidencia_viavel:
        flag = FlagClassificacao.amarelo
        justificativa = avaliacao.justificativa
    else:
        flag = FlagClassificacao.amarelo
        justificativa = f"Amarelo — baixa confiança (sem evidência de viabilidade). {avaliacao.justificativa}".strip()

    return _salvar_auto(
        db, item, flag=flag, justificativa=justificativa, fontes=fontes_dump, procedimento_id=None, modelo=modelo_usado
    )

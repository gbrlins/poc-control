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
    StatusProcedimento,
)

TOP_K = 5


def texto_item(item: Item) -> str:
    partes = [item.titulo]
    if item.descricao:
        partes.append(item.descricao)
    if item.criterio_aceite:
        partes.append(f"Critério de aceite: {item.criterio_aceite}")
    return "\n".join(partes)


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
    classificacao.modelo = modelo

    db.commit()
    db.refresh(classificacao)
    return classificacao


def classificar_item(
    db: Session, item: Item, api_key: str | None = None, model: str | None = None
) -> Classificacao:
    """Semáforo: busca vetorial nos procedimentos validados → confirmação pelo Gemini →
    se não houver match, pesquisa de viabilidade na web com grounding do Google Search."""
    texto = texto_item(item)
    modelo_usado = modelo_efetivo(model)

    chunks = _buscar_candidatos(
        db,
        embed_query(texto, api_key=api_key),
        categorias_afinidade=[item.categoria_codigo] if item.categoria_codigo else None,
    )
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

from sqlalchemy.orm import Session

from app.classificacao.service import _buscar_candidatos
from app.gemini import (
    CandidatoProcedimento,
    classificar_atendimento_rfi,
    confirmar_match,
    embed_query,
    modelo_efetivo,
    pesquisar_atendimento_rfi,
)
from app.models import OrigemClassificacao, RfiItem, VeredictoRfi


def texto_item_rfi(item: RfiItem) -> str:
    partes = [item.codigo]
    if item.categoria:
        partes.append(item.categoria)
    partes.append(item.descricao)
    return " — ".join(partes)


def _avaliar_por_procedimento_interno(
    db: Session, item: RfiItem, texto: str, api_key: str | None, model: str | None
) -> bool:
    """Primeiro procura na base de procedimentos validados (restrita por afinidade de categoria,
    mesma lógica de app/classificacao/service.py::classificar_item) antes de ir para a web --
    mesmo espírito do semáforo de PoC: um passo a passo interno já confirmado responde melhor (e
    mais rápido, mais barato em tokens) do que uma pesquisa na internet. Devolve True e já grava o
    veredito quando um procedimento confirma o atendimento; False quando não há nada confirmado
    (e quem chamou segue para a pesquisa web, sem tocar no item)."""
    chunks = _buscar_candidatos(
        db,
        embed_query(texto, api_key=api_key),
        categorias_afinidade=[item.categoria_codigo] if item.categoria_codigo else None,
    )
    if not chunks:
        return False

    candidatos = [
        CandidatoProcedimento(
            titulo_procedimento=c.procedimento.titulo, heading_title=c.heading_title, content_text=c.content_text
        )
        for c in chunks
    ]
    confirmacao = confirmar_match(texto, candidatos, api_key=api_key, model=model)
    if not confirmacao.atende or not (0 <= confirmacao.indice_candidato < len(chunks)):
        return False

    procedimento = chunks[confirmacao.indice_candidato].procedimento
    item.veredito = VeredictoRfi.atende
    item.justificativa = confirmacao.justificativa
    item.fontes = []
    item.procedimento_id = procedimento.id
    item.origem = OrigemClassificacao.auto
    item.modelo = modelo_efetivo(model)
    db.commit()
    db.refresh(item)
    return True


def avaliar_item_rfi(db: Session, item: RfiItem, api_key: str | None = None, model: str | None = None) -> RfiItem:
    """Semáforo de 4 estados do RFI: primeiro procura um procedimento interno já validado que \
    confirme o atendimento (_avaliar_por_procedimento_interno); só se não achar nada, pesquisa \
    com grounding do Google Search → classificação numa chamada separada (mesma limitação de \
    grounding+response_schema do semáforo de PoC, ver \
    app/classificacao/service.py::classificar_item)."""
    texto = texto_item_rfi(item)
    modelo_usado = modelo_efetivo(model)

    if _avaliar_por_procedimento_interno(db, item, texto, api_key, model):
        return item

    texto_pesquisa, fontes = pesquisar_atendimento_rfi(texto, api_key=api_key, model=model)
    avaliacao = classificar_atendimento_rfi(texto_pesquisa, api_key=api_key, model=model)

    if avaliacao.nao_atende:
        veredito = VeredictoRfi.nao_atende
    elif avaliacao.atende_totalmente:
        veredito = VeredictoRfi.atende
    elif avaliacao.atende_parcialmente:
        veredito = VeredictoRfi.atende_parcial
    else:
        veredito = VeredictoRfi.sem_evidencia

    item.veredito = veredito
    item.justificativa = avaliacao.justificativa
    item.fontes = [f.model_dump() for f in fontes]
    item.origem = OrigemClassificacao.auto
    item.procedimento_id = None
    item.modelo = modelo_usado

    db.commit()
    db.refresh(item)
    return item

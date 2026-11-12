import uuid

from sqlalchemy.orm import Session

from app.classificacao.service import (
    JUSTIFICATIVA_HISTORICO,
    _buscar_candidatos,
    _buscar_candidatos_historico,
    atualizar_embedding_historico_rfi,
)
from app.gemini import (
    CandidatoProcedimento,
    classificar_atendimento_rfi,
    confirmar_match,
    embed_query,
    interpretar_erro_gemini,
    modelo_efetivo,
    pesquisar_atendimento_rfi,
)
from app.models import OrigemClassificacao, RfiItem, VeredictoRfi

JUSTIFICATIVA_ERRO = (
    'Não foi possível avaliar este item: {erro} Use "Reavaliar" depois de resolver o problema.'
)


def texto_item_rfi(item: RfiItem) -> str:
    partes = [item.codigo]
    if item.categoria:
        partes.append(item.categoria)
    partes.append(item.descricao)
    return " — ".join(partes)


def _confirmar_procedimento_interno(
    db: Session, item: RfiItem, texto: str, vetor: list[float], api_key: str | None, model: str | None
) -> tuple[uuid.UUID, str] | None:
    """Primeiro procura na base de procedimentos validados (restrita por afinidade de categoria,
    mesma lógica de app/classificacao/service.py::classificar_item) antes de ir para a web --
    mesmo espírito do semáforo de PoC: um passo a passo interno já confirmado responde melhor (e
    mais rápido, mais barato em tokens) do que uma pesquisa na internet. Só confirma e devolve
    (procedimento_id, justificativa); não grava nada no item nem comita -- quem chama
    (_avaliar_item_rfi) decide o que fazer com a confirmação, porque mesmo com procedimento
    confirmando ela ainda complementa com uma busca web antes de persistir (ver seu próprio
    docstring). `vetor` já vem calculado por avaliar_item_rfi (embed_query de `texto`) e é
    reaproveitado aqui e em _avaliar_por_historico, em vez de cada uma recalcular o mesmo
    embedding com uma chamada a mais ao Gemini."""
    chunks = _buscar_candidatos(
        db,
        vetor,
        categorias_afinidade=[item.categoria_codigo] if item.categoria_codigo else None,
    )
    if not chunks:
        return None

    candidatos = [
        CandidatoProcedimento(
            titulo_procedimento=c.procedimento.titulo, heading_title=c.heading_title, content_text=c.content_text
        )
        for c in chunks
    ]
    confirmacao = confirmar_match(texto, candidatos, api_key=api_key, model=model)
    if not confirmacao.atende or not (0 <= confirmacao.indice_candidato < len(chunks)):
        return None

    procedimento = chunks[confirmacao.indice_candidato].procedimento
    return procedimento.id, confirmacao.justificativa


def _avaliar_por_historico(
    db: Session, item: RfiItem, texto: str, vetor: list[float], api_key: str | None, model: str | None
) -> bool:
    """Segunda fonte de evidência, depois dos procedimentos internos e antes da web: a base de
    histórico compartilhada (app/classificacao/service.py::_buscar_candidatos_historico), que
    junta itens de PoC e de RFI que já viraram evidência confirmada. Mesmo formato de confirmação
    do Gemini usado para procedimentos (confirmar_match), mas a justificativa nunca é a dele --
    sempre o texto fixo e anônimo em JUSTIFICATIVA_HISTORICO, pra nunca vazar qual cliente/PoC/
    edital originou o match (mesma anonimidade da ADR 1). `vetor`: ver docstring de
    _confirmar_procedimento_interno -- mesmo embedding, calculado uma vez só."""
    textos_historico = _buscar_candidatos_historico(
        db,
        vetor,
        categorias_afinidade=[item.categoria_codigo] if item.categoria_codigo else None,
    )
    if not textos_historico:
        return False

    candidatos = [
        CandidatoProcedimento(titulo_procedimento="Execução/resposta anterior", heading_title="Item", content_text=t)
        for t in textos_historico
    ]
    confirmacao = confirmar_match(texto, candidatos, api_key=api_key, model=model)
    if not confirmacao.atende or not (0 <= confirmacao.indice_candidato < len(textos_historico)):
        return False

    item.veredito = VeredictoRfi.atende
    item.justificativa = JUSTIFICATIVA_HISTORICO
    item.fontes = []
    item.procedimento_id = None
    item.confirmado_por_historico = True
    item.origem = OrigemClassificacao.auto
    item.modelo = modelo_efetivo(model)
    atualizar_embedding_historico_rfi(db, item, api_key)
    db.commit()
    db.refresh(item)
    return True


def _etapa(db: Session, item: RfiItem, etapa: str | None) -> None:
    """Grava o passo atual da avaliação (o front mostra ao abrir o item enquanto processa)."""
    item.etapa = etapa
    db.commit()


def avaliar_item_rfi(db: Session, item: RfiItem, api_key: str | None = None, model: str | None = None) -> RfiItem:
    # Antes de tentar: se a chamada ao Gemini falhar (sem credencial cadastrada, chave inválida,
    # quota, etc.), um item que nunca tinha sido avaliado ficava com veredito=null pra sempre --
    # o front (RfiDetail.tsx) usa exatamente esse campo pra decidir se ainda está "processando" e
    # continuar o polling, então a tela mostrava "em processamento" indefinidamente, sem nenhum
    # indício de que já tinha falhado (só um log no servidor, nunca visto pelo usuário). Guardado
    # antes da tentativa porque o `except` abaixo precisa saber se havia algo bom a preservar.
    veredito_antes = item.veredito
    try:
        return _avaliar_item_rfi(db, item, api_key, model)
    except Exception as exc:
        db.rollback()
        if veredito_antes is None:
            # Nunca tinha sido avaliado: marca "sem evidência" com o erro real do Gemini na
            # justificativa, pra sair do limbo "processando" e o usuário saber que precisa
            # resolver a credencial (ou outro problema) e usar "Reavaliar" -- em vez de ficar
            # girando pra sempre. Quem já tinha um veredito confirmado (reavaliação que falhou)
            # mantém o que já tinha: uma falha transiente não pode apagar uma resposta boa.
            item.veredito = VeredictoRfi.sem_evidencia
            item.justificativa = JUSTIFICATIVA_ERRO.format(erro=interpretar_erro_gemini(exc))
            item.origem = None
        item.etapa = None
        db.commit()
        raise
    finally:
        # Sai da avaliação (com sucesso ou não): nenhum passo "em curso" fica pendurado no item.
        try:
            if item.etapa is not None:
                item.etapa = None
                db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()


def _avaliar_item_rfi(db: Session, item: RfiItem, api_key: str | None, model: str | None) -> RfiItem:
    """Semáforo de 4 estados do RFI, em 3 passos: procedimento interno já validado
    (_confirmar_procedimento_interno) → histórico de execuções bem-sucedidas equivalentes
    (_avaliar_por_historico) → só se nenhum dos dois confirmar, pesquisa com grounding do Google
    Search → classificação numa chamada separada (mesma limitação de grounding+response_schema do
    semáforo de PoC, ver app/classificacao/service.py::classificar_item)."""
    texto = texto_item_rfi(item)
    modelo_usado = modelo_efetivo(model)
    # Um embedding só, reaproveitado pelos dois passos abaixo (ver suas docstrings) -- antes cada
    # um chamava embed_query(texto) de novo, uma chamada ao Gemini desperdiçada sempre que o
    # procedimento interno não confirmava nada.
    _etapa(db, item, "procedimento")
    vetor = embed_query(texto, api_key=api_key)

    confirmacao_interna = _confirmar_procedimento_interno(db, item, texto, vetor, api_key, model)
    if confirmacao_interna is not None:
        procedimento_id, justificativa = confirmacao_interna
        item.veredito = VeredictoRfi.atende
        item.justificativa = justificativa
        item.procedimento_id = procedimento_id
        item.confirmado_por_historico = False
        item.origem = OrigemClassificacao.auto
        item.modelo = modelo_efetivo(model)
        # Mesmo com o procedimento confirmando (evidência mais forte, já destacada na UI -- ver
        # RfiItemRow), complementa com fontes da web em vez de pular a pesquisa de vez: só a
        # busca com grounding, sem a segunda chamada de classificação (o veredito já está
        # decidido pelo procedimento, não precisa reclassificar). Uma falha aqui não pode derrubar
        # um veredito que já foi confirmado -- fica só sem fontes complementares.
        _etapa(db, item, "web")
        try:
            _, fontes = pesquisar_atendimento_rfi(texto, api_key=api_key, model=model)
            item.fontes = [f.model_dump() for f in fontes]
        except Exception:  # noqa: BLE001 - complemento best-effort, não pode perder a confirmação
            item.fontes = []
        atualizar_embedding_historico_rfi(db, item, api_key)
        db.commit()
        db.refresh(item)
        return item

    _etapa(db, item, "historico")
    if _avaliar_por_historico(db, item, texto, vetor, api_key, model):
        return item

    _etapa(db, item, "web")
    texto_pesquisa, fontes = pesquisar_atendimento_rfi(texto, api_key=api_key, model=model)
    _etapa(db, item, "classificando")
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
    item.confirmado_por_historico = False
    item.modelo = modelo_usado
    atualizar_embedding_historico_rfi(db, item, api_key)

    db.commit()
    db.refresh(item)
    return item

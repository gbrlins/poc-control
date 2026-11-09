"""Casamento de termo de busca contra o objeto de uma licitação -- o PNCP não tem busca por
palavra-chave (ver pncp_client.py), então o filtro é feito aqui, em cima do texto já baixado."""

import unicodedata


def _normalizar(texto: str) -> str:
    """Minúsculas e sem acento, pra "contêineres" bater com "conteineres" e "SLES" bater com
    "sles" independente de como o termo ou o objeto foram digitados."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return sem_acento.lower()


def termos_que_batem(objeto: str, termos: list[str]) -> list[str]:
    """Devolve os termos (na forma original, não normalizada) cuja versão normalizada aparece como
    substring do objeto normalizado. Lista vazia quando nenhum bate."""
    objeto_normalizado = _normalizar(objeto)
    return [termo for termo in termos if _normalizar(termo) in objeto_normalizado]

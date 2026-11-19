"""URLs reais das fontes do Gemini.

Com grounding do Google Search, cada fonte volta como um link de redirecionamento
(vertexaisearch.cloud.google.com/grounding-api-redirect/...) e o "título" é só o domínio. Esse link some com o tempo e não diz nada a
quem lê, então resolvemos o redirecionamento UMA vez, na hora de gravar a fonte, e guardamos o endereço final. Qualquer falha
(timeout, sem Location, host inesperado) devolve o link original: nunca perde a fonte."""
import logging
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

_HOSTS_DE_REDIRECIONAMENTO = {"vertexaisearch.cloud.google.com"}
_TIMEOUT_S = 4.0
_MAX_PARALELO = 8


def _resolver(url: str) -> str:
    try:
        if urlparse(url).hostname not in _HOSTS_DE_REDIRECIONAMENTO:
            return url
        with httpx.Client(timeout=_TIMEOUT_S, follow_redirects=False) as cliente:
            resposta = cliente.get(url)
        destino = resposta.headers.get("location", "")
        if resposta.is_redirect and urlparse(destino).scheme in ("http", "https"):
            return destino
    except Exception:  # noqa: BLE001 -- resolver é conveniência; a fonte original continua valendo
        logger.info("Não foi possível resolver o redirecionamento da fonte", exc_info=True)
    return url


def resolver_urls(urls: list[str]) -> list[str]:
    """Resolve vários links em paralelo, mantendo a ordem."""
    if not urls:
        return []
    with ThreadPoolExecutor(max_workers=min(_MAX_PARALELO, len(urls))) as pool:
        return list(pool.map(_resolver, urls))

"""Importa os procedimentos validados de seed/procedimentos/ para o banco.

Uso: docker compose run --rm --entrypoint python api scripts/import_seed.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.db import SessionLocal
from app.gemini import embed_document
from app.models import Procedimento, ProcedimentoChunk, StatusProcedimento
from app.procedimentos.html_processing import extrair_secoes

SEED_DIR = pathlib.Path(__file__).resolve().parent.parent / "seed" / "procedimentos"

PROCEDIMENTOS = [
    {
        "arquivo": "argo-cd-k3s.html",
        "titulo": "Argo CD do cliente → k3s: roteiro da sessão",
        "tags": ["Argo CD", "k3s", "OpenShift", "GitOps"],
        "categorias": ["K8S"],
    },
    {
        "arquivo": "hpa-nginx-k3s-ingress.html",
        "titulo": "HPA em nginx no k3s, com Ingress",
        "tags": ["k3s", "HPA", "Ingress", "Traefik", "Rancher"],
        "categorias": ["K8S"],
    },
    {
        "arquivo": "vault-k3s-integracao.html",
        "titulo": "Integração do k3s com Vault externo",
        "tags": ["k3s", "Vault", "HashiCorp Vault", "Kubernetes Auth"],
        "categorias": ["K8S", "SEC"],
    },
]


def main() -> None:
    db = SessionLocal()
    try:
        for item in PROCEDIMENTOS:
            existente = db.query(Procedimento).filter(Procedimento.titulo == item["titulo"]).first()
            if existente is not None:
                print(f"Já existe, pulando: {item['titulo']}")
                continue

            html = (SEED_DIR / item["arquivo"]).read_text(encoding="utf-8")
            secoes = extrair_secoes(html)

            procedimento = Procedimento(
                titulo=item["titulo"],
                tags=item["tags"],
                categorias=item["categorias"],
                cliente_origem="Sefaz-RJ",
                data_origem=None,
                status=StatusProcedimento.validado,
                versao=1,
                html_original=html,
            )
            db.add(procedimento)

            for secao in secoes:
                embedding = embed_document(secao.content_text)
                db.add(
                    ProcedimentoChunk(
                        procedimento=procedimento,
                        heading_level=secao.heading_level,
                        heading_title=secao.heading_title,
                        parent_heading_title=secao.parent_heading_title,
                        order_index=secao.order_index,
                        content_text=secao.content_text,
                        embedding=embedding,
                    )
                )

            db.commit()
            print(f"Importado: {item['titulo']} ({len(secoes)} seções)")
    finally:
        db.close()


if __name__ == "__main__":
    main()

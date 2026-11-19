"""Importa os procedimentos validados de seed/procedimentos/ para o banco, do mesmo jeito que um upload pela tela.

Uso (dentro do contêiner da api, com a pasta seed/ montada pelo docker-compose):
    docker compose run --rm --entrypoint python api scripts/import_seed.py --user voce@exemplo.com

--user  e-mail de um usuário existente: ele vira o dono dos procedimentos e a chave do Gemini cadastrada em "Minha conta" é a usada
        (embeddings e tradução). Sem --user vale a GEMINI_API_KEY do ambiente e os procedimentos ficam sem dono (qualquer engenheiro
        pode assumi-los depois).

Cada procedimento passa por app.procedimentos.router._criar_procedimento -- o mesmo caminho do upload e da importação por JSON --, então
ganha o idioma detectado, o título e a tradução em inglês e as seções com embedding. Os que já existem (mesmo título) são pulados:
rodar de novo é seguro. Precisa de uma chave do Gemini válida; sem ela o script avisa e para.
"""

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.db import SessionLocal
from app.gemini_key import resolve_api_key
from app.models import Procedimento, StatusProcedimento, User
from app.procedimentos.router import _criar_procedimento

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Importa os procedimentos de seed/procedimentos/.")
    parser.add_argument("--user", help="e-mail do usuário dono (e da chave do Gemini); sem ele, usa a chave do ambiente e fica sem dono")
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        usuario = None
        if args.user:
            usuario = db.query(User).filter(User.email == args.user).first()
            if usuario is None:
                print(f"Usuário não encontrado: {args.user}", file=sys.stderr)
                return 1
        api_key = resolve_api_key(usuario) if usuario is not None else None

        criados = 0
        for item in PROCEDIMENTOS:
            if db.query(Procedimento).filter(Procedimento.titulo == item["titulo"]).first() is not None:
                print(f"Já existe, pulando: {item['titulo']}")
                continue
            html = (SEED_DIR / item["arquivo"]).read_text(encoding="utf-8")
            try:
                procedimento = _criar_procedimento(
                    db,
                    titulo=item["titulo"],
                    tags=item["tags"],
                    categorias=item["categorias"],
                    cliente_origem="Sefaz-RJ",
                    data_origem=None,
                    status_valor=StatusProcedimento.validado,
                    versao=1,
                    html=html,
                    api_key=api_key,
                    dono_id=usuario.id if usuario is not None else None,
                )
            except Exception as exc:  # noqa: BLE001 - quase sempre é a chave do Gemini (ausente, inválida, sem cota)
                db.rollback()
                print(f"Falhou em '{item['titulo']}': {exc}", file=sys.stderr)
                print("Confira a chave do Gemini (--user usa a de 'Minha conta'; sem --user vale a GEMINI_API_KEY).", file=sys.stderr)
                return 1
            criados += 1
            print(f"Importado: {item['titulo']} ({len(procedimento.chunks)} seções, idioma {procedimento.idioma_original or '?'}, EN: {procedimento.titulo_en or '-'})")
        print(f"Pronto: {criados} importado(s).")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())

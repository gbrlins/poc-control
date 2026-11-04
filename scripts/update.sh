#!/bin/sh
# Atualiza o deployment pra última versão do repo: git pull, rebuild das imagens que mudaram,
# recria os contêineres (não só rebuilda a imagem -- ver nota abaixo) e confere o resultado.
# Migrações do banco rodam sozinhas: docker-entrypoint.sh já chama `alembic upgrade head` toda
# vez que o contêiner da api sobe, então não tem passo manual de migração aqui.
#
# Uso: scripts/update.sh [--force]
#   --force   rebuilda e recria mesmo se o git pull não trouxe nada novo.

set -eu

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"   # raiz deste repo (poc-control é o próprio repo aqui, não uma pasta de monorepo)
REPO_DIR="$PROJECT_DIR"
FORCE=0
[ "${1:-}" = "--force" ] && FORCE=1

cd "$REPO_DIR"
ANTES="$(git rev-parse HEAD)"
git pull
DEPOIS="$(git rev-parse HEAD)"

if [ "$ANTES" = "$DEPOIS" ] && [ "$FORCE" -eq 0 ]; then
    echo "Já está na última versão ($DEPOIS) -- nada a fazer (use --force pra recriar mesmo assim)."
    exit 0
fi

echo "Atualizando $ANTES -> $DEPOIS"
cd "$PROJECT_DIR"

# A stack real nesta Pi roda em Docker (dockerd ativo, contêineres `poc-control-{web,api,db}-1`
# criados pelo Docker Compose v2, nomes com hífen) -- não em Podman. `gbrlins` não está no grupo
# `docker` (ver CLAUDE.md/memória de acesso), então todo comando de Docker aqui precisa de `sudo`;
# o `sudo` abaixo pede a senha normalmente quando rodado numa sessão interativa de verdade.
# `docker compose up -d` (Compose v2) já recria sozinho qualquer contêiner cuja imagem mudou --
# não precisa do workaround manual de stop+rm que uma versão antiga deste script tinha pra um
# `podman-compose` que nunca foi, de fato, o que roda em produção aqui (2026-11-04).
sudo docker compose build

sudo docker compose up -d

echo
echo "--- Verificação ---"
sleep 3
sudo docker compose ps
# shellcheck disable=SC1091
[ -f .env ] && . ./.env 2>/dev/null || true
echo
echo "Bundle servido:"
curl -s http://localhost:"${WEB_PORT:-8090}"/ | grep -o 'index-[^"]*\.js' || echo "  (não consegui ler -- confira manualmente)"
echo "Revisão do banco:"
sudo docker exec poc-control-api-1 python -m alembic current || echo "  (não consegui ler -- confira manualmente)"

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

podman compose build

# `podman compose up -d --build` sozinho NÃO recria um contêiner já existente, só rebuilda a
# imagem (achado em produção, nesta mesma máquina, na época com o `podman-compose` standalone --
# que nem tinha o subcomando `rm`; hoje `podman compose` delega pro `docker-compose` instalado
# como cli-plugin do próprio podman, 2026-11-04). Então recria à mão, UM DE CADA VEZ, na ordem
# "web" primeiro e "api" depois --
# `web` depende de `api`, e o `rm` tem que terminar de verdade pra `web` (uma chamada só pra
# `podman rm`) antes da chamada seguinte tentar `api`. Já tentamos um `podman rm` por contêiner
# dentro de um loop só de remoção (06efe1d) e depois um único `podman rm -f web api` numa chamada
# só (a8115433) -- os dois ainda falharam com "has dependent containers", porque a checagem de
# dependência do podman não respeita a ordem dos argumentos dentro de uma chamada multi-arg (ele
# processa por algo como ordem de criação/ID interno, não a ordem do array do shell). A única
# forma que realmente funcionou ao testar manualmente é stop+rm como DUAS CHAMADAS DE COMANDO
# separadas por contêiner, dentro do mesmo loop -- é isso abaixo. `db` fica de fora de propósito
# -- não muda de imagem com o código, e os dados estão no volume `pgdata`, não no contêiner.
for SERVICO in web api; do
    CONTAINER="poc-control_${SERVICO}_1"
    if podman container exists "$CONTAINER"; then
        podman stop "$CONTAINER" >/dev/null
        podman rm -f "$CONTAINER" >/dev/null
    fi
done

podman compose up -d

echo
echo "--- Verificação ---"
sleep 3
podman compose ps
# shellcheck disable=SC1091
[ -f .env ] && . ./.env 2>/dev/null || true
echo
echo "Bundle servido:"
curl -s http://localhost:"${WEB_PORT:-8090}"/ | grep -o 'index-[^"]*\.js' || echo "  (não consegui ler -- confira manualmente)"
echo "Revisão do banco:"
podman exec poc-control_api_1 python -m alembic current || echo "  (não consegui ler -- confira manualmente)"

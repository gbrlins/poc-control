#!/bin/sh
# Define a versão do produto num lugar só e propaga para o resto.
#
# Fonte única: "version" em web/package.json (o que o `vite build` injeta no rodapé do app). Este script grava o mesmo número em
# web/package-lock.json (via `npm version`) e na constante APP_VERSION do planejador (poc-planner/index.html), que aparece no cabeçalho dele e
# nos relatórios que ele gera. `web/tests/version.check.mts` falha se algum dos três divergir.
#
# Uso: scripts/set-version.sh 2.1.0     (depois: git commit, e `git tag -a v2.1.0` no commit da versão)
set -eu

VERSAO="${1:-}"
case "$VERSAO" in
  [0-9]*.[0-9]*.[0-9]*) ;;
  *) echo "Uso: $0 MAJOR.MINOR.PATCH (ex.: 2.1.0)" >&2; exit 1 ;;
esac

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"

( cd "$RAIZ/web" && npm version "$VERSAO" --no-git-tag-version --allow-same-version >/dev/null )
sed -i "s/^const APP_VERSION = '[^']*';/const APP_VERSION = '$VERSAO';/" "$RAIZ/poc-planner/index.html"

echo "Versão $VERSAO gravada em web/package.json, web/package-lock.json e poc-planner/index.html."
echo "Confira com: node --experimental-strip-types web/tests/version.check.mts"

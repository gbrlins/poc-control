// Every "/api/..." path the frontend calls must sit under a prefix the backend actually serves.
// Run with: node --experimental-strip-types web/tests/apiPaths.check.mts  (exit code 1 on any FAIL)
// Born from a blanket page-route rename that also rewrote /api/procedimentos/... to /api/procedures/... (the API was never renamed).
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const raiz = new URL("../../", import.meta.url).pathname;
function arquivos(dir: string, ext: RegExp): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? arquivos(p, ext) : ext.test(n) ? [p] : [];
  });
}
const prefixos = new Set(
  arquivos(join(raiz, "api/app"), /\.py$/).flatMap((f) => [...readFileSync(f, "utf8").matchAll(/APIRouter\([^)]*prefix="([^"]+)"/g)].map((m) => m[1])),
);
const usados = new Set(
  arquivos(join(raiz, "web/src"), /\.tsx?$/).flatMap((f) => [...readFileSync(f, "utf8").matchAll(/[`"'](\/api\/[a-z_/-]+)/g)].map((m) => m[1])),
);
let falhou = false;
for (const u of [...usados].sort()) {
  const ok = [...prefixos].some((p) => u.startsWith(p));
  if (!ok) { console.log("FAIL", u, "is not under any backend router prefix"); falhou = true; }
}
console.log(falhou ? "" : `ok   ${usados.size} API paths all under one of ${prefixos.size} backend prefixes`);
process.exitCode = falhou ? 1 : 0;

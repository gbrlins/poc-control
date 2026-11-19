// The product has ONE version: "version" in web/package.json (what the app footer shows). The lock file and the planner's APP_VERSION
// must carry the same number; scripts/set-version.sh writes all three.
// Run with: node --experimental-strip-types web/tests/version.check.mts  (exit code 1 on any FAIL)
import { readFileSync } from "node:fs";

const raiz = new URL("../../", import.meta.url).pathname;
const pkg = JSON.parse(readFileSync(`${raiz}web/package.json`, "utf8")).version as string;
const lock = JSON.parse(readFileSync(`${raiz}web/package-lock.json`, "utf8"));
const planner = /^const APP_VERSION = '([^']*)';/m.exec(readFileSync(`${raiz}poc-planner/index.html`, "utf8"))?.[1];

const encontradas: Record<string, string | undefined> = {
  "web/package.json": pkg,
  "web/package-lock.json (version)": lock.version,
  "web/package-lock.json (packages[''])": lock.packages?.[""]?.version,
  "poc-planner/index.html (APP_VERSION)": planner,
};
let falhou = false;
if (!/^\d+\.\d+\.\d+$/.test(pkg)) { console.log("FAIL web/package.json version is not MAJOR.MINOR.PATCH:", pkg); falhou = true; }
for (const [onde, v] of Object.entries(encontradas)) {
  if (v !== pkg) { console.log(`FAIL ${onde} is ${v ?? "missing"}, expected ${pkg}`); falhou = true; }
}
if (!falhou) console.log(`ok   version ${pkg} is the same in all ${Object.keys(encontradas).length} places`);
process.exitCode = falhou ? 1 : 0;

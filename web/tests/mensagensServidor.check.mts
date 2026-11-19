// Run with: node --experimental-strip-types web/tests/mensagensServidor.check.mts  (exit code 1 on any FAIL)
import { traduzirMensagemServidor as t } from "../src/mensagensServidor.ts";
const eq = (a: string, b: string, label: string) => { if (a !== b) { console.log("FAIL", label, "\n  got:", a, "\n  want:", b); process.exitCode = 1; } else console.log("ok  ", label); };
eq(t("Not authenticated", "pt"), "Não autenticado", "en->pt exact");
eq(t("Não autenticado", "en"), "Not authenticated", "pt->en exact (legacy stored)");
eq(t("Not authenticated", "es"), "No autenticado", "en->es exact");
eq(t("Not authenticated", "en"), "Not authenticated", "en->en unchanged");
eq(t("Empty file: a.pdf", "pt"), "Arquivo vazio: a.pdf", "en->pt template");
eq(t("Arquivo vazio: a.pdf", "es"), "Archivo vacío: a.pdf", "pt->es template");
eq(t("Gemini did not answer within 120s (it hung or is very slow right now). Try again or with a smaller document.", "pt"), "O Gemini não respondeu em 120s (travou ou está muito lento agora). Tente de novo ou com um documento menor.", "timeout en->pt");
eq(t('Could not evaluate this item: Gemini is temporarily overloaded (high demand on the configured model). It is not a problem with your API key — try again in a few minutes. Use "Re-evaluate" after fixing the problem.', "pt"), 'Não foi possível avaliar este item: O Gemini está temporariamente sobrecarregado (alta demanda no modelo configurado). Não é um problema com a sua chave de API — tente novamente em alguns minutos. Use "Reavaliar" depois de resolver o problema.', "RFI error nested en->pt");
eq(t('Não foi possível avaliar este item: Erro inesperado ao chamar o Gemini: boom Use "Reavaliar" depois de resolver o problema.', "en"), 'Could not evaluate this item: Unexpected error calling Gemini: boom Use "Re-evaluate" after fixing the problem.', "RFI error pt->en with raw inner");
eq(t("a.pdf: Empty file: a.pdf\nb.pdf: Arquivo vazio: b.pdf", "es"), "a.pdf: Archivo vacío: a.pdf\nb.pdf: Archivo vacío: b.pdf", "per-document lines mixed");
eq(t("PoC sem título", "en"), "Untitled PoC", "default title pt->en");
eq(t("Untitled RFI", "pt"), "RFI sem título", "default title en->pt");
eq(t("some raw text we do not know", "es"), "some raw text we do not know", "unknown untouched");
eq(t("", "en"), "", "empty");

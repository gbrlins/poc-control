# Plan: rename the whole codebase to English (approved 2026-11-18, not started)

## Context

poc-control started as a Portuguese-speaking project. It will now be maintained by programmers who do not read Portuguese, and
the app itself defaults to English. Today the Portuguese is in every layer, not only in file names:

| Layer | What is Portuguese today (measured on `feature/sync/gbrlins-v2`) |
|---|---|
| Files and folders | ~60 of 209 tracked files: `api/app/procedimentos/`, `classificacao/`, `licitacoes/`, `pocs/apresentacao.py`, `roteiro.py`, `planilha_import.py`, `traducao_cache.py`…; `web/src/features/executar-poc/`, `planejar-poc/`, `Procedimentos.tsx`, `MinhaConta.tsx`, `mensagensServidor.ts`…; test files; Alembic file names |
| Code identifiers | ~1,760 distinct Python identifiers, a large share Portuguese (`procedimento`, `itens`, `idioma`, `sessao`, `titulo`, `extracao`, `historico`…); 22 test files named and written in Portuguese |
| Comments and docs | ~800 comment/docstring lines in `api/app` (98% Portuguese), 75 in tests, 129 in the planner, `CLAUDE.md` (604 lines, mostly Portuguese), `docs/sincronizar-gbrlins-poc-control.md` (obsolete) |
| API | URL segments `itens`, `sessoes`, `notas`, `anexos`, `documentos`, `procedimentos`, `licitacoes`, `classificar`, `reavaliar`, `reextrair`, `roteiro`, `apresentacao`…; ~220 Portuguese JSON fields in 4 schema files, mirrored by 37 interfaces / 284 fields in `web/src/api.ts` |
| Database | ~15 of 19 tables (`procedimentos`, `itens`, `classificacoes`, `sessoes`, `notas`, `anexos`, `licitacoes`…), ~150 of 245 columns, 13 enum types whose stored values are Portuguese (`rascunho/validado`, `verde/amarelo/vermelho`, `atende/nao_atende`, `pendente/em_andamento`…) |
| Frontend internals | 554 i18n keys per language with Portuguese prefixes (`procedimentos.`, `itemRow.`, `pocDetail.`…), CSS classes, component names |
| Config | env vars `SYNC_SERVIDOR_URL/EMAIL/SENHA`, `EXTRACAO_RECUPERAR_NO_INICIO` |
| Gemini prompts | ~20 instructions in `api/app/gemini.py` written in Portuguese |

## Decisions already taken (from the user)

1. **Scope: everything, staged**, each stage its own merge request, the database last, with a rehearsal on real data.
2. **Gemini prompts: translate**, as a separate final step with a before/after output check.
3. **Instances: only the Raspberry Pi and local machines.** No long-lived API aliases are needed. Old exported JSON files must
   still import (cheap and kept), and the Pi's `.env` is updated at deploy time.

## What stays Portuguese on purpose

- Everything the user reads in the **Portuguese UI** (the `pt` dictionary in `i18n.tsx`, `pt` report labels, the Portuguese seed
  procedure texts, sample PoC files). Portuguese is a language of the product, not a naming problem.
- **Brazilian proper nouns and external wire formats**: `PNCP` (the tender portal's API field names stay inside
  `tenders/pncp_client.py`, mapped to English names right at the boundary), `CNPJ` (kept as a term: `agency_cnpj`), "edital" in
  UI text.
- Historical Alembic revisions keep their contents (they describe the past); only their file names change.

## Method (applies to every stage)

- **One rename map is the single source of truth**: `docs/glossary.md` (Portuguese -> English term, with the decision for
  ambiguous ones). Codemods read it; humans review it once, up front. Core terms (proposal):
  procedimento→procedure, classificacao→classification, semáforo flag (`verde/amarelo/vermelho`)→`green/yellow/red`,
  aderencia→fit, conducao→led_by, sessao→session, nota→note, anexo→attachment, prerequisito→prerequisite, fase→phase,
  responsavel→owner, criado_por→created_by, licitacao→tender, orgao→agency, documento→document, origem_conhecimento→
  knowledge_origin, idioma/idiomas→language/source_languages, traducoes→translations, fontes→sources, veredito→verdict
  (`atende→meets`, `atende_parcial→partially_meets`, `nao_atende→does_not_meet`, `sem_evidencia→no_evidence`),
  rascunho/validado→draft/validated, ativa/concluida/suspensa→active/completed/suspended, extraindo/pronto/erro→
  extracting/ready/error, pendente/em_andamento/concluido/bloqueado/nao_aplicavel→pending/in_progress/completed/blocked/
  not_applicable, roteiro→day_script, apresentacao→presentation, resumo→summary, planilha→spreadsheet, exclusao→deletion,
  recuperacao→recovery, relatorio→report, visao→view, titulo→title, descricao→description, criterio_aceite→
  acceptance_criterion, cliente→customer, escopo→scope, categoria→category, justificativa→justification.
- **Tools, not hand edits**: `git mv` for files/folders (history follows); `libcst`/`rope` for Python identifiers and imports;
  the TypeScript compiler API (`ts-morph`) for TS identifiers; a small script for i18n keys and CSS classes. Every stage is a
  scripted, re-runnable change, committed as pure renames separate from any logic change.
- **Safety nets built first (Stage 0)**: (a) an OpenAPI snapshot test, (b) a `pg_dump --schema-only` snapshot, (c) the full test
  suites, (d) a frontend smoke checklist. Stages 1-3 must leave (a) and (b) **byte-identical**: that is the proof that nothing
  observable changed. Stage 4 changes (a) on purpose, Stage 5 changes (b) on purpose, and each diff must equal the rename map.
- **Decouple code from storage**: during Stages 2-4 the Python names change while the stored names stay, using
  `mapped_column("titulo", ...)` (explicit column name) and Pydantic `Field(alias=...)`/`serialization_alias`. This lets the code
  be renamed and reviewed long before any data migration.
- **Avoid conflicts**: announce a short freeze to anyone else committing; keep each stage's branch short-lived; list the mass-rename
  commits in `.git-blame-ignore-revs` so `git blame` stays useful.

## Stages (each = one MR, independently valuable, can stop after any)

### Stage 0 - Foundations (no behaviour change)
- Write `docs/glossary.md` and get it reviewed.
- Add `api/tests/test_openapi_snapshot.py` (golden `openapi.json`), a schema-snapshot script (`scripts/schema-snapshot.sh`), and a
  frontend check that every `t("key")` exists in all three i18n dictionaries (also useful long-term).
- Record the baseline: 124 DB tests + 51 unit tests + 3 front checks + `tsc` + build all green.
- Rehearsal data: clone the old volume (`poc-control_pgdata`, revision 0024, 1 PoC / 3 RFIs) again for Stage 5; plan a Pi backup.
- Effort: ~0.5 day.

### Stage 1 - Files, folders, modules (pure moves)
- API: `procedimentos/`→`procedures/`, `classificacao/`→`classification/`, `licitacoes/`→`tenders/`; `pocs/apresentacao.py`→
  `presentation.py`, `roteiro.py`→`day_script.py`, `documentos.py`→`documents.py`, `planilha_import.py`→`spreadsheet_import.py`,
  `resultados.py`→`results.py`, `traducao.py`→`translation.py`; top level: `categorias`→`categories`, `idioma`→`language`,
  `exclusao`→`deletion`, `recuperacao`→`recovery`, `relatorio_i18n`→`report_i18n`, `relatorio_visao`→`report_view`,
  `traducao_cache`→`translation_cache`, `url_real`→`real_url`; scripts (`limpar_orfaos`→`clean_orphans`); Alembic file names
  (revision ids untouched); test files.
- Web: `features/executar-poc`→`features/poc-execution`, `planejar-poc`→`poc-planning`, `licitacoes`→`tenders`; components
  (`ProcedimentoView`→`ProcedureView`, `MinhaConta`→`MyAccount`, `Usuarios`→`Users`, `mensagensServidor.ts`→`serverMessages.ts`,
  `rascunhoUpload.ts`→`uploadDraft.ts`, `ProgressoEnvio`→`UploadProgress`…); the `@/` alias keeps imports stable.
- Also update: `docker-compose.yml` (seed mount), `web/Dockerfile`, `CLAUDE.md` paths, `docs/diagrams/README.md`, CODEOWNERS.
- Verify: `git diff -M` shows only renames + import lines; OpenAPI and schema snapshots identical; all tests green. Effort: ~1 day.

### Stage 2 - Code identifiers (no wire, no storage change)
- Python: functions, classes, variables, arguments, test names (`test_traduz_so_o_que_a_ia_escreveu…` → English sentences);
  SQLAlchemy attributes keep their column names via `mapped_column("<old>")`; Pydantic fields keep JSON names via aliases.
- TypeScript: components, hooks, props, local names; planner internals where Portuguese (the planner is mostly English already).
- Env vars: `SYNC_SERVER_URL/EMAIL/PASSWORD`, `EXTRACTION_RECOVER_ON_START`: new names read first, old names still accepted with a
  logged warning for one release (protects the Pi's `.env`); documented in `DOCKER.md` and `.env.example`.
- Verify: snapshots identical; tests green. Effort: ~2-3 days (tooling plus review of the codemod output).

### Stage 3 - Comments, docstrings, log messages, docs
- Translate ~900 Portuguese comment/docstring lines, log messages (`logger.*`), and test docstrings to English, module by module.
- `CLAUDE.md` -> English (it is the maintainers' and the AI agent's primary doc); delete the obsolete
  `docs/sincronizar-gbrlins-poc-control.md`; `poc-planner/README-VENDORED.md` in English. Add `CONTRIBUTING.md`: English identifiers
  and comments, UI text only through the three i18n dictionaries.
- Verify: no behaviour change (snapshots, tests). Effort: ~2-3 days.

### Stage 4 - API paths and JSON field names (the wire contract)
- URL segments: `itens`→`items`, `sessoes`→`sessions`, `notas`→`notes`, `anexos`→`attachments`, `documentos`→`documents`,
  `procedimentos`→`procedures`, `licitacoes`→`tenders`, `classificar`→`classify`, `reavaliar`→`re-evaluate`,
  `reextrair`→`re-extract`, `roteiro`→`day-script`, `apresentacao`→`presentation`, `exportar-json`→`export-json`, etc.
- JSON fields in the four schema files and `web/src/api.ts` (37 interfaces); the planner connector (`serverProcClean`,
  `serverProcToLib`), `sync/client.py`, `docs/procedure-schema.md`, and the exported formats (procedure JSON, `resultados`):
  bump `schema` to 2. **Old exports still import**: the importers accept the legacy field names (kept in one `LEGACY_FIELDS` map).
- `web/tests/apiPaths.check.mts` (already exists) must pass; the OpenAPI snapshot is regenerated and its diff reviewed against the map.
- Effort: ~2 days.

### Stage 5 - Database (tables, columns, enum values)
- One Alembic revision `0035_english_names`: `op.rename_table`, `op.alter_column(new_column_name=...)`,
  `ALTER TYPE ... RENAME VALUE` for the enum values and `RENAME` of the enum types; rename indexes/constraints too, so that
  `alembic check` shows no diff. Then remove the `mapped_column("<old>")` shims. A reversible `downgrade()`.
- **Rehearse before the Pi**: (1) fresh database to head; (2) the cloned October volume (0024→0035); (3) a copy of the Pi's data.
  Compare row counts and per-table checksums before/after, and the schema dump against the map.
- Update seed data, `import_seed.py`, `clean_orphans.py`, and any raw SQL.
- Pi rollout: backup (`pg_dump`), no extraction running (an API restart kills it), `scripts/update.sh`, check `alembic current`.
  Rollback = `alembic downgrade` or restoring the dump. Effort: ~1-2 days including rehearsal.

### Stage 6 - Frontend internals
- i18n keys (554 per language) and CSS classes via the map, guarded by the Stage 0 key-existence check; route names are already English.
- Effort: ~1 day.

### Stage 7 - Gemini prompts
- Translate the ~20 prompts in `api/app/gemini.py` to English with an explicit "answer in <language>" parameter (already there).
- **Before/after check with a real key**: run extraction, classification, RFI evaluation, guided draft and summaries on the seed
  procedures, the sample PoCs and one RFI with the old and new prompts; compare structure and quality; keep a prompt only if it is as
  good. Uses the user's Gemini quota. Effort: ~1 day plus review.

### Stage 8 - Guardrails
- A small script and CI/pre-commit hook that flags known Portuguese terms from the glossary in new identifiers and file names
  (allow-list for the Portuguese UI dictionary and seed content). Effort: ~0.5 day.

Rough total: ~2 working weeks for one person, most of it review. Stages 1-3 are low risk and deliver most of the value for
maintainers; Stages 4-5 carry the real risk (contract and data).

## Risks and mitigations

- **Data loss/corruption at Stage 5**: rehearsal on real data clones, checksums, backup, reversible migration, no deploy during an extraction.
- **Hidden coupling to names** (strings in the planner, SQL in scripts, enum values compared as text, docs): the snapshots, the
  frontend key check, `apiPaths.check.mts`, and a repo-wide search for each old term after each stage.
- **Merge conflicts with other contributors** (Gabriel and others): freeze windows, small MRs, quick merges, blame-ignore list.
- **Prompt regression**: Stage 7 is isolated and gated by the before/after check.
- **Pi `.env` breakage**: old env var names still accepted with a warning for one release.
- **Time**: do not start before the global-SAs demo; nothing here is needed for it.

## Verification (end to end, every stage)

1. `cd api && pytest` (51 unit + 124 DB tests in the container), `cd web && npx tsc --noEmit && npm run build`, the three front checks.
2. OpenAPI snapshot and schema snapshot: identical for Stages 1-3, diff == rename map for Stages 4-5.
3. Local stack smoke test in the browser (login, Home, planner, enable execution, PoC page in 3 languages, RFI list and create, procedures
   import/export, reports) plus the Stage 5 migration rehearsal on the cloned real database.
4. `git grep` for the retired Portuguese terms of the stage returns only allowed places (UI dictionary, seed content, legacy-import map).

## Critical files

`api/app/models.py` (columns and enums), `api/app/*/schemas.py` and `web/src/api.ts` (wire), `api/app/*/router.py` (paths),
`web/src/i18n.tsx` (keys), `poc-planner/index.html` (connector), `api/app/gemini.py` (prompts), `api/alembic/versions/` (new revision),
`docker-compose.yml`, `.env.example`, `DOCKER.md`, `CLAUDE.md`, plus the new `docs/glossary.md`.

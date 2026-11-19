# Plan: complete UI/UX review (planned 2026-11-18, not started)

## Context

poc-control grew from a prototype into a tool SAs use every week: a React shell (Home hub, PoCs, RFIs, procedures, tenders, account)
plus the planner, a separate single-file HTML app (about 4,600 lines) embedded in an iframe. Several authors built the two halves at
different times. Testing the 2.1.x builds exposed usability problems that no single bug fix addresses (two procedure stores that look
like duplicates, "Enable execution" buried in the planner Summary, inconsistent Home tiles, uploads that gave no feedback). The app now
also has a global, English-first audience. The review should find the rest systematically and fix the highest-value problems.

**Decisions from the user:** priority = the **daily SA workflow** (plan -> execute -> report, RFI triage); evidence = **expert review plus 2-3
SA sessions**; targets = **WCAG 2.1 AA on the shell, best effort on the planner**, laptop, tablet and 200% zoom (phones only where cheap);
output = **findings, a ranked backlog, then fix the top items in small merge requests**. Nothing starts before the global-SAs demo.

## What exists today (measured)

- **Shell screens (13 routes)**: Home hub + "Projects and PoCs" list, PoCs list/new/detail, RFIs list/new/detail, Procedures list/new/import/detail,
  Tenders, Users, My account, Login. Top bar only (home, theme, language, account); no navigation menu. `PocDetail.tsx` is 1,855 lines, `RfiDetail.tsx` 641.
- **Planner**: dashboard (hidden when embedded), 8 wizard steps, Kickoff checklist tab, Library, Import; own header/toolbars and its own
  inline 3-language strings. Visual conventions differ from the shell.
- **Components**: no shared Button, Dialog, Table or Toast; two hand-rolled modals; 4 native `window.confirm` in the shell and 7 in the planner;
  241 inline `style={{}}`; one 1,552-line stylesheet with 4 breakpoints (the planner has 1).
- **Accessibility signals (shell TSX)**: 7 `aria-*`, 3 `role=`, 56 `<label>` but only 19 `htmlFor`, 6 click handlers on non-buttons; planner: 1 `aria`, 4 click handlers on div/span.
- **Good already**: i18n discipline (essentially no hard-coded user-visible text), light/dark themes, language switch, upload progress, typed-title delete confirmation (`DangerZone`).
- **Responsive probe at 390 px** (Home, PoC detail): both overflow horizontally (399 > 373 px); the account button is cut off in the top bar;
  the fixed build-info footer overlaps content. Tiles stack and tabs scroll, so it degrades reasonably.
- **Findings from testing already on the list**: duplicate-looking procedure stores; buried execution action; inconsistent tiles (form vs list);
  planner and shell differ visually; planner shows API errors untranslated; an API restart silently kills running analyses; executive summary and
  session screens show untranslated stored text; browser-native validation messages in the browser's language.

## Method

**Phase A - Prepare (~0.5 day).** Personas: SA (daily), admin, first-time viewer. Core journeys (the review's backbone):
J1 plan a PoC from scratch (planner, 8 steps, export); J2 import a customer document into a plan; J3 enable execution and land on the PoC page;
J4 run the PoC (status, notes, attachments, sessions, session summary, day script); J5 report (exports, presentation, executive summary);
J6 triage an RFI end to end; J7 manage procedures (local library vs server, import/export, validate a draft, guided draft); J8 account and admin
(Gemini key/model, users); J9 live tenders (beta). Rubric: Nielsen's 10 heuristics + WCAG 2.1 AA checks (keyboard, focus visibility, labels,
contrast, 200% zoom, reduced motion) + a consistency checklist (loading / empty / error / success states, destructive actions, progress
feedback, terminology, three languages). Use only sample data (`seed/poc`, sample PoCs, seeded procedures), never customer data.

**Phase B - Expert walk-through (~2-3 days).** Walk every journey in EN, PT and ES, light and dark, at 1440 / 1024 px and 200% zoom, keyboard
only, on the local stack. Run axe-core on every shell screen; do a manual accessibility pass on the planner's key steps. Record each finding in a
table: id, journey/step, screen, rule (heuristic or WCAG criterion), severity (blocker / major / minor / polish), evidence (screenshot), suggested
fix, effort (S / M / L).

**Phase C - SA sessions (~1 day plus scheduling).** 2-3 SAs, 3-4 real tasks (e.g. enable execution and find a flagged item; triage a small RFI;
start a plan from a customer document), think-aloud, notes on hesitations, wrong turns, time and success. Script, consent line and note template
prepared in Phase A. Run on the local stack (or the Pi) with sample data.

**Phase D - Synthesize (~0.5 day).** Merge and de-duplicate; rank by severity x journey importance / effort; group into themes. Deliverable:
`docs/ux-review/` with `findings.md`, `sessions.md`, `backlog.md` and a `screenshots/` folder. Review it with the user and agree the order of fixes.

**Phase E - Fix the top items (iterative, small MRs).** Start with shared foundations that many screens reuse: (1) design tokens and shared
components under `web/src/components/` (Button, Dialog/ConfirmDialog replacing `window.confirm`, Toast/inline Alert, DataTable, EmptyState,
FormField with label association; keep `ProgressoEnvio`, `BatchDocumentUploader`, `DangerZone` patterns); (2) accessibility fixes (labels, aria,
focus-visible, keyboard for clickable rows, contrast); (3) the top journey pain points from Phases B-C (for example shell/planner consistency,
navigation, status and progress feedback, splitting `PocDetail.tsx` into tab components); (4) responsive fixes (top bar overflow, footer overlay).
Planner changes stay small and targeted because it is one large file.

## Ordering with the English renaming plan (below)

Phases A-D change no code, so they can start any time after the demo. Phase E and the renaming both touch the frontend: do the rename's
Stage 0-2 (mechanical moves and identifiers) first, then Phase E on the renamed code, to avoid conflicts; Stages 3+ of the rename can run in parallel.

## Deliverables

`docs/ux-review/{findings,sessions,backlog}.md` + screenshots; a short readout for the user; then Phase E merge requests, each with
before/after screenshots in EN/PT/ES and both themes.

## Critical files

`web/src/pages/Layout.tsx` (top bar, footer), `web/src/styles.css`, `web/src/components/*`, `web/src/pages/Home.tsx` and `HomeProjetos.tsx`,
`web/src/features/*/pages/` (`PocDetail.tsx`, `RfiDetail.tsx`, uploads, procedures), `web/src/i18n.tsx`,
`poc-planner/index.html` (`renderHeader`, `renderEmbeddedToolbar`, `renderWizardNav`, `renderFooterBar`, the Summary and Tests views).

## Reuse

Existing patterns: `ProgressoEnvio`, `BatchDocumentUploader`, `DangerZone` (typed-title confirmation), the theme and language logic in `Layout.tsx`
and the `THEME_EVENT` bridge to the planner, the `web/tests/*.check.mts` style for automated checks (add an accessibility check next to them),
`docs/diagrams/` for the journeys, and the seed and sample data for the walk-through.

## Verification

- Every finding reproducible from its steps and screenshot; severity rubric applied consistently; the user spot-checks the ranking.
- After each fix MR: re-walk the touched journey; axe reports no serious/critical violations on touched shell screens; the key flows (J3, J6)
  complete keyboard-only; no horizontal scroll at 200% zoom on shell screens; EN/PT/ES and light/dark screenshots attached; `tsc`, build and the
  front checks pass; API tests unaffected.
- Compare task success and time in a small before/after run with the same 2-3 SAs for the two most important tasks.

## Risks

Sessions depend on SAs' availability; the planner is a large single file (keep edits small and checked in the browser); splitting `PocDetail.tsx`
is risky (do it behind the existing screens' behavior, tab by tab); scope creep (a ranked backlog and a cap on items per MR); conflicts with the
rename (see ordering). Estimate: Phases A-D about 5 working days including the sessions; Phase E is open-ended and driven by the backlog.

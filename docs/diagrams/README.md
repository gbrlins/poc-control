# Process diagrams (draw.io)

Open the `.drawio` files with [diagrams.net](https://app.diagrams.net) (File > Open from > Device), the desktop app, or
the "Draw.io Integration" extension for VS Code. GitLab shows them as plain XML, so use one of those to read them.
Each file has several pages (tabs at the bottom): an overview first, then one sequence diagram per phase.

| File | Pages |
|---|---|
| `poc-to-execution.drawio` | 0 Overview, 1 Plan in the planner (browser), 2 Enable execution and extract the items, 3 Traffic-light classification of an item, 4 Execute the PoC |
| `rfi-analysis.drawio` | 0 Overview, 1 Create the RFI and extract the requirements, 2 Evaluate each requirement, 3 Review, follow up and export |

Colours: red = the person, blue = browser, green = the server (API and background tasks), purple = Gemini, yellow = stored data.
In the sequence pages, a solid arrow is a call, a dashed one a return, an open head an asynchronous call (a background task
is scheduled), and the grey frames are `alt` / `opt` / `loop` blocks.

They describe what the code does as of version 2.1.2. When a flow changes, update the page that covers it. Where to look:

- PoC: `api/app/pocs/router.py` and `tasks.py` (creation, extraction, planner import), `api/app/classificacao/service.py`
  (the traffic light and the guided draft), `api/app/planner/router.py` (hydrate, history, procedure draft),
  `web/src/pages/HomeProjetos.tsx` and `poc-planner/index.html` (`execEnable`, `executionPayload`).
- RFI: `api/app/rfi/router.py`, `tasks.py` (extraction and the evaluation loop), `service.py` (the three evidence steps),
  `api/app/recuperacao.py` (what a restart does), `web/src/features/rfi/pages/`.

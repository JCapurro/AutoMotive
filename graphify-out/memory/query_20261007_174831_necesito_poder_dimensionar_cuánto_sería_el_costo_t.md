---
type: "query"
date: "2026-10-07T17:48:31.102021+00:00"
question: "Necesito poder dimensionar cuánto sería el costo técnico y económico de mover todo el worker a algún VPS."
contributor: "graphify"
outcome: "useful"
source_nodes: ["main.py", "_mercadolibre_browser.py", "crawl.py", "install-tasks.ps1"]
---

# Q: Necesito poder dimensionar cuánto sería el costo técnico y económico de mover todo el worker a algún VPS.

## Answer

Assessment dated 2026-10-07. Query expanded with graph vocabulary: worker scheduler browser mercadolibre llm claude config crawl windows. Sources main.py, _mercadolibre_browser.py, config.py and install-tasks.ps1 identify Python worker loops, external API LLM, hosted DB, Windows supervision and persistent headed Chrome. Proposed Linux x86 VPS with 4 vCPU/8GB; adapt supervision/watchdog/backup and remote graphical access; recreate source sessions and validate on candidate IP before cutover. Engineering estimate 16-28 hours, subject to source access validation; 48-72 hours observation. VPS budget 15-25 USD monthly, excluding existing DB/web/API/email charges, operator time and any subsequently required proxy service. Single live memory sample approximately 570 MB including descendants is not peak capacity proof. Keep one complete worker active at cutover; crawl loop is not protected for multiple replicas.

## Outcome

- Signal: useful

## Source Nodes

- main.py
- _mercadolibre_browser.py
- crawl.py
- install-tasks.ps1
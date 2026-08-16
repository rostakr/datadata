# A0 — Stav projektu a integrační fronta

Aktualizováno: 2026-08-16

Tento dokument je operativní A0 přehled. Autoritativní produktové a architektonické zásady jsou v `PROJECT_SPEC.md`.

## Ověřený baseline

- Cílový repozitář: `rostakr/datadata`.
- Default branch: `main`.
- Baseline commit před touto A0 změnou: `f58cdeeff494464f69fcc3713dcdec0db9258544`.
- Přiložený projektový archiv a baseline `main` mají shodný Git tree SHA `6d11a237325e88eebb49fecea46bcd859e6f1330`.
- Lokální core suite na stejném snapshotu: `241 passed` při vynechání `tests/test_a6_app.py`.
- Kompletní lokální suite se v aktuálním A0 runtime zastaví při collection A6 testu, protože runtime nemá balík `streamlit`. To je environmentální blokace, nikoli potvrzená chyba A6.
- GitHub Actions na baseline SHA evidoval pouze Pages deployment; A0 proto neoznačuje aktuální `main` za release-validovaný, dokud neproběhne vlastní A7 exact-SHA release gate.

## Stav modulů

### A1 — Import dat

Implementace je na `main`. Další release práce musí zachovat read-only snapshot, source reconciliation a explicitní accounting každého importovaného záznamu.

### A2 — Normalizace a databáze

Canonical SQLite, lossless membership a provenance jsou na `main`. A2 je autoritativní zdroj normalizovaných dat pro další vrstvy.

### A3 — Zpracování a třídění

Processing a participant resolution jsou na `main`. A3 nesmí zavádět paralelní message/participant model.

### A4 — Analytický engine

Deterministické metriky a kandidátní vzorce jsou na `main`. A4 výstupy nesmí být prezentovány jako psychologická interpretace.

### A5 — AI analýza

Bounded context, evidence chain a provenance integrace jsou na `main`. AI musí pracovat pouze nad vybraným kontextem a doložitelnými kandidáty/metrikami.

### A6 — Rozhraní

Streamlit UI a evidence/provenance bridge jsou na `main`. A6 production packet musí fail-closed při chybějící nebo stale source provenance.

### A7 — QA / validace

Independent oracles a exact-SHA release harness jsou v repozitáři. Aktuální A0 priorita je ověřit, že se tento harness skutečně spouští v novém cílovém repozitáři a že výsledný SHA má `release_ready=true`.

## Aktuální integrační fronta

1. **A0 governance + release wiring**
   - přidat autoritativní `PROJECT_SPEC.md`,
   - držet tento status dokument aktuální,
   - zahrnout governance změny do A7 release workflow triggerů.

2. **A7 exact-SHA validace na `rostakr/datadata`**
   - core full-repository pytest v CI,
   - compileall,
   - A5 live evidence/provenance probe,
   - A6 live A2→A6→A5 provenance fixture,
   - aggregate verdict se stejným `GITHUB_SHA`,
   - žádné prohlášení release-ready bez artefaktu s `release_ready=true`.

3. **A0 real Apple archive gate**
   - až po zeleném synthetic/current-main gate,
   - spustit lokálně nad skutečným `chat.db`,
   - zdroj před/po musí zůstat byte-identical,
   - target conversation se vybírá pouze exact resolverem nebo explicitním `--conversation-id`,
   - lokální reporty a inventáře se nepublikují do veřejného GitHubu.

4. **A6 praktická UX matice**
   - desktop,
   - iPhone portrait,
   - iPhone landscape,
   - skutečné zobrazení evidence a message drill-down,
   - až nad release-validovaným SHA.

## Release pravidlo A0

A0 může označit SHA za integračně připravený pouze tehdy, když:

- všechny povinné A7 komponenty jsou `VALID`,
- všechny reporty mají přesně stejný `contract_sha`,
- aggregate verdict obsahuje `release_ready=true`,
- neexistuje nevyřešená data-integrity nebo provenance chyba.

Skutečný osobní archiv je samostatná praktická validační vrstva a nikdy se nenahrazuje syntetickým CI fixturem.

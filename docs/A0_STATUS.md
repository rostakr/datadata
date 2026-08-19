# Operativní stav projektu — Runtime v2

Aktualizováno: 2026-08-20

Tento dokument je operativní stav, nikoliv druhá architektonická specifikace. Autorita projektu je `PROJECT_SPEC.md`.

Historické označení A0–A7 zůstává pouze pro orientaci v existujícím kódu a CI workflow během migrace. Produkční runtime je Runtime v2.

## Cílový repozitář

- Repository: `rostakr/datadata`
- Default branch: `main`
- Repozitář je veřejný.
- Skutečný osobní archiv, zprávy, přílohy, lokální real-archive reporty, evidence packy, AI cache a secrets se nesmí commitovat.

Exact SHA se zde nehardcoduje. Release autoritu má Git historie a exact-SHA QA workflow konkrétního commitu.

## Ověřený základ

Před migrací Runtime v2 prošel lokální real-archive vertical slice těmito vrstvami:

- source SQLite integrity,
- read-only import/reconciliation,
- canonical SQLite ingest,
- membership/source provenance,
- processing/participant resolution,
- deterministická analytika,
- canonical UI read model,
- browser matrix,
- exact-SHA QA gates.

Runtime v2 tyto ověřené vrstvy nepřepisuje. Mění zejména AI execution boundary a hlavní UI tok.

## RAW completeness vs. analysis readiness

RAW gate report zůstává autoritativní a nikdy se nepřepisuje.

Známá soukromá media limitation zůstává external-data omezením; systém nesmí tvrdit, že analyzoval fyzický obsah příloh, které nejsou na lokálním stroji dostupné.

Canonical text/metadata readiness a fyzická attachment completeness jsou nadále oddělené verdicts.

## Produkční Runtime v2

Nová cesta:

`RAW → CANONICAL STORE → SIGNALS → EVIDENCE PACKS → INTERPRETER → ANALYSIS STORE → UI`

### Canonical Store

Stávající canonical SQLite a provenance zůstávají zdrojem pravdy. AI nevytváří canonical identitu ani source provenance.

### Signal Engine

Stávající deterministické analytické views/findings se používají jako candidate index. AI není potřeba pro metriky, změny rytmu ani další deterministické signály.

### Evidence Compiler

Selected evidence se dělí podle skutečné velikosti provider payloadu (`max_input_chars`), nikoli podle fixního počtu zpráv.

Provider vidí pouze:

- krátké `E1…En` labels,
- sender,
- timestamp,
- text,
- volitelnou otázku.

Provider nevidí:

- canonical message IDs,
- membership IDs,
- source record keys,
- source snapshot keys,
- parser/import provenance.

Tato data zůstávají v lokální mapě a materializují se až po inference.

### Interpreter

Produkční Interpreter:

- používá jeden inference call na evidence pack,
- používá Ollama JSON Schema structured output,
- u Qwen3 produkční profil vypíná thinking,
- používá deterministickou teplotu 0,
- omezuje maximální modelový output,
- neprovádí automatický repair inference,
- validuje všechny `E-label` reference proti lokálnímu packu,
- po validaci host aplikace připojí canonical evidence a provenance.

Více packů se standardně skládá deterministicky; není vyžadován další synthesis call.

## Hlavní UI

Production `app.py` používá `a6/runtime_ui.py`.

Běžný tok má tři části:

1. **Konverzace** — canonical read model bez AI.
2. **Signály** — deterministické analytické kandidáty.
3. **Interpretace** — ruční nebo signal-based evidence → compact Runtime v2 inference → evidence drill-down.

Starý `a6.app_legacy` zůstává pouze jako migrační/reference kód a není hlavním Streamlit entrypointem.

## Legacy A5

`src/analyzazprav/a5_ai/` obsahuje původní orchestrátor, ContextBuilder, repair/cache/chunk synthesis a staré integrační adaptéry.

Tyto komponenty již nejsou production execution path. Dočasně se zachovávají kvůli regresním testům a postupné migraci. Sdílený `providers/OllamaProvider` zůstává použitelný i Runtime v2.

Nové funkce se do legacy orchestrátoru nepřidávají.

## Runtime v2 live acceptance

Nový fyzický gate:

```bash
make runtime-accept-local \
  DATABASE=/cesta/messages.sqlite \
  PACKET=/cesta/a5-context.json \
  MODEL=qwen3:1.7b
```

Dočasný alias `make a5-accept-local` spouští tentýž Runtime v2 gate, nikoli starý A5 orchestrátor.

`PASS` vyžaduje:

- validní packet/canonical provenance,
- evidence pack v provider budgetu,
- skutečný lokální Ollama inference,
- validní structured model output,
- validní E-label evidence,
- lokální materializaci canonical evidence,
- pouze `PASS` provenance reconciliation.

Výstup gate je privacy-safe a nesmí obsahovat message text, IDs, source keys ani lokální paths.

Podrobnosti: [`A5_LIVE_ACCEPTANCE.md`](A5_LIVE_ACCEPTANCE.md).

## Aktuální integrační fronta

Pro Runtime v2 zbývá před definitivním fyzickým release closure:

1. sloučit Runtime v2 pouze po zeleném repository CI a browser smoke,
2. na trusted lokálním stroji stáhnout/použít výsledný exact main SHA,
3. spustit jeden malý reálný Runtime v2 live acceptance,
4. získat privacy-safe `verdict=PASS` a process exit `0`,
5. teprve potom označit nový Interpreter flow za fyzicky ověřený.

Předchozí neúspěšné dlouhé běhy legacy A5 se nepoužívají jako release evidence pro Runtime v2.

## QA pravidlo

Release commit musí mít:

- kompletní repository tests/compile,
- canonical/provenance fixtures,
- Runtime v2 evidence/interpreter tests,
- Streamlit browser viewport smoke,
- exact-SHA aggregate QA verdict,
- lokální real-archive correctness bez publikace osobních dat.

Modelový timeout nesmí invalidovat Canonical Store ani Signal Engine. AI je interpretační enrichment, ne dependency datové správnosti.

## Hlavní zásada

**Celý archiv zpracuje program. AI dostane jen malý důkazní balíček a pouze jej interpretuje.**

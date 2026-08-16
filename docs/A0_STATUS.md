# A0 — Stav projektu a integrační fronta

Aktualizováno: 2026-08-16

Tento dokument je **operativní stav**, nikoliv druhá architektonická specifikace. Autorita projektu je `PROJECT_SPEC.md` v kořeni repozitáře.

## Cílový repozitář

- Repository: `rostakr/datadata`
- Default branch: `main`
- Repozitář je veřejný: skutečný osobní archiv, zprávy, přílohy, lokální real-archive reporty a secrets se nesmí commitovat.

## Aktuální synteticky ověřený baseline

- Ověřený SHA: `324a9237f54e1a3f3b29cffb0f4a169c22905825`.
- GitHub Actions run: `A7 current-main release gate` #21 (`31955109743`).
- Workflow conclusion: `success`.
- `core = VALID`.
- `A5 = VALID`.
- `A6 = VALID`.
- Všechny component `contract_sha` odpovídají přesně `324a9237f54e1a3f3b29cffb0f4a169c22905825`.
- `issues = []`.
- `overall_verdict = VALID`.
- `release_ready = true`.

Tento verdict prokazuje definovaný syntetický exact-current-checkout A1–A7 integrační gate. **Neprokazuje úplnost ani kompatibilitu konkrétního skutečného Apple Messages archivu.**

### Data-correctness invariants zahrnuté v baseline

- tri-state `is_from_me` se zachovává; unknown se nesmí převést na incoming,
- sender identity se zachovává nezávisle na neznámém směru,
- UTC mikrosekundy používají přesnou integer/timedelta aritmetiku bez float-roundingu,
- provenance a conversation membership se musí zachovat přes A2→A6→A5,
- chybějící/stale provenance je fail-closed,
- A7 current-main release workflow se spouští pro každý PR a každý push do `main`.

## Řídicí hierarchie

1. `PROJECT_SPEC.md`
2. canonical kontrakty v `docs/`
3. A0/A7 release a validační dokumentace
4. `docs/agents/*.md`
5. ostatní dokumentace
6. historické návrhy

`docs/PROJECT_SPEC.md` je pouze pointer na root specifikaci a nesmí se rozvíjet jako paralelní master dokument.

## Stav modulů

### A1 — Import dat

Implementace je na `main`. Povinné invariants: read-only source, explicitní source identity, accounting každého vstupního záznamu a reconciliation.

### A2 — Normalizace a databáze

Canonical SQLite, lossless membership, provenance a přesná práce s časem jsou na `main`. A2 je autorita canonical modelu pro A3–A7.

### A3 — Zpracování a třídění

Processing, sessions/threads a participant resolution jsou na `main`. A3 vytváří pouze derived struktury a nesmí zavést paralelní message/participant model.

### A4 — Analytický engine

Deterministické metriky a kandidátní vzorce jsou na `main`. A4 nesmí maskovat interpretaci jako metriku.

### A5 — AI analýza

Bounded context, evidence chain a provenance integrace jsou na `main`. AI pracuje pouze nad relevantním kontextem a musí explicitně oddělit fakta, metriky, vzorce, interpretaci a nejistotu.

### A6 — Rozhraní

Streamlit UI a evidence/provenance bridge jsou na `main`. Production read path musí fail-closed při chybějící nebo stale provenance a umožnit drill-down z výsledku na evidence/source.

### A7 — QA / validace

Independent oracles a exact-SHA release harness jsou v repozitáři. A7 je jediná vrstva oprávněná vydat strojový release verdict podle `docs/A7_RELEASE_GATE.md`.

## Aktuální integrační fronta

1. **Real Apple archive gate — nejvyšší priorita**
   - spustit lokálně nad skutečným požadovaným `chat.db`,
   - source před/po musí zůstat byte-identical,
   - ověřit A1 source reconciliation,
   - ověřit A2 canonical integrity/provenance,
   - ověřit A3 processing a participant resolution,
   - ověřit A4 deterministic analytics,
   - ověřit A5 bounded evidence/provenance,
   - ověřit A6 production packet + evidence drill-down,
   - target conversation vybírat pouze exact resolverem nebo explicitním `--conversation-id`,
   - žádné osobní reporty, inventories, zprávy ani přílohy do veřejného GitHubu.

2. **Vyřešit všechny real-archive quality stavy**
   - `INVALID` blokuje pokračování,
   - `NEEDS_REVIEW` se musí explicitně posoudit a uzavřít,
   - MVP release candidate vyžaduje odpovídající real-archive verdict podle `docs/A0_REAL_ARCHIVE_GATE.md`.

3. **A6 praktická UX validace**
   - desktop,
   - iPhone portrait,
   - iPhone landscape,
   - evidence a message drill-down,
   - provádět až nad SHA a datovým snapshotem, které prošly požadovanými gates.

4. **Průběžná exact-SHA A7 ochrana**
   - každý další PR/push musí znovu projít full repository pytest, compileall, A5 probe, A6 provenance fixture a aggregate exact-SHA verdict,
   - předchozí zelený SHA se automaticky nepřenáší na nový commit.

## Release pravidlo A0

A0 může označit SHA za synteticky integračně připravený pouze tehdy, když:

- povinné A7 komponenty jsou `VALID`,
- reporty mají stejný `contract_sha`,
- aggregate verdict obsahuje `release_ready=true`,
- neexistuje nevyřešená data-integrity/provenance chyba.

Pro **MVP release candidate** je navíc povinný real-archive gate nad skutečným cílovým archivem. A0 nesmí obejít, reinterpretovat ani ručně „přepsat“ negativní A7 nebo real-archive verdict.

## Hlavní priorita

**Syntetický vertical slice je zelený. Další krok je prokázat stejnou správnost na skutečném Apple Messages archivu bez publikace osobních dat.**

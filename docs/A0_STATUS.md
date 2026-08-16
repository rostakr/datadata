# A0 — Stav projektu a integrační fronta

Aktualizováno: 2026-08-16

Tento dokument je **operativní stav**, nikoliv druhá architektonická specifikace. Autorita projektu je `PROJECT_SPEC.md` v kořeni repozitáře.

## Cílový repozitář

- Repository: `rostakr/datadata`
- Default branch: `main`
- Repozitář je veřejný: skutečný osobní archiv, zprávy, přílohy, lokální real-archive reporty a secrets se nesmí commitovat.

## Ověřený code baseline před governance refresh

- `b87f66d5a27046c84b24f9abf65b108614c695f5`
- Merge PR #10: data-correctness hardening a release-gate hardening.
- Zachován tri-state `is_from_me`; unknown se nesmí převést na incoming.
- Sender identity se zachovává nezávisle na neznámém směru.
- UTC mikrosekundy používají přesnou integer/timedelta aritmetiku bez float-roundingu.
- A7 current-main release workflow se spouští pro každý PR a každý push do `main`.

Governance/documentation commity po tomto baseline musí samy projít standardním A7 exact-SHA gate; existence dokumentace není release verdict.

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

1. **Governance synchronizace**
   - udržet `PROJECT_SPEC.md` jako jedinou autoritu,
   - agentní prompty sladit s aktuálním kódem a canonical kontrakty,
   - nedovolit duplicitní master dokumenty.

2. **Exact-SHA A7 validace každé změny**
   - full repository pytest v CI,
   - compileall,
   - A5 evidence/provenance probe,
   - A6 A2→A6→A5 provenance fixture,
   - aggregate verdict na stejném `GITHUB_SHA`,
   - žádné `release-ready` tvrzení bez `release_ready=true`.

3. **Real Apple archive gate**
   - spouštět lokálně nad skutečným `chat.db`,
   - source před/po musí zůstat byte-identical,
   - conversation vybírat exact resolverem nebo explicitním `--conversation-id`,
   - žádné osobní reporty/inventáře do veřejného GitHubu.

4. **A6 praktická UX validace**
   - desktop,
   - iPhone portrait,
   - iPhone landscape,
   - evidence a message drill-down,
   - provádět nad SHA, který prošel požadovanými datovými/QA gates.

## Release pravidlo A0

A0 může označit SHA za integračně připravený pouze tehdy, když:

- povinné A7 komponenty jsou `VALID`,
- reporty mají stejný `contract_sha`,
- aggregate verdict obsahuje `release_ready=true`,
- neexistuje nevyřešená data-integrity/provenance chyba.

A0 nesmí sám obejít, reinterpretovat nebo ručně „přepsat“ negativní A7 verdict.

## Hlavní priorita

**Dokončit a udržovat jeden auditovatelný end-to-end vertical slice; nerozmnožovat funkcionalitu na úkor správnosti, provenance nebo validačního řetězce.**

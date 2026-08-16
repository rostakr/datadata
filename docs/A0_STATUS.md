# A0 — Stav projektu a integrační fronta

Aktualizováno: 2026-08-16

Tento dokument je **operativní stav**, nikoliv druhá architektonická specifikace. Autorita projektu je `PROJECT_SPEC.md` v kořeni repozitáře.

## Cílový repozitář

- Repository: `rostakr/datadata`
- Default branch: `main`
- Repozitář je veřejný: skutečný osobní archiv, zprávy, přílohy, lokální real-archive reporty a secrets se nesmí commitovat.

## Aktuální synteticky ověřený baseline

- Ověřený SHA: `4d8723f110d1010410e79b90f558b99d61054e96`.
- A6 `full-suite-and-smoke` na tomto exact SHA: `success`.
- A7 `current-main release gate` na tomto exact SHA: `success`.
- `core = VALID`.
- `A5 = VALID`.
- `A6 = VALID`.
- Aggregate exact-SHA verdict je `VALID` a release gate je zelený.

Tento verdict prokazuje syntetický exact-current-checkout A1–A7 integrační gate a browser QA nad demo daty. Neprokazuje fyzickou dostupnost všech příloh konkrétního osobního archivu.

## Reálný Apple Messages archive gate

Real-archive pipeline byla 2026-08-16 znovu spuštěna lokálně nad skutečným Apple Messages snapshotem. Žádný osobní obsah ani lokální report nebyl publikován do GitHubu.

### Ověřený textový/datový řetězec

- source `chat.db` SQLite integrity: `quick_check = ok`,
- A1: `21 705 / 21 705` message rows emitted,
- A1 message errors: `0`,
- A1 reconciliation errors: `0`,
- A7 staging: `PASS`,
- A2 canonical ingest: `PASS`,
- A2 integrity: `PASS`,
- A3 processing: `PASS`,
- A7 participant validation: `PASS`,
- A7 vertical reconciliation: `PASS`,
- A4 analytics: `PASS`,
- A5 bounded-context/provenance probe: `PASS`,
- A6 production packet/provenance probe: `PASS`.

### Cílová canonical conversation

Výběr byl proveden explicitním canonical `conversation_id`, nikoliv fuzzy/substring resolverem.

- memberships: `10 869`,
- canonical messages: `10 869`,
- unknown timestamps: `0`,
- participant cardinality: `2`,
- source conversation cardinality: `1`.

### Aktuální real-archive verdict

`NEEDS_REVIEW`, nikoliv `INVALID`.

Zbývající quality warningy:

- `3 107` attachment occurrences nelze fyzicky ověřit, protože nebyl dodán odpovídající `Attachments` root,
- `21` unsupported records jsou orphan attachment rows; nejsou to ztracené message rows.

Textová/canonical/analytická pipeline je tedy lossless pro message rows. Attachment completeness zůstává externí datový blocker, dokud nejsou dostupné fyzické attachment soubory.

## Data-correctness invariants zahrnuté v baseline

- tri-state `is_from_me` se zachovává; unknown se nesmí převést na incoming,
- sender identity se zachovává nezávisle na neznámém směru,
- UTC mikrosekundy používají přesnou integer/timedelta aritmetiku bez float-roundingu,
- JSONL čtení nesmí rozdělit platný záznam na Unicode `U+2028/U+2029`,
- provenance lookup v A2 používá index podle skutečného `(import_run_id, source_record_key)` kontraktu,
- provenance a conversation membership se musí zachovat přes A2→A6→A5,
- chybějící/stale provenance je fail-closed,
- Ollama A5 preflight kontroluje server + přesný model přes `/api/tags` před `/api/chat`,
- žádný cloud fallback není povolen,
- A7 current-main release workflow se spouští pro každý PR a každý push do `main`.

## A6 browser QA

Na `main` je automatizovaný browser gate pro:

- desktop `1440×900`,
- iPhone portrait `390×844`,
- iPhone landscape `844×390`.

Gate kontroluje Streamlit exception stav, všech 7 hlavních tabů, page-level horizontal overflow a responsive layout metrik `6 → 1 → 2`.

Na `main` je rovněž `tools/a6_real_data_ui_qa.py`, který umí stejnou matici spustit **lokálně nad explicitně zadanou canonical SQLite databází** bez uploadu osobních dat. Screenshoty s osobním obsahem jsou opt-in a defaultně se nevytvářejí.

## Stav modulů

### A1 — Import dat

**VALIDATED on real archive for message rows.** Read-only source, source identity, accounting a reconciliation prošly na skutečném snapshotu.

### A2 — Normalizace a databáze

**VALIDATED on real archive.** Canonical SQLite, lossless membership, provenance, přesné timestampy a integrity gate prošly.

### A3 — Zpracování a třídění

**VALIDATED on real archive.** Processing a participant resolution prošly bez ztráty canonical messages.

### A4 — Analytický engine

**VALIDATED on real archive.** Deterministické analytics + A7 oracle prošly.

### A5 — AI analýza

**VALIDATED for bounded-context/evidence/provenance path.** Live external/local model inference není součástí real-archive gate; Ollama readiness je nyní fail-closed přes explicitní preflight.

### A6 — Rozhraní

**SYNTHETIC BROWSER VALIDATED + REAL-DATA PROVENANCE VALIDATED.** Desktop/iPhone browser matrix je zelená na demo datech; production packet/provenance probe je zelený na reálné canonical DB. Finální interaktivní browser run nad reálnou canonical DB zůstává posledním bodem issue #6.

### A7 — QA / validace

**VALID.** Independent oracles, exact-SHA release harness a real-archive reconciliation rozhodují fail-closed.

## Aktuální integrační fronta

1. **Dokončit issue #6 — real-data A6 browser run**
   - spustit `tools/a6_real_data_ui_qa.py` nad canonical `messages.sqlite` vytvořenou real-archive gate,
   - desktop + iPhone portrait + iPhone landscape,
   - ověřit `Konverzace`, `Vybrané zprávy`, `Analýza`, evidence drill-down a žádné Streamlit exceptions,
   - osobní DB/report/screenshoty nesmí být uploadovány do veřejného GitHubu.

2. **Attachment completeness**
   - pokud budou dodány fyzické Apple Messages `Attachments`, znovu spustit real-archive gate s `--attachments-root`,
   - bez attachments root zůstává tento stav explicitně `NEEDS_REVIEW`; nesmí se přepsat na `VALID` ručně.

3. **Live local A5 execution**
   - po dostupnosti lokální Ollama instance a požadovaného modelu spustit explicitní live A5 analýzu přes nový preflight,
   - zachovat bounded context a provenance,
   - žádný cloud fallback.

4. **Průběžná exact-SHA ochrana**
   - každý další PR/push musí znovu projít full repository pytest, compileall, A5 probe, A6 provenance fixture, A6 browser gate a aggregate A7 exact-SHA verdict.

## Release pravidlo A0

A0 může označit SHA za synteticky integračně připravený pouze tehdy, když:

- povinné A7 komponenty jsou `VALID`,
- reporty mají stejný `contract_sha`,
- aggregate verdict obsahuje `release_ready=true`,
- neexistuje nevyřešená data-integrity/provenance chyba.

Pro MVP release candidate je navíc povinné:

- real-archive message/canonical/analytics řetězec bez integrity chyby,
- explicitní posouzení všech `NEEDS_REVIEW` warningů,
- praktický A6 real-data browser run,
- žádné publikování osobního archivu do veřejného repozitáře.

A0 nesmí obejít, reinterpretovat ani ručně „přepsat“ negativní A7 nebo real-archive verdict.

## Hlavní priorita

**Datový a analytický vertical slice je ověřený i na skutečném archivu. Nejbližší release úkol je dokončit lokální A6 browser QA nad touto canonical databází; přílohy zůstávají samostatný externí data-quality blocker.**

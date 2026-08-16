# A0 — Stav projektu a integrační fronta

Aktualizováno: 2026-08-16

Tento dokument je **operativní stav**, nikoliv druhá architektonická specifikace. Autorita projektu je `PROJECT_SPEC.md` v kořeni repozitáře.

## Cílový repozitář

- Repository: `rostakr/datadata`
- Default branch: `main`
- Repozitář je veřejný: skutečný osobní archiv, zprávy, přílohy, lokální real-archive reporty a secrets se nesmí commitovat.

## Aktuální synteticky ověřený baseline

- Ověřený `main` SHA: `2dba4b5835bc3f2cb6353790eba70147f90a3779`.
- PR #20 je merged; issue #18 je completed.
- A6 `full-suite-and-smoke` na tomto exact SHA: `success`.
- A7 `current-main release gate` na tomto exact SHA: `success`.
- `core = VALID`.
- `A5 = VALID`.
- `A6 = VALID`.
- Aggregate exact-SHA release verdict je zelený.
- A7 navíc ověřuje skutečný Streamlit startup/health v CI prostředí.

Tento baseline prokazuje current-checkout testy, compile, A5/A6 provenance probes, Streamlit runtime smoke a browser viewport gate nad bezpečnými testovacími daty. Neprokazuje fyzickou dostupnost všech příloh konkrétního osobního archivu.

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

Výběr byl proveden explicitním canonical conversation ID, nikoliv fuzzy/substring resolverem. Identifikátor samotný se do veřejné dokumentace nezapisuje.

- memberships: `10 869`,
- canonical messages: `10 869`,
- unknown timestamps: `0`,
- participant cardinality: `2`,
- source conversation cardinality: `1`.

### Aktuální real-archive verdict

`NEEDS_REVIEW`, nikoliv `INVALID`.

Zbývající quality warningy:

- `3 107` attachment occurrences nelze fyzicky ověřit, protože nebyl dodán odpovídající `Attachments` root,
- `21` unsupported records jsou orphan attachment rows; nejsou to ztracené message rows,
- A5 context quality warning může vzniknout, pokud evidence přesáhne běžný message limit; evidence se nesmí tiše zahodit.

Textová/canonical/analytická pipeline je lossless pro message rows. Attachment completeness zůstává externí datový blocker, dokud nejsou dostupné fyzické attachment soubory.

## Private real-data interaction/evidence audit

Po merge PR #20 byl lokálně nad private canonical SQLite proveden data-level audit odpovídající ne-browser části issue #6. Report zůstal pouze lokální a obsahoval jen statusy/počty.

Výsledek: `PASS`.

- target memberships: `10 869`,
- target canonical messages: `10 869`,
- unknown timestamps: `0`,
- deterministicky zúžené období: `5 435` message rows,
- A4 metrics: available,
- A4 findings: available,
- evidence-bearing finding: resolvable,
- current source provenance pro vybranou evidence: complete,
- production A6→A5 packet provenance: complete,
- A5 packet adapter: validated bez provider callu,
- exact materialized evidence snapshot reconciliation: `PASS`,
- syntetický provenance drift: `STALE`,
- syntetická missing current evidence: `FAIL`,
- semantic separation contract: `PASS` pro metric evidence / Pozorování / Interpretace / Vzorce / Alternativní vysvětlení / Nejistoty.

Tento audit **nenahrazuje fyzický Streamlit browser run nad reálnou DB**. Potvrzuje však, že real-data selection, period filtering, A4/evidence/provenance a A5 packet hranice jsou na skutečných canonical datech funkční a fail-closed.

## Data-correctness invariants zahrnuté v baseline

- tri-state `is_from_me` se zachovává; unknown se nesmí převést na incoming,
- sender identity se zachovává nezávisle na neznámém směru,
- UTC mikrosekundy používají přesnou integer/timedelta aritmetiku bez float-roundingu,
- JSONL fyzické record framing musí zachovat `U+2028/U+2029` uvnitř message textu bez rozbití JSONL,
- provenance lookup v A2 používá index podle `(import_run_id, source_record_key)`,
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

`tools/a6_real_data_ui_qa.py` po PR #20 navíc podporuje lokální real-data interaction/evidence matici:

- deterministický nebo explicitní local-only conversation target,
- period check,
- A4 metrics/findings,
- evidence + source provenance,
- A6→A5 packet validation bez provider callu,
- browser flow přes `Konverzace`, `Grafy`, `Významná období`, `Vybrané zprávy`, `Analýza`,
- privacy guard reportu,
- stale/missing provenance fail-closed regression contract,
- screenshoty s osobním obsahem jsou opt-in.

## Stav modulů

### A1 — Import dat

**VALIDATED on real archive for message rows.** Read-only source, source identity, accounting a reconciliation prošly na skutečném snapshotu.

### A2 — Normalizace a databáze

**VALIDATED on real archive.** Canonical SQLite, lossless membership, provenance, přesné timestampy a integrity gate prošly.

### A3 — Zpracování a třídění

**VALIDATED on real archive.** Processing a participant resolution prošly bez ztráty canonical messages.

### A4 — Analytický engine

**VALIDATED on real archive.** Deterministické analytics + A7 oracle prošly; private interaction audit potvrzuje dostupné metrics/findings a resolvable evidence.

### A5 — AI analýza

**VALIDATED for bounded-context/evidence/provenance path.** Production packet adapter a source provenance prošly na reálných datech. Live Ollama inference není součástí real-archive gate; readiness je fail-closed přes explicitní preflight.

### A6 — Rozhraní

**SYNTHETIC BROWSER VALIDATED + REAL-DATA DATA/PROVENANCE VALIDATED.** Desktop/iPhone browser matrix a Streamlit runtime smoke jsou zelené v CI; private real-data data-level interaction/evidence audit je `PASS`. Posledním bodem issue #6 zůstává fyzický browser render/click run nad private canonical DB v prostředí se Streamlitem.

### A7 — QA / validace

**VALID.** Independent oracles, exact-SHA release harness, Streamlit runtime smoke a real-archive reconciliation rozhodují fail-closed.

## Aktuální integrační fronta

1. **Dokončit issue #6 — fyzický real-data A6 browser run**
   - spustit `tools/a6_real_data_ui_qa.py` nad private canonical `messages.sqlite`,
   - desktop + iPhone portrait + iPhone landscape,
   - potvrdit skutečný render/click flow, evidence/message/source drill-down a žádné Streamlit exceptions,
   - DB/report/screenshoty nesmí být uploadovány do veřejného GitHubu.
   - aktuální ChatGPT runtime má Playwright/Chromium, ale nemá Streamlit; pokus o instalaci selhává kvůli nedostupné síti/DNS.

2. **Attachment completeness**
   - pokud budou dodány fyzické Apple Messages `Attachments`, znovu spustit real-archive gate s `--attachments-root`,
   - bez attachments root zůstává stav explicitně `NEEDS_REVIEW`; nesmí se ručně přepsat na `VALID`.

3. **Live local A5 execution**
   - po dostupnosti lokální Ollama instance a požadovaného modelu spustit explicitní live A5 analýzu přes preflight,
   - zachovat bounded context a provenance,
   - žádný cloud fallback.

4. **Průběžná exact-SHA ochrana**
   - každý další PR/push musí znovu projít full repository pytest, compile, Streamlit smoke, A5 probe, A6 provenance fixture, A6 browser gate a aggregate A7 exact-SHA verdict.

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

**Textový/datový/analytický vertical slice i private real-data interaction/evidence hranice jsou ověřené. Nejbližší release úkol je jediný: fyzický Streamlit browser QA nad private canonical databází; přílohy zůstávají samostatný externí data-quality blocker.**

# PROJECT_SPEC — Analýza zpráv Runtime v2

Tento soubor je **jediná autoritativní projektová a architektonická specifikace** repozitáře `rostakr/datadata`.

Při konfliktu platí pořadí autority:

1. `PROJECT_SPEC.md`,
2. explicitní canonical kontrakty v `docs/`,
3. release a validační dokumentace,
4. ostatní dokumentace,
5. historický kód.

Historické označení A0–A7 již není běhovou architekturou. Staré moduly mohou dočasně zůstat jako kompatibilní adaptéry během migrace, ale nesmí určovat nový runtime ani vytvářet druhý datový model.

## 1. Cíl

Vytvořit lokální, rychlý, auditovatelný systém pro analýzu dlouhodobé osobní komunikace, který:

- jednou správně importuje a normalizuje archiv,
- nad celou historií provede levnou deterministickou analýzu,
- vybere pouze relevantní události a úseky,
- sestaví malé evidence packy podle skutečného rozpočtu vstupu,
- použije AI pouze k interpretaci těchto malých packů,
- nikdy nenechá LLM rozhodovat o canonical identitě nebo provenance,
- funguje i na slabším lokálním CPU,
- umožňuje dohledat každý významný závěr ke konkrétním canonical zprávám.

Nová hlavní pipeline:

`RAW → CANONICAL STORE → SIGNALS → EVIDENCE PACKS → INTERPRETER → ANALYSIS STORE → UI`

QA je průřezový kontrakt nad každou hranicí, nikoli samostatný runtime stupeň.

## 2. Čtyři běhové části

### S1 — Canonical Store

Jediný zdroj pravdy pro normalizovaná data.

Obsahuje:

- conversation,
- participant,
- message,
- membership,
- attachment,
- timestamp,
- source provenance,
- import/reconciliation metadata.

Pravidla:

- RAW je read-only,
- canonical identita se nikdy nevytváří v AI vrstvě,
- SQLite je výchozí lokální úložiště,
- neznámá hodnota zůstává explicitně neznámá,
- každý canonical záznam musí být dohledatelný ke zdroji.

Existující funkční importní a normalizační kód se při migraci znovu nepíše bez důvodu. Runtime v2 jej používá přes stabilní read model.

### S2 — Signal Engine

Deterministicky analyzuje celý archiv nebo zvolené období.

Počítá zejména:

- objem a frekvenci komunikace,
- initiation,
- response latency,
- délku a rytmus sessions,
- změny intenzity,
- dlouhé mezery,
- změny poměru účastníků,
- konfliktní/negativní lexikální kandidáty,
- významné change points,
- opakující se interakční sekvence,
- témata pouze tehdy, pokud jsou označena jako lexikální/statistická, nikoli jako psychologický fakt.

Signal Engine **nepoužívá LLM**. Jeho výstupem jsou malé strukturované `Signal` a `Segment` záznamy s canonical message references.

### S3 — Evidence Compiler

Převádí signály, segmenty nebo ruční výběr na minimální vstup pro AI.

Evidence pack obsahuje pouze:

- krátké lokální labely `E1`, `E2`, ...,
- chronologicky seřazený text nezbytných zpráv,
- minimální sender/time metadata potřebná pro interpretaci,
- relevantní deterministické metriky,
- volitelnou otázku uživatele.

Evidence pack **neobsahuje source provenance payload**. Provenance zůstává lokálně v Canonical Store a připojuje se až po inference.

Rozpočet packu se řídí velikostí vstupu, nikoli pevným počtem zpráv. Výchozí implementace musí mít explicitní `max_input_chars` a později může použít přesný tokenizer. Pokud se segment nevejde, Evidence Compiler ho deterministicky rozdělí na menší packy se zachovaným pokrytím relevantní evidence.

Každý pack musí mít lokální mapu:

`E-label → canonical message_id → membership_id → provenance`

Tato mapa se nikdy negeneruje modelem.

### S4 — Interpreter

AI dostává pouze Evidence Pack a vrací malý interpretační objekt.

Povolený výstup:

- `summary`,
- `claims[]`.

Každý claim obsahuje pouze:

- `kind`: `observation | pattern | interpretation | uncertainty`,
- `text`,
- `evidence`: seznam labelů `E1...En`,
- `confidence`: `low | medium | high`.

LLM nesmí vracet canonical IDs, membership IDs, source record keys ani provenance. Po inference host aplikace validuje evidence labely a materializuje canonical references z lokální mapy Evidence Packu.

Neplatný výstup failne okamžitě. Runtime v2 **neprovádí automatický repair inference**, protože repair zdvojnásobuje latenci a komplikuje stav. Uživatel může explicitně spustit nový pokus.

Výchozí cesta je jeden modelový call na jeden pack. Více packů se standardně skládá deterministicky do reportu; volitelná AI syntéza smí dostat pouze již validované claims a jejich lokální evidence labely, nikdy původní celý archiv.

## 3. Analysis Store

Výsledky se ukládají lokálně mimo veřejný repozitář.

Každý uložený výsledek obsahuje:

- fingerprint Evidence Packu,
- model/provider,
- prompt contract version,
- čas běhu,
- validované claims,
- lokálně materializované canonical evidence refs,
- stav `COMPLETED | INVALID_OUTPUT | TIMEOUT | PROVIDER_ERROR | STALE`.

Cache klíč musí záviset na obsahu packu, modelu a verzi prompt kontraktu.

## 4. Evidence a provenance

Provenance je programová vlastnost, nikoli část jazykového modelu.

Tok evidence:

1. Signal/ruční výběr odkazuje na canonical message IDs.
2. Evidence Compiler ověří existenci a membership.
3. Model vidí pouze krátké `E-labels`.
4. Interpreter výstup smí citovat pouze tyto labely.
5. Host validátor odmítne neznámý/duplicitní label.
6. Host materializuje canonical message refs a aktuální source provenance.
7. UI provede drill-down přímo do Canonical Store.

Tím se eliminuje potřeba posílat modelu dlouhé provenance JSON objekty a zároveň se zvyšuje auditovatelnost.

## 5. AI prompt standard

System prompt musí být krátký a stabilní. Nesmí obsahovat rozsáhlé prose kontrakty ani opakovat kompletní JSON schema v textu, pokud provider podporuje structured output.

Model dostává:

- stručnou roli,
- čtyři povolené typy claimů,
- pravidlo evidence labels,
- pravidlo nejistoty,
- Evidence Pack.

Model nesmí:

- diagnostikovat osobnost nebo poruchu jako jistý fakt,
- tvrdit motivaci bez evidence,
- vytvářet provenance,
- citovat zprávu, která v packu není,
- prezentovat deterministickou metriku jako AI objev.

## 6. UI

Běžný tok uživatele:

1. otevřít canonical databázi,
2. zvolit conversation,
3. zobrazit timeline a deterministické signály,
4. kliknout na signal/segment nebo ručně označit zprávy,
5. zvolit typ otázky,
6. spustit lokální interpretaci,
7. zobrazit claims s evidence drill-downem.

Export/import velkého `a5-context.json` není součástí běžného runtime. Může zůstat pouze jako debug/diagnostický nástroj.

UI nesmí zobrazovat interní source provenance payload modelu, protože model jej vůbec nedostává.

## 7. Model a hardware

Architektura nesmí předpokládat výkonný GPU stroj.

Výchozí lokální profil musí fungovat s malým modelem přibližně 1–4B parametrů a s krátkým evidence packem. Větší model je volitelná kvalitativní nadstavba, ne podmínka correctness nebo release gate.

Modelová kvalita a systémová správnost jsou oddělené:

- systémová správnost = canonical data, signals, evidence mapping, validace,
- interpretační kvalita = schopnost zvoleného modelu formulovat užitečné claims.

## 8. Acceptance a QA

Release gate se nesmí opírat o to, zda jeden konkrétní velký LLM dokončí dlouhý prompt.

Povinné vrstvy QA:

### Canonical gate

- read-only ingest,
- reconciliation,
- integrita SQLite,
- provenance completeness.

### Signal gate

- deterministické fixtures,
- přesné očekávané metriky,
- stabilní segmentace.

### Evidence gate

- žádný chybějící selected message,
- žádné mixed conversation packy,
- budget enforcement,
- lossless label mapping,
- provenance materializace z canonical dat.

### Interpreter contract gate

- syntetický provider testuje validaci bez LLM,
- lokální provider smoke test ověřuje dostupnost modelu a jeden malý structured-output request,
- timeout modelu neinvaliduje Canonical Store ani Signal Engine.

### Real-archive gate

Reálný archiv se testuje lokálně. Do veřejného GitHubu se smějí dostat pouze privacy-safe agregované verdicts.

## 9. Migrace ze starého A0–A7

Mapování během přechodu:

- A1 + A2 → S1 Canonical Store,
- A3 + A4 → S2 Signal Engine,
- A5 ContextBuilder/orchestrator → S3 Evidence Compiler + S4 Interpreter,
- A6 → UI nad novým runtime,
- A7 → průřezové QA gates.

Starý `a5_ai` orchestrátor, chunk synthesis, repair pass a live acceptance jsou deprecated. Mohou zůstat dočasně kvůli regresním testům, ale nové funkce se do nich nepřidávají.

Migrace je dokončena, až:

1. hlavní UI nepoužívá starý A5 orchestrátor,
2. nový runtime má vlastní testy,
3. compatibility packet není nutný pro běžný provoz,
4. staré A5 runtime soubory lze odstranit bez ztráty funkce.

## 10. Bezpečnost a soukromí

Repozitář je veřejný. Nikdy sem necommitovat:

- skutečný `chat.db`,
- osobní zprávy,
- osobní přílohy,
- reálné evidence packy,
- lokální databázové cesty,
- source record/snapshot keys z reálného archivu,
- model cache s osobním obsahem,
- secrets.

Lokální AI nemá cloud fallback.

## 11. Priority

Při konfliktu platí:

1. správnost canonical dat,
2. provenance a auditovatelnost,
3. jednoduchost,
4. determinismus,
5. rychlost a nízké nároky na hardware,
6. testovatelnost,
7. interpretační kvalita,
8. UX.

## 12. Definition of Done

Změna je hotová pouze tehdy, když:

1. vychází z aktuálního `main`,
2. zachovává read-only RAW a canonical provenance,
3. nepřidává nový paralelní datový model,
4. má deterministický test nebo validační gate,
5. AI část není nutná pro dostupnost dat a metrik,
6. evidence je materializována host aplikací, ne modelem,
7. relevantní CI testy projdou,
8. dokumentace odpovídá skutečnému runtime.

## Hlavní zásada

**Celý archiv zpracuje program. AI dostane jen malý důkazní balíček a pouze jej interpretuje.**

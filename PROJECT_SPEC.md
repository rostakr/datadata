# PROJECT_SPEC — Analýza zpráv

Tento soubor je **jediná autoritativní projektová a architektonická specifikace** repozitáře `rostakr/datadata`.

Při konfliktu platí pořadí autority:

1. `PROJECT_SPEC.md`,
2. explicitní canonical kontrakty v `docs/`,
3. A0/A7 release a validační dokumentace,
4. agentní prompty v `docs/agents/`,
5. ostatní dokumentace,
6. historický kód nebo starší návrhy.

Žádný agent nesmí vytvořit paralelní architekturu, datový model nebo novou autoritativní specifikaci mimo toto pořadí.

## 1. Hlavní cíl

Vytvořit lokální, spolehlivý a auditovatelný systém pro import, zpracování, statistickou analýzu a AI interpretaci dlouhodobé osobní komunikace, primárně Apple iMessage.

Výsledný systém musí umožnit:

- import kompletní historie komunikace,
- zachování vazby na původní zdrojová data,
- normalizaci zpráv a příloh do jednoho canonical modelu,
- deterministické programové analýzy,
- detekci významných změn a období,
- AI interpretaci pouze nad relevantním bounded contextem,
- jednoduché lokální UI,
- dohledání každého významného závěru ke konkrétním zprávám, metrikám a zdrojové provenance.

Základní pipeline:

`RAW → NORMALIZED → DERIVED → ANALYTICS → RELEVANT CONTEXT → AI ANALYSIS → UI → QA`

## 2. Závazné principy

### Data před interpretací

Nejdříve správná data, potom správné metriky, až následně AI interpretace. AI nesmí nahrazovat deterministické výpočty.

### RAW je read-only

Originální importovaná data se nikdy nemění. Transformace probíhají pouze v odvozených vrstvách.

### Žádná tichá ztráta dat

Každý vstupní záznam musí skončit jako zpracovaný, duplicita, explicitně nepodporovaný nebo chyba. Reconciliation se musí uzavřít.

### Provenance je povinná

Každá canonical zpráva musí být dohledatelná ke zdroji. Každá odvozená metrika a každý významný AI závěr musí být dohledatelný ke canonical entitám a zdrojové evidenci.

### Jeden canonical model

Základní model je společný pro celý projekt:

`conversation → participant → message → attachment → timestamp → metadata`

Moduly nesmí vytvářet paralelní message/participant/conversation modely.

### Local-first a minimální disclosure

Osobní archiv zůstává lokálně. Externí AI nesmí automaticky dostávat celý archiv; pouze minimální relevantní kontext pro konkrétní analýzu.

### Jednoduchost a auditovatelnost

Preferovat jednodušší, deterministické, testovatelné a snadno opravitelné řešení před frameworkovou nebo infrastrukturní složitostí.

### Navazovat na existující implementaci

Před změnou vždy ověřit aktuální `main`, existující kód, kontrakty a testy. Neimplementovat druhou verzi funkce, která již existuje.

### Hotové = implementované + integrované + ověřené

Za hotové se nepovažuje návrh, pseudokód, TODO, mock, nepropojená komponenta ani neotestovaný kód.

### Testování je součást implementace

Každá významná změna musí mít test nebo validační mechanismus. Relevantní testy a A7 gate jsou součást Definition of Done.

## 3. Datové vrstvy

- **L0 RAW** — neměnný zdrojový archiv a identita vstupních záznamů.
- **L1 NORMALIZED** — canonical SQLite model s explicitní provenance.
- **L2 DERIVED** — sessions, threads, participant resolution, klasifikace a další deterministicky odvozené struktury.
- **L3 ANALYSIS** — metriky, kandidátní vzorce, relevantní kontext, AI výstupy a QA evidence.

Přechod mezi vrstvami musí být auditovatelný. Odvozená vrstva nesmí zpětně měnit předchozí vrstvu.

## 4. Čas a směr zpráv

Časová a směrová informace je datově kritická.

- canonical čas musí zachovat přesnost bez float-roundingu,
- UTC převody musí být deterministické,
- lokální čas a timezone musí být explicitní, pokud jsou známy,
- `is_from_me` je tri-state, pokud zdroj nedává jistou hodnotu; `unknown` se nesmí tiše převést na incoming nebo outgoing,
- neznámý směr nesmí zničit nebo přepsat identitu sendera.

## 5. Moduly A0–A7

- **A0 — Hlavní koordinace:** architektura, priority, kontrakty, integrační pořadí, stav a release rozhodování.
- **A1 — Import dat:** read-only ingest, staging, source identity a reconciliation.
- **A2 — Normalizace a databáze:** canonical model, timestamps, membership, provenance a integrita.
- **A3 — Zpracování a třídění:** sessions, threads, participant resolution a další derived struktury.
- **A4 — Analytický engine:** deterministické metriky a kandidátní změny/vzorce.
- **A5 — AI analýza:** bounded context, evidence chain, interpretace a explicitní nejistota.
- **A6 — Rozhraní:** lokální UI nad canonical a analysis read modely, evidence drill-down.
- **A7 — QA / validace:** nezávislé oracles, reconciliation, exact-SHA release gates a regresní ochrana.

Každý modul musí mít jasné `INPUT → PROCESSING → OUTPUT` a respektovat vlastnictví kontraktů sousedních modulů.

## 6. Analytický standard

Výstupy vždy rozlišují:

- **fakt** — přímo přítomný ve zdrojových/canonical datech,
- **metrika** — deterministicky vypočítaná hodnota,
- **vzorec** — opakovaný nebo statisticky významný jev,
- **interpretace** — možné vysvětlení,
- **nejistota** — omezení dat nebo alternativní vysvětlení.

Interpretace nesmí být prezentována jako prokázaný fakt. AI nesmí diagnostikovat osobnost, psychickou poruchu nebo motivaci člověka jako jistou skutečnost.

## 7. AI pravidla

A5 nesmí standardně analyzovat celý archiv. Kontext musí být připraven deterministickými vrstvami a omezen na potřebný rozsah.

Významný AI závěr musí mít:

1. pozorování,
2. evidence,
3. interpretaci,
4. alternativní vysvětlení,
5. míru jistoty,
6. strojově dohledatelné reference na zprávy/metriky/provenance.

Bez evidence je závěr pouze nedoložená hypotéza a nesmí být prezentován jako výsledek systému.

## 8. MVP / end-to-end vertical slice

Prioritou je jeden plně funkční scénář před množstvím izolovaných funkcí:

1. načíst iMessage data,
2. provést read-only import a source reconciliation,
3. normalizovat do canonical SQLite,
4. zachovat kompletní provenance,
5. vybrat conversation/kontakt a časové období,
6. zobrazit skutečné zprávy,
7. vypočítat základní metriky včetně response latency a initiation,
8. detekovat kandidátní významná období,
9. vytvořit relevantní bounded context,
10. provést AI analýzu s evidence chain,
11. zobrazit výsledek a source drill-down v UI,
12. projít A7 exact-SHA validací.

## 9. QA a release pravidlo

A7 je nezávislá validační vrstva, ne kosmetický testovací doplněk.

SHA lze označit jako release-ready pouze pokud:

- povinné testy a validační komponenty jsou `VALID`,
- reporty odkazují na stejný `contract_sha`,
- nejsou nevyřešené integrity/provenance chyby,
- aggregate verdict obsahuje `release_ready=true`,
- real-archive gate, pokud je pro daný milník požadován, proběhne lokálně bez publikace osobních dat.

CI syntetické fixtures nenahrazují praktickou validaci skutečného Apple Messages archivu.

## 10. Bezpečnost osobních dat

Repozitář `rostakr/datadata` je veřejný. Proto se do GitHubu nesmí commitovat:

- skutečný `chat.db`,
- osobní zprávy,
- soukromé přílohy,
- lokální inventáře skutečného archivu,
- reporty obsahující osobní text nebo identifikátory,
- tokeny, API klíče nebo jiné secrets.

Testy musí používat syntetická nebo bezpečně anonymizovaná data.

## 11. Priorita rozhodování

Při konfliktu cílů platí:

1. správnost dat,
2. úplnost dat,
3. dohledatelnost,
4. spolehlivost,
5. jednoduchost,
6. testovatelnost,
7. rychlost,
8. analytická kvalita,
9. UX,
10. vizuální vzhled.

## 12. Definition of Done

Změna je hotová pouze tehdy, když:

1. vychází z aktuálního stavu `rostakr/datadata:main`,
2. nerozbíjí vlastnictví A0–A7 ani canonical kontrakty,
3. zachovává RAW read-only pravidlo a provenance,
4. nemůže tiše ztratit nebo přepsat neznámá data,
5. má odpovídající test nebo validaci,
6. relevantní lokální/CI testy prošly,
7. A7 exact-SHA gate nehlásí regresi,
8. dokumentace byla aktualizována, pokud se změnil kontrakt nebo architektura.

## Hlavní zásada

**Nejdříve správná data. Potom správné metriky. Až potom AI interpretace.**

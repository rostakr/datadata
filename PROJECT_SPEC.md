# PROJECT_SPEC — Analýza zpráv

Tento dokument je autoritativní specifikace projektu. Při konfliktu s dílčí dokumentací, historickým kódem nebo návrhem má přednost tento soubor.

## Hlavní cíl

Vytvořit lokální, spolehlivý a auditovatelný systém pro import, zpracování, statistickou analýzu a AI interpretaci dlouhodobé osobní komunikace, primárně iMessage.

Výsledný systém musí umožnit:

- importovat kompletní historii komunikace,
- zachovat vazbu na původní zdrojová data,
- normalizovat zprávy a přílohy do jednotného modelu,
- analyzovat komunikaci programově,
- detekovat významné změny a období,
- použít AI pouze nad relevantním výběrem dat,
- zobrazit výsledky v jednoduchém lokálním UI,
- dohledat každý významný závěr zpět ke konkrétním zprávám a metrikám.

Základní pipeline:

`RAW DATA → NORMALIZED DATA → DERIVED DATA → ANALYTICS → RELEVANT CONTEXT → AI ANALYSIS → UI → QA`

## Závazné principy

### 1. Data mají přednost před interpretací

Nejdříve musí být správná data, potom správné metriky a až následně AI interpretace. AI nesmí nahrazovat deterministické výpočty, které lze provést programově.

### 2. Zdrojová data se nemění

Originální importovaná data jsou read-only. Veškeré čištění, deduplikace, klasifikace a transformace probíhají pouze v odvozených vrstvách.

### 3. Žádná data se nesmí tiše ztratit

Každý importovaný záznam musí být úspěšně zpracován, označen jako duplicita, označen jako nepodporovaný, nebo zaznamenán jako chyba. Musí být možné provést reconciliation mezi vstupem a výsledkem importu.

### 4. Provenance je povinná

Každá normalizovaná zpráva musí být dohledatelná ke svému původnímu zdroji. Analytické a AI výsledky musí být dohledatelné ke zprávám nebo metrikám, ze kterých vznikly.

### 5. Jednotný datový model

Všechny importéry převádějí data do společného modelu:

`conversation → participant → message → attachment → timestamp → metadata`

Jednotlivé moduly nesmí vytvářet vlastní paralelní datové modely.

### 6. Local-first

Citlivá komunikace má zůstávat lokálně. Externím AI službám se neposílá kompletní archiv automaticky. Posílá se pouze minimální relevantní kontext potřebný pro konkrétní analýzu.

### 7. Jednoduchost před složitostí

Preferovat řešení, které je jednodušší, lépe testovatelné, auditovatelné, deterministické, snadno opravitelné a snadno rozšiřitelné. Nevytvářet zbytečné frameworky, abstrakce nebo služby.

### 8. Navazovat na existující implementaci

Před každou změnou nejprve zjistit aktuální stav projektu. Nevytvářet paralelní implementaci funkcionality, která už v projektu existuje. Existující funkční kód se rozšiřuje nebo opravuje.

### 9. Hotové znamená funkční

Za dokončenou práci se nepovažuje návrh, pseudokód, placeholder, TODO, mock implementace nebo neotestovaný kód. Dokončená funkce musí být implementovaná, propojená a ověřená.

### 10. Testování je součást implementace

Každá důležitá změna musí mít odpovídající test nebo validační mechanismus. Před dokončením úkolu musí být spuštěny relevantní testy.

## Datové vrstvy

- **L0 RAW** — neměnný zdrojový archiv a jeho identita.
- **L1 NORMALIZED** — společný canonical model se source provenance.
- **L2 DERIVED** — deterministicky odvozené sessions, threads, klasifikace a pomocné struktury.
- **L3 ANALYSIS** — metriky, kandidátní vzorce, relevantní kontext, AI výstupy a QA evidence.

## Moduly

- **A0 — Hlavní koordinace**: architektura, integrační pořadí, kontrakty, release stav.
- **A1 — Import dat**: read-only ingest, staging, source reconciliation.
- **A2 — Normalizace a databáze**: canonical model, provenance, integrity.
- **A3 — Zpracování a třídění**: sessions, threads, participant resolution a odvozené struktury.
- **A4 — Analytický engine**: deterministické metriky a kandidátní vzorce.
- **A5 — AI analýza**: bounded relevant context, evidence provenance, interpretace.
- **A6 — Rozhraní**: lokální UI nad canonical/analysis read modely.
- **A7 — QA / validace**: nezávislé oracles, reconciliation, release gates.

A0 koordinuje architekturu a integraci. A1–A7 pracují pouze ve své oblasti a respektují společná rozhraní.

## MVP

MVP musí obsahovat alespoň:

- import iMessage,
- normalizaci do canonical SQLite,
- úplnou provenance a reconciliation,
- výběr kontaktu / conversation a časového období,
- zobrazení skutečných zpráv,
- základní komunikační metriky,
- response latency,
- initiation,
- detekci významných období / změn,
- AI analýzu pouze nad relevantním kontextem,
- evidence odkazy z AI výstupů,
- QA a fail-closed validační brány.

## Analytická pravidla

Vždy rozlišovat:

- **fakt** — přímo přítomný ve zdrojových datech,
- **metrika** — programově vypočítaná hodnota,
- **vzorec** — opakovaný nebo statisticky významný jev,
- **interpretace** — možné vysvětlení,
- **nejistota** — nedostatek dat pro spolehlivý závěr.

Interpretace se nesmí prezentovat jako prokázaný fakt. AI nemá diagnostikovat osobnost, psychické poruchy nebo motivaci člověka jako jistou skutečnost.

## Priorita rozhodování

Při konfliktu mezi cíli používat toto pořadí:

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

## Definition of Done

Změna je hotová pouze tehdy, když:

1. navazuje na existující implementaci,
2. zachovává canonical model a provenance,
3. nemůže tiše ztratit data,
4. má test nebo validační mechanismus,
5. relevantní testy prošly,
6. integrační A7 gate nehlásí regresi,
7. významný závěr lze zpětně doložit daty nebo metrikou.

## Hlavní zásada

**Nejdříve správná data. Potom správné metriky. Až potom AI interpretace.**

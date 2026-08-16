# A7 — current-main release gate

> **Autorita:** tento dokument je operativní release kontrakt podřízený kořenovému `PROJECT_SPEC.md`. Platí pro `rostakr/datadata` a aktuální exact SHA. A7 verdict nesmí být ručně přepsán A0 ani jiným modulem.

Tato brána je syntetická integrační kontrola aktuálního checkoutu. Nenahrazuje `az-qa staging`, `az-qa vertical` ani real-archive gate nad skutečným archivem.

## Autoritativní princip

Všechny komponenty (`core`, `A5`, `A6`) musí být spuštěny nad stejným `GITHUB_SHA`. Workflow nepřepíná na historické A5/A6 branche ani nepoužívá připnuté staré SHA.

Každý PR a každý push do `main`, který může ovlivnit projekt nebo jeho governance, musí být posuzován podle stejného exact-SHA principu. Dokumentační změna sama o sobě není release důkaz.

## Komponenty

- `core`: kompletní repository `pytest` + `compileall`;
- `A5`: aktuální A5 validator vytvoří materializovaný evidence snapshot a nezávislý A7 `validate_a5_evidence_chain` jej znovu ověří včetně membership, source a A4 metric provenance; záměrně poškozená provenance musí být odmítnuta;
- `A6`: production `CanonicalDatabase` vytvoří A2 fixture s jednou canonical zprávou ve dvou conversations, explicitním unknown timestampem a přílohou. Aktuální A6 musí zachovat memberships, unknown-time stav, message/attachment provenance, vytvořit production A5 packet se source provenance a aktuální A5 packet adapter ji musí zachovat. Záměrně odstraněná source provenance musí selhat v A7 i A5;
- `release-verdict`: pouze povinné `VALID` reporty se stejným SHA a úspěšné joby dávají `release_ready=true`.

## Povinné datové invariants

Release gate musí chránit alespoň tyto zásady:

- unknown se nesmí tiše převést na false/zero/domnělou hodnotu,
- `is_from_me` zachovává tri-state semantics tam, kde direction není znám,
- sender identity se neztrácí při unknown direction,
- UTC mikrosekundy a časové převody nesmí používat lossy float-rounding,
- canonical membership a source provenance se musí zachovat přes A2→A6→A5,
- záměrně poškozená nebo chybějící provenance musí být odmítnuta fail-closed.

## Fail-closed pravidla

Chybějící report po úspěšném jobu znamená `NEEDS_REVIEW`. Neúspěšný job, `INVALID` komponenta, neznámý verdict nebo rozdílný `contract_sha` znamená `INVALID`. Žádný takový stav se nesmí prezentovat jako release-ready.

Pokud nelze pro exact SHA prokázat stav, výchozí výsledek není `VALID`.

## Scope boundary

`release_ready=true` z tohoto workflow znamená pouze to, že aktuální commit prošel definovanou syntetickou integrační bránou. Neprokazuje kompatibilitu s libovolnou reálnou Apple Messages databází ani úplnost konkrétního uživatelského archivu.

Před označením MVP jako release candidate musí podle požadovaného milníku následovat skutečný archiv:

`A1 source reconciliation → A2 canonical provenance → A3 processing → A4 deterministic analytics → A5 bounded evidence → A6 drill-down → A7 vertical + downstream verdict`.

## Veřejný repozitář

A7 artifacts a fixtures nesmí obsahovat skutečný osobní `chat.db`, osobní zprávy, soukromé přílohy, real-archive inventory ani secrets. CI používá pouze syntetická nebo bezpečně anonymizovaná data.

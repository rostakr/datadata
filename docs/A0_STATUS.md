# A0 — Stav projektu a integrační fronta

Aktualizováno: 2026-08-17

Tento dokument je **operativní stav**, nikoliv druhá architektonická specifikace. Autorita projektu je `PROJECT_SPEC.md` v kořeni repozitáře.

## Cílový repozitář

- Repository: `rostakr/datadata`
- Default branch: `main`
- Repozitář je veřejný: skutečný osobní archiv, zprávy, přílohy, lokální real-archive reporty, AI cache a secrets se nesmí commitovat.

Aktuální exact SHA se záměrně nehardcoduje do tohoto stavového dokumentu. Release autoritu má Git historie a A7 exact-SHA workflow pro konkrétní commit.

## Ověřený reálný Apple Messages vertical slice

Private real-archive acceptance proběhla lokálně bez publikace osobních dat.

Ověřený řetězec:

- source SQLite integrity: PASS,
- A1 import/reconciliation: PASS pro podporované message/conversation/attachment relace,
- A2 canonical ingest + provenance + integrity: PASS,
- A3 processing/participant resolution: PASS,
- A4 deterministic analytics: PASS,
- A5 bounded context/evidence/provenance: PASS,
- A6 canonical packet/provenance: PASS,
- A6 desktop + iPhone portrait + iPhone landscape private browser matrix: PASS,
- A7 vertical reconciliation/exact-SHA release gates: PASS.

Canonical cílová konverzace měla při fyzické acceptance `10 869` memberships a `10 869` canonical messages; identifikátor konverzace ani osobní obsah se do veřejného repozitáře nezapisuje.

## RAW completeness vs. analysis readiness

RAW gate report zůstává autoritativní a nikdy se nepřepisuje.

Aktuální soukromý RAW verdict je `NEEDS_REVIEW`, protože historická media vrstva není fyzicky úplná. Privacy-safe lokální attachment audit prokázal:

- `79` referencovaných attachment occurrences nemá na aktuálním lokálním stroji dostupný binární soubor,
- všech `79` skončilo jako `NOT_FOUND`,
- žádná z nich nebyla obnovitelná percent/Unicode normalizací,
- žádný unikátní relokovaný basename kandidát nebyl nalezen,
- žádná ambiguity nebyla nalezena,
- resolver-fix signal není přítomen.

Současně `21` orphan attachment metadata rows není referencováno žádnou `message_attachment_join` relací. Reconciliation je dál eviduje, ale release-policy je klasifikuje jako audit-only/nonblocking; nejde o ztracené message rows ani broken attachment relace.

`real_archive_release_review` v2 proto odděluje dvě pravdivá tvrzení:

- RAW archive completeness: `NEEDS_REVIEW`, media `PARTIAL`,
- `CANONICAL_TEXT_AND_METADATA` analysis readiness: `VALID`, `release_ready=true`.

Explicitní limitation je `REFERENCED_ATTACHMENT_BINARIES_UNAVAILABLE`. Systém nesmí tvrdit, že chybějící binární obsah analyzoval.

## A5 — plná lokální AI execution cesta

A5 používá pouze lokální provider. Produkční implementace je Ollama přes `http://localhost:11434` nebo explicitně zadanou lokální URL.

Před jakýmkoli evidence promptem:

1. A6 packet/membership/source provenance musí projít validací,
2. Ollama `/api/tags` preflight musí potvrdit přesně požadovaný lokální model,
3. žádný cloud fallback se nesmí spustit.

### Bounded execution

Skutečné A6 tlačítko pro AI používá stejný bounded princip jako A4/A5 gate:

- max. `120` explicitních evidence messages na chunk,
- max. `180` messages v provider-visible contextu jednoho chunku,
- chronologické deterministické dělení,
- union chunků musí pokrýt původní selected evidence právě jednou,
- evidence se nesmí samplingem ani trimmingem ztratit,
- chyba jediného chunku ukončí flow fail-closed.

### Validovaná chunk synthesis

Více úspěšných chunků se spojí druhým lokálním Ollama krokem. Synthesis prompt dostává pouze již validované chunk-level claims, uncertainty a jejich message IDs. Nedostává celý raw A6 packet ani kompletní textový kontext.

Finální synthesis evidence může citovat pouze message IDs, které již byly citované validovanými chunk výsledky. Validator je kontroluje proti lokálnímu validation-only contextu a potom evidence znovu materializuje z canonical A6 packetu včetně membership/source provenance.

### Lokální cache

Fresh i cached A5 výsledek musí mít stejný provenance kontrakt. Default private cache je mimo repo:

`~/.datadata/cache/a5.sqlite`

Cestu lze změnit pomocí `ANALYZA_ZPRAV_A5_CACHE`. Cache obsahuje odvozené soukromé AI evidence/results a nesmí se commitovat ani uploadovat.

## A6 — uživatelský end-to-end flow

Uživatel může v lokálním Streamlit UI:

1. otevřít canonical konverzaci,
2. zvolit období a zobrazit zprávy/metriky,
3. otevřít A4 významný nález nebo lexikální téma,
4. použít jeho exact evidence jako A5 selection, případně vybrat zprávy ručně,
5. zvolit Ollama model, typ analýzy a blind/retrospective mode,
6. spustit lokální A5,
7. u velkého výběru vidět privacy-safe stav jednotlivých bounded částí,
8. zobrazit finální strukturovaný výsledek,
9. rozkliknout evidence a ověřit canonical/source provenance.

A6 neposílá osobní data do žádné cloud AI služby.

## Stav modulů

### A1 — Import dat

**VALIDATED.** Read-only ingest, source identity, accounting a reconciliation jsou ověřené na reálném archivu. Známá fyzická absence historických binárních médií je explicitní external data limitation, nikoliv tichá ztráta.

### A2 — Normalizace a databáze

**VALIDATED.** Canonical SQLite, lossless membership, timestamps, provenance a integrity prošly reálným vertical slice.

### A3 — Zpracování a třídění

**VALIDATED.** Processing a participant resolution prošly bez ztráty canonical messages.

### A4 — Analytický engine

**VALIDATED.** Deterministické metrics/findings/topics a evidence vazby jsou dostupné a ověřené na real-data read modelu.

### A5 — AI analýza

**IMPLEMENTED + SYNTHETICALLY VALIDATED end-to-end.** Provider, preflight, bounded context, chunking, validation, repair, cache, synthesis a evidence provenance jsou integrovány do skutečné A6 execution cesty. Poslední praktická acceptance je fyzický lokální inference run proti skutečně nainstalovanému Ollama modelu.

### A6 — Rozhraní

**VALIDATED.** Desktop/iPhone private real-data browser matrix je PASS. UI obsahuje skutečný local-Ollama A5 flow a evidence/source drill-down.

### A7 — QA / validace

**VALID.** Independent oracles, complete repository suite, compile, Streamlit smoke, A5/A6 provenance probes, browser gate a aggregate exact-SHA verdict zůstávají povinné pro každý release commit.

## Aktuální integrační fronta

Po sloučení chunked live-A5 implementace zbývá jediná praktická podmínka pro označení lokální aplikace za fyzicky end-to-end ověřenou:

**spustit jednu skutečnou A5 analýzu přes lokální Ollama model v A6 a potvrdit `completed`/validní evidence drill-down.**

Tato lokální acceptance nesmí uploadovat zprávy, AI cache, screenshots s osobním obsahem ani raw report. Na GitHub lze zapsat pouze privacy-safe status, model name podle potřeby, počty chunků/statusy a PASS/FAIL bez osobního obsahu.

## Release pravidlo A0

A0 nesmí obejít A7 ani raw gate. Release commit je integračně přijatelný pouze pokud:

- complete repository tests/compile projdou,
- A5 live-contract probe a A6 provenance fixture projdou,
- Streamlit/browser smoke projde,
- aggregate A7 exact-SHA verdict je zelený,
- reálná canonical/text analysis readiness nemá nevyřešenou integrity/provenance chybu,
- známá media limitation zůstává explicitní a není zaměněna za media completeness.

## Hlavní zásada

**Nejdříve správná data. Potom správné metriky. Až potom AI interpretace.**

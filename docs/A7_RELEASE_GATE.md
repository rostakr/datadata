# Runtime v2 — exact-SHA release gate

> **Autorita:** tento dokument je operativní release kontrakt podřízený kořenovému `PROJECT_SPEC.md`.

Historický název souboru zůstává kvůli migraci, ale A7 již není samostatná runtime vrstva. QA je průřezový kontrakt nad Runtime v2.

## Autoritativní princip

Všechny povinné komponenty musí být spuštěny nad stejným `GITHUB_SHA`. Workflow nepřepíná na historické větve ani staré pinned SHA.

Dokumentační změna sama o sobě není release evidence.

## Povinné komponenty

### `core`

- kompletní repository `pytest`,
- `compileall`,
- Streamlit health smoke nad hlavním `app.py`.

### `runtime`

Syntetický exact-SHA probe ověřuje:

- Evidence Compiler vytvoří bounded pack,
- provider payload používá pouze `E-labels` a neobsahuje canonical message ID, membership ID ani source provenance,
- jeden validní pack provede právě jeden provider call,
- claim evidence je po inference materializována lokálně zpět na canonical zprávu,
- neznámý evidence label je odmítnut fail-closed bez repair callu.

Tento CI probe používá syntetický provider. Skutečnou lokální Ollama inference nenapodobuje.

### `ui`

Syntetický canonical SQLite fixture ověřuje hranici:

`Canonical Store → A6 read model → provenance-enriched packet → Runtime v2 Evidence Compiler`

Chrání zejména:

- přesnou membership množinu,
- unknown timestamp,
- message/attachment provenance projection,
- zachování canonical evidence v lokální mapě,
- odstranění canonical/source identity z provider payloadu,
- fail-closed odmítnutí chybějící production provenance.

### `release-verdict`

Pouze `VALID` reporty `core + runtime + ui` se stejným exact SHA a úspěšné workflow joby mohou dát `release_ready=true`.

## Povinné invariants

Release gate musí chránit minimálně:

- RAW zůstává read-only,
- unknown se nesmí tiše převést na domnělou hodnotu,
- canonical membership a provenance se neztrácí,
- deterministická analytika není nahrazena AI,
- provider-visible evidence je bounded,
- LLM nedostává canonical/source identity, kterou nepotřebuje,
- model nesmí vytvořit novou canonical evidence referenci,
- záměrně poškozená provenance nebo evidence label musí selhat fail-closed.

## Fail-closed pravidla

Chybějící report po úspěšném jobu znamená `NEEDS_REVIEW`. Neúspěšný job, `INVALID` komponenta, neznámý verdict nebo rozdílný `contract_sha` znamená `INVALID`.

Pokud nelze pro exact SHA prokázat stav, výchozí výsledek není `VALID`.

## Scope boundary

`release_ready=true` dokazuje syntetickou integrační správnost aktuálního checkoutu. Nedokazuje kompatibilitu s libovolnou reálnou Apple Messages databází ani úplnost konkrétního soukromého archivu.

Pro fyzické lokální ověření Interpreteru musí na trusted stroji následovat:

`real canonical packet → Runtime v2 Evidence Compiler → skutečný lokální Ollama inference → local evidence materialization → provenance reconciliation`

pomocí `make runtime-accept-local`.

Skutečný osobní archiv, packet ani modelové evidence se do GitHub Actions neposílají.

## Veřejný repozitář

QA artifacts a fixtures nesmí obsahovat skutečný osobní `chat.db`, osobní zprávy, přílohy, real-archive inventory, lokální paths ani secrets. CI používá pouze syntetická data.

## Legacy probes

Staré `tools/a7_release/a5_live.py` a `a6_live.py` mohou dočasně zůstat jako migrační/regresní utility, ale již nejsou autoritativními komponentami release verdictu. Nový workflow používá `runtime_live.py` a `ui_live.py`.

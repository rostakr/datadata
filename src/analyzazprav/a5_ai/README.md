# Legacy A5 implementation — deprecated

Tento adresář obsahuje původní A5 implementaci a během migrace Runtime v2 zůstává v repozitáři pouze kvůli regresním testům, kompatibilním adaptérům a postupnému odstranění starého kódu.

**Není to již production runtime.** Autoritativní architektura je v `PROJECT_SPEC.md` a nový interpretive runtime je v `src/analyzazprav/runtime/`.

## Co je zde historické

Původní A5 obsahuje zejména:

- `ContextBuilder` s message-count limity,
- `AIAnalyzer`,
- modelově generovaný rozsáhlý structured result,
- jeden automatický repair inference po validační chybě,
- cache starého A5 kontraktu,
- chunk orchestrator,
- multi-chunk synthesis,
- A2/A4/A6 integrační adaptéry.

Tyto komponenty se již nesmějí rozšiřovat novou produkční funkcionalitou.

## Nová produkční cesta

Runtime v2 používá:

`canonical data → deterministic signals → Evidence Compiler → compact Interpreter → local evidence materialization`

Klíčové rozdíly:

- pack budget je podle skutečné velikosti provider payloadu, nikoli pevného počtu zpráv,
- provider nevidí canonical message IDs, membership IDs ani source provenance,
- model cituje pouze lokální `E1…En` labels,
- canonical/source evidence materializuje host aplikace po inference,
- Ollama dostává JSON Schema structured output,
- u podporovaných thinking modelů produkční Runtime v2 používá non-thinking inference,
- automatický repair inference není povolen,
- jeden pack znamená jeden inference call,
- multi-pack výsledek je standardně složen deterministicky bez dalšího modelového callu.

Nový kód:

- `src/analyzazprav/runtime/evidence.py`
- `src/analyzazprav/runtime/interpreter.py`
- `src/analyzazprav/runtime/service.py`
- `a6/a5_bridge.py::run_local_runtime`
- `a6/runtime_ui.py`
- `tools/runtime_live_acceptance.py`

## Co zůstává z tohoto adresáře produkčně použité

Dočasně zůstává `providers/` jako lokální provider abstraction. `OllamaProvider` je používán i Runtime v2, protože jde o jednoduchou HTTP hranici a není důvod ji duplikovat.

Ostatní moduly tohoto adresáře jsou považovány za legacy, dokud nebudou odstraněny nebo explicitně přesunuty do nového runtime.

## Migrační pravidlo

Starý A5 kód lze odstranit po splnění všech podmínek:

1. hlavní UI používá pouze `run_local_runtime`,
2. Runtime v2 tests a browser smoke jsou zelené,
3. Runtime v2 live acceptance projde lokálně na reálném canonical packetu,
4. žádný production entrypoint neimportuje starý orchestrator/analyzer/cache,
5. potřebné provider utility jsou přesunuty nebo označeny jako sdílené.

Do té doby legacy testy mohou zůstat jako regresní ochrana canonical/evidence chování, ale jejich existence neznamená, že starý orchestrátor je production path.

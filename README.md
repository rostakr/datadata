# Analýza zpráv

Local-first systém pro auditovatelnou analýzu dlouhodobé osobní komunikace.

Hlavní architektura Runtime v2:

`RAW → CANONICAL STORE → SIGNALS → EVIDENCE PACKS → INTERPRETER → ANALYSIS STORE → UI`

Autoritativní specifikace je [`PROJECT_SPEC.md`](PROJECT_SPEC.md).

## Proč Runtime v2

Původní A0–A7 implementace postupně vytvořila příliš těžký AI runtime: velké prompt kontrakty, fixní message chunky, modelově generovanou provenance strukturu, repair inference a následnou synthesis inference. Na slabším lokálním CPU to vedlo k dlouhým promptům, truncation a timeoutům.

Runtime v2 odděluje systémovou správnost od kvality LLM:

1. **Canonical Store** drží správná data a provenance.
2. **Signal Engine** programově analyzuje celou historii.
3. **Evidence Compiler** sestaví malý pack podle skutečné velikosti vstupu.
4. **Interpreter** provede jeden krátký inference call na pack.
5. Python validuje krátké `E1…En` reference a teprve lokálně je mapuje zpět na canonical message IDs a provenance.

LLM nikdy nedostává source record keys, snapshot keys, membership IDs ani celý archiv.

## Historické A0–A7

A0–A7 už nejsou autoritativní runtime architekturou. Během migrace slouží pouze jako mapování stávajícího kódu:

- A1/A2 → Canonical Store,
- A3/A4 → Signal Engine,
- A5 → Evidence Compiler + Interpreter,
- A6 → UI,
- A7 → průřezové QA gates.

Starý A5 orchestrátor zůstává dočasně v repozitáři kvůli regresním testům, ale hlavní A6 bridge používá Runtime v2.

## Lokální spuštění

Pokud už existuje canonical `messages.sqlite`:

```bash
python -m tools.local_app --database /cesta/messages.sqlite
```

nebo:

```bash
make a6-launch DATABASE=/cesta/messages.sqlite
```

Přímo z Apple Messages `chat.db`:

```bash
python -m tools.local_app \
  --chat-db /cesta/k/chat.db \
  --target EXACT_TARGET
```

RAW archiv zůstává read-only a odvozená data vznikají mimo repozitář v `~/.datadata/runs/`, pokud není explicitně zvoleno jiné lokální umístění.

## Runtime v2 AI flow

Uživatel v UI vybere signál/segment nebo konkrétní zprávy. A6 připraví lokální packet, Runtime v2 jej okamžitě zredukuje na evidence pack a provider dostane pouze například:

```json
{
  "evidence": [
    {"label":"E1","sender":"P1","timestamp":"...","text":"..."},
    {"label":"E2","sender":"P2","timestamp":"...","text":"..."}
  ],
  "question":"..."
}
```

Model vrací pouze:

```json
{
  "summary": "...",
  "claims": [
    {
      "kind": "observation",
      "text": "...",
      "evidence": ["E1", "E2"],
      "confidence": "medium"
    }
  ]
}
```

Potom host aplikace:

- odmítne neznámé nebo duplicitní evidence labely,
- mapuje `E1…En` zpět na canonical message IDs,
- lokálně materializuje membership/source provenance,
- umožní evidence drill-down v UI.

Automatický repair inference není součástí Runtime v2. Neplatný modelový výstup failne rychle a explicitně.

## Evidence budget

Runtime v2 nepoužívá pevné pravidlo „120 evidence / 180 context zpráv“. Pack je omezen skutečnou velikostí serializovaného provider vstupu (`max_input_chars`).

Pokud se selected evidence nevejde:

- selected zprávy se deterministicky rozdělí,
- každá selected zpráva patří právě do jednoho packu,
- pouze ne-selected okolní kontext se doplňuje, když se do budgetu vejde,
- canonical identita a provenance se do provider payloadu neposílají.

## Lokální model

Správnost systému nesmí záviset na velkém modelu. Pro starší CPU je vhodný malý lokální model; větší model je volitelná kvalitativní nadstavba.

Ollama musí běžet lokálně a model musí být nainstalovaný před spuštěním. Není žádný cloud fallback.

## Vývoj

```bash
make setup
make test
make compile
make check
```

Pro vývoj včetně UI:

```bash
make setup-dev
make ui
```

Skutečný osobní archiv se nezpracovává v GitHub Codespaces ani v CI.

## Soukromí

Repozitář `rostakr/datadata` je veřejný. Nikdy sem necommitovat:

- skutečný `chat.db`,
- osobní zprávy,
- přílohy,
- reálné evidence packy,
- lokální archive/report databáze,
- source provenance identifikátory z reálného archivu,
- secrets.

## Hlavní zásada

**Celý archiv zpracuje program. AI dostane jen malý důkazní balíček a pouze jej interpretuje.**

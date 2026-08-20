# Runtime v2 — fyzická lokální Ollama acceptance

Tento dokument nahrazuje původní A5 chunk/repair/synthesis acceptance.

Runtime v2 ověřuje jednu jednoduchou fyzickou cestu:

`canonical packet → budgeted evidence pack → local Ollama → E-label validation → local canonical/provenance materialization → reconciliation`

Starý A5 orchestrátor může během migrace zůstat v repozitáři kvůli regresním testům, ale tento gate jej nepoužívá.

## Co `PASS` dokazuje

Úspěšný verdict `PASS` znamená současně:

- vstupní packet má validní canonical identity a požadovanou source provenance,
- Evidence Compiler sestavil jeden nebo více packů bez překročení input budgetu,
- provider payload neobsahuje canonical message IDs, membership IDs ani source provenance,
- lokální Ollama model provedl skutečný inference request,
- modelový výstup prošel Runtime v2 contract validací,
- všechny evidence labely existují v příslušném lokálním packu,
- canonical evidence refs byly materializovány host aplikací až po inference,
- každá materializovaná claim evidence se proti aktuální canonical membership/source provenance reconciliuje jako `PASS`.

Neplatný modelový výstup, timeout, chybějící evidence nebo jiný reconciliation status failne explicitně.

## Co bylo odstraněno

Runtime v2 acceptance nemá:

- automatický repair inference,
- fixní 120-message chunky,
- 180-message context limit,
- AI generované canonical/provenance objekty,
- povinnou AI synthesis nad chunky,
- závislost na jednom velkém modelu.

Jeden pack = jeden krátký modelový call.

## Soukromí

Acceptance se smí spouštět pouze na důvěryhodném lokálním stroji.

Soukromé vstupy:

- canonical `messages.sqlite`,
- lokální analysis packet obsahující text zpráv a provenance.

Tyto soubory se nesmí commitovat, uploadovat do GitHubu ani přesouvat do Codespaces.

Provider je lokální Ollama bez cloud fallbacku. Do modelového promptu se navíc neposílají source record/snapshot keys ani canonical membership/message IDs. Ty zůstávají v lokální mapě Evidence Compileru.

Výstup acceptance je privacy-safe a obsahuje pouze:

- schema/verdict,
- provider/model,
- počty selected zpráv, packů, claims a evidence zpráv,
- agregované reconciliation status counts,
- allowlisted failure reasons.

## Spuštění

Ollama musí běžet a zvolený model musí být předem nainstalovaný.

```bash
make runtime-accept-local \
  DATABASE=/cesta/messages.sqlite \
  PACKET=/cesta/a5-context.json \
  MODEL=qwen3:1.7b
```

Dočasný kompatibilní alias:

```bash
make a5-accept-local \
  DATABASE=/cesta/messages.sqlite \
  PACKET=/cesta/a5-context.json \
  MODEL=qwen3:1.7b
```

Oba příkazy spouštějí **Runtime v2**, nikoli deprecated A5 orchestrátor.

Volitelné nastavení:

```bash
RUNTIME_TIMEOUT_SECONDS=300
RUNTIME_MAX_INPUT_CHARS=6000
OLLAMA_URL=http://localhost:11434
```

Přímý CLI ekvivalent:

```bash
python -m tools.runtime_live_acceptance \
  --database /cesta/messages.sqlite \
  --packet /cesta/a5-context.json \
  --model qwen3:1.7b \
  --timeout-seconds 300 \
  --max-input-chars 6000
```

## Výsledek

Úspěšný běh:

```json
{
  "verdict": "PASS"
}
```

s exit code `0`.

Typické privacy-safe failure kategorie:

- `PACKET_INVALID`,
- `PROVIDER_PREFLIGHT_TIMEOUT`,
- `PROVIDER_UNAVAILABLE`,
- `INFERENCE_TIMEOUT`,
- `PROVIDER_ERROR`,
- `MODEL_OUTPUT_INVALID`,
- `CLAIMS_MISSING`,
- `CANONICAL_READ_FAILED`,
- `EVIDENCE_RECONCILIATION_FAILED`,
- `EVIDENCE_RECONCILIATION_NOT_PASS`,
- `MESSAGE_EVIDENCE_MISSING`.

Raw exception detail ani soukromé IDs se do acceptance reportu nevypisují.

## Release pravidlo

Fyzický lokální modelový smoke test je pouze Interpreter contract gate. Canonical/Signal correctness se ověřuje odděleně deterministickými testy a real-archive gates.

To znamená, že timeout konkrétního modelu nesmí zneplatnit správně importovaný archiv ani deterministické metriky. Pro release je požadována funkční malá lokální inference cesta na podporovaném lokálním modelu, nikoli úspěch obřího promptu na konkrétním 8B modelu.

# A5 — fyzická lokální Ollama acceptance

Tento postup uzavírá poslední praktickou podmínku A0 po syntetickém ověření A5/A6: jeden skutečný lokální inference run nad reálným canonical A6 packetem s následnou kontrolou evidence provenance.

Nejde o nový analytický engine ani paralelní A5 cestu. Nástroj používá existující `a6.a5_bridge.run_local_a5`, stejný bounded/chunked orchestrátor a stejné A5 evidence kontrakty jako A6 UI.

## Co acceptance dokazuje

Úspěšný verdict `PASS` znamená současně:

- Ollama model skutečně provedl fresh inference; acceptance vždy používá `force_refresh=True`, takže cache hit nemůže nahradit fyzický modelový run,
- A5 execution skončil `completed`,
- všechny bounded chunky skončily `completed`,
- assertion-bearing výsledek obsahuje materializovanou message evidence,
- A5 evidence snapshot se proti aktuální A2 membership/source provenance reconciliuje pouze jako `PASS`,
- případná chunk synthesis proběhla přes existující validovaný A5 orchestrátor.

`STALE`, `FAIL`, `UNVERIFIED`, nedokončený chunk nebo chybějící materializovaná evidence jsou fail-closed.

## Soukromí

Acceptance se smí spouštět pouze na důvěryhodném lokálním stroji.

Vstupy jsou soukromé:

- canonical `messages.sqlite`,
- A6 `a5-context.json`, který může obsahovat text zpráv, message IDs a source provenance,
- lokální A5 cache.

Tyto soubory se nesmí commitovat, uploadovat do GitHubu ani přesouvat do Codespaces. `make a5-accept-local` i samotný CLI nástroj odmítnou běh při nastaveném `$CODESPACES`.

Výstup acceptance je naopak záměrně privacy-safe. Obsahuje pouze:

- schema/verdict,
- `provider=ollama`,
- zvolený model,
- počty selected/chunk/evidence položek,
- agregované reconciliation status counts,
- allowlisted failure kategorie.

Neobsahuje message text, message/conversation/membership/source IDs, lokální paths, context hash ani modelový obsah.

## Příprava packetu

Spusťte A6 nad canonical databází:

```bash
make a6-launch DATABASE=/cesta/messages.sqlite
```

V A6 vyberte evidence zprávy ručně nebo z A4 nálezu / lexikálního tématu. V záložce **Analýza** stáhněte již existující export **A5 kontext** jako `a5-context.json`.

Soubor zůstává pouze lokálně.

## Fresh live acceptance

Ollama musí běžet lokálně a model musí být již nainstalovaný. Potom spusťte:

```bash
make a5-accept-local \
  DATABASE=/cesta/messages.sqlite \
  PACKET=/cesta/a5-context.json \
  MODEL=qwen3:8b
```

Volitelně lze změnit:

```bash
OLLAMA_URL=http://localhost:11434
A5_ANALYSIS_TYPE=segment
A5_MODE=blind
A5_TIMEOUT_SECONDS=120
```

`A5_TIMEOUT_SECONDS` je timeout jednoho lokálního Ollama `/api/chat` inference requestu. Výchozí hodnota zůstává `120` sekund. Na pomalejším CPU-only stroji lze použít například:

```bash
make a5-accept-local \
  DATABASE=/cesta/messages.sqlite \
  PACKET=/cesta/a5-context.json \
  MODEL=qwen3:8b \
  A5_TIMEOUT_SECONDS=900
```

Delší timeout nemění evidence/provenance pravidla ani fail-closed acceptance kontrakt; pouze dává lokálnímu modelu více času na dokončení stejného inference requestu.

Přímý CLI ekvivalent:

```bash
python -m tools.a5_live_acceptance \
  --database /cesta/messages.sqlite \
  --packet /cesta/a5-context.json \
  --model qwen3:8b \
  --timeout-seconds 900
```

## Výsledek

Úspěšný běh skončí exit code `0` a jedním JSON objektem s `"verdict":"PASS"`.

Neúspěšný běh skončí nenulovým exit code a privacy-safe `FAIL`. Typické kategorie:

- `PACKET_LOAD_FAILED`,
- `PACKET_PROVENANCE_INVALID`,
- `LIVE_EXECUTION_FAILED`,
- `PROVENANCE_LOOKUP_FAILED`,
- `EVIDENCE_RECONCILIATION_NOT_PASS`,
- `CHUNK_NOT_COMPLETED`,
- `MESSAGE_EVIDENCE_MISSING`.

CLI úmyslně nevypisuje raw exception detail, protože ten může obsahovat soukromý lokální kontext. Při debugování používejte lokální A6/Ollama logy a nic z nich nepublikujte bez sanitizace.

## A0 completion rule

Po prvním fyzickém `PASS` lze do veřejného A0 statusu zaznamenat pouze privacy-safe fakt, že live acceptance proběhla, případně název modelu a agregované počty chunků/evidence. Samotný A6 packet, modelový výstup, cache, IDs ani lokální report obsahující osobní data se do repozitáře neukládají.

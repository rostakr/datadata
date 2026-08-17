# Analýza zpráv

Local-first pipeline pro auditovatelný import, normalizaci, deterministickou analýzu a AI interpretaci osobní komunikace.

`RAW → NORMALIZED → DERIVED → ANALYTICS → RELEVANT CONTEXT → AI ANALYSIS → UI → QA`

## Autorita projektu

Jediná autoritativní projektová a architektonická specifikace je [`PROJECT_SPEC.md`](PROJECT_SPEC.md).

Agentní prompty jsou v [`docs/agents/`](docs/agents/). Operativní integrační stav vede A0 v [`docs/A0_STATUS.md`](docs/A0_STATUS.md). A7 release pravidla jsou v [`docs/A7_RELEASE_GATE.md`](docs/A7_RELEASE_GATE.md).

Při konfliktu dokumentace má přednost `PROJECT_SPEC.md` a canonical kontrakty. Nevytvářet paralelní datový model ani druhou hlavní specifikaci.

## Moduly

- A0 — hlavní koordinace, architektura a integrační pořadí
- A1 — import a source reconciliation
- A2 — canonical SQLite, provenance a integrita
- A3 — processing, sessions, threads a participant resolution
- A4 — deterministická analytika
- A5 — bounded AI context, evidence chain a interpretace
- A6 — lokální Streamlit UI a source/evidence drill-down
- A7 — nezávislá QA, reconciliation a exact-SHA release gates

## Základní pravidla

- zdrojová data jsou read-only,
- žádný vstupní záznam se nesmí tiše ztratit,
- všechny vrstvy používají jeden canonical model,
- neznámá informace zůstává neznámá; nesmí být domyšlena jako jistá hodnota,
- deterministické metriky se nepočítají pomocí AI,
- AI dostává pouze minimální relevantní bounded context,
- významný závěr musí být dohledatelný ke zprávám, metrikám a provenance,
- změna není hotová bez testu/validace a bez relevantního A7 gate.

## Vývojové prostředí

Společné příkazy pro lokální vývoj, Codespaces i CI jsou v `Makefile`:

```bash
make setup
make test
make compile
make check
```

Pro kompletní vývojové prostředí včetně Playwright Chromium:

```bash
make setup-dev
```

### GitHub Codespaces

`.devcontainer/devcontainer.json` připraví Python 3.11, nainstaluje vývojové závislosti, spustí `make check` a A6 viewport smoke test. Při každém startu Codespace se automaticky spustí Streamlit na portu `8501` a GitHub port otevře jako preview.

Ruční příkazy v Codespace:

```bash
make check
make ui
make a6-smoke
```

Stejné příkazy jsou dostupné také jako VS Code Tasks.

**Codespaces je vývojové a QA prostředí, ne úložiště skutečného osobního archivu.** Do Codespaces ani do repozitáře nenahrávat skutečný `chat.db`, osobní zprávy, přílohy ani soukromý canonical `messages.sqlite`. Reálný archiv se zpracovává pouze na důvěryhodném lokálním stroji.

## Nejjednodušší lokální spuštění

Pokud už existuje canonical `messages.sqlite`:

```bash
python -m tools.local_app --database /cesta/messages.sqlite
```

nebo přes společný příkaz:

```bash
make a6-launch DATABASE=/cesta/messages.sqlite
```

Přímo z Apple Messages `chat.db`:

```bash
python -m tools.local_app \
  --chat-db /cesta/k/chat.db \
  --target EXACT_TARGET
```

`EXACT_TARGET` musí být přesná canonical/source identita; fuzzy výběr se nepoužívá. Alternativně lze zadat autoritativní lokální ID:

```bash
python -m tools.local_app \
  --chat-db /cesta/k/chat.db \
  --conversation-id CANONICAL_CONVERSATION_ID
```

Launcher pouze skládá existující `tools.real_archive_gate` a A6. RAW archiv zůstává **read-only**. Pokud není uveden `--workdir`, odvozená data vzniknou mimo repozitář v adresáři `~/.datadata/runs/`.

Verdict `INVALID` UI nespustí. Stav `NEEDS_REVIEW` lze otevřít pouze jako explicitní lokální kontrolu; samotným otevřením se verdict nemění na `VALID`.

Pro vývoj lze A6 spustit také samostatně:

```bash
make ui
```

nebo přímo:

```bash
streamlit run app.py
```

## Lokální AI přes Ollama

A6 obsahuje skutečné lokální A5 spuštění v záložce **Analýza**. Nejprve vyberte zprávy ručně nebo použijte evidence A4 nálezu / lexikálního tématu. Potom zvolte lokální Ollama model a spusťte **Spustit A5 lokálně přes Ollama**.

Ollama musí běžet lokálně na zadané URL a zvolený model musí být předem nainstalovaný. A6 před odesláním evidence provede `/api/tags` preflight. Model se automaticky nestahuje a neexistuje cloud fallback.

A5 nikdy neposílá celý archiv do jednoho modelového promptu:

- explicitní evidence je chronologicky dělena po maximálně `120` zprávách,
- každý chunk používá maximálně `180` message context,
- všechny chunky dohromady zachovají původní selected evidence právě jednou,
- chyba kteréhokoli chunku zastaví analýzu fail-closed,
- více validních chunků se syntetizuje pouze z již validovaných dílčích závěrů a jejich message IDs,
- kompletní/raw message context se do syntézního promptu neposílá,
- finální evidence se znovu validuje a materializuje z canonical dat a provenance.

Výsledek se zobrazuje ve stejném A6 UI jako strukturované pozorování, interpretace, vzorce, alternativní vysvětlení a nejistoty s evidence/source drill-downem. U vícedílné analýzy UI navíc zobrazí privacy-safe počet částí, počet evidence zpráv a stav každé části.

Lokální výsledky se cachují mimo repozitář v `~/.datadata/cache/a5.sqlite`. Cestu lze přepsat proměnnou `ANALYZA_ZPRAV_A5_CACHE`.

Podrobný A5 kontrakt: [`src/analyzazprav/a5_ai/README.md`](src/analyzazprav/a5_ai/README.md).

## Reálný Apple Messages archiv

Kompletní read-only gate bez automatického spuštění UI lze spustit samostatně:

```bash
python -m tools.real_archive_gate \
  --chat-db /cesta/k/chat.db \
  --workdir /cesta/k/novemu-prazdnemu-workdir \
  --target EXACT_TARGET
```

Stejný lokální gate je dostupný přes `Makefile`:

```bash
make a6-gate-local \
  CHAT_DB=/cesta/k/chat.db \
  WORKDIR=/cesta/k/novemu-prazdnemu-workdir \
  TARGET=EXACT_TARGET
```

A gate + následné lokální A6 UI:

```bash
make a6-launch-archive-local \
  CHAT_DB=/cesta/k/chat.db \
  TARGET=EXACT_TARGET
```

Tyto `*-local` targety úmyslně odmítnou běh uvnitř GitHub Codespaces.

`EXACT_TARGET` nahraďte pouze přesnou canonical/source identitou z lokálního archivu. Resolver nikdy fuzzy nevybere conversation. Pokud target není přesná canonical/source identita, další běh se provede s explicitním `CONVERSATION_ID` / `--conversation-id`.

Podrobný kontrakt: [`docs/A0_REAL_ARCHIVE_GATE.md`](docs/A0_REAL_ARCHIVE_GATE.md).

## CI pro A6

Workflow `.github/workflows/a6-tests.yml` používá stejné příkazy jako Codespaces:

```bash
make check
make a6-smoke
```

Navíc validuje JSON konfiguraci Codespaces/VS Code a ukládá viewport evidence jako GitHub Actions artifact.

## Soukromí

Repozitář `rostakr/datadata` je veřejný. Nikdy sem necommitovat skutečný `chat.db`, osobní zprávy, soukromé přílohy, lokální real-archive reporty, secrets ani jiné osobní zdrojové artefakty.

## Hlavní zásada

**Nejdříve správná data. Potom správné metriky. Až potom AI interpretace.**

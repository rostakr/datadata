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

## Instalace

```bash
python -m pip install -r requirements.txt
pytest -q
```

## Nejjednodušší lokální spuštění

Pokud už existuje canonical `messages.sqlite`:

```bash
python -m tools.local_app --database /cesta/messages.sqlite
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

Launcher pouze skládá existující `tools.real_archive_gate` a A6. RAW archiv zůstává read-only. Pokud není uveden `--workdir`, odvozená data vzniknou mimo repozitář pod `~/.analyzazprav/runs/`. Verdict `INVALID` UI nespustí; `NEEDS_REVIEW` lze otevřít pouze jako explicitní lokální kontrolu a není tím změněn na `VALID`.

Pro vývoj lze A6 spustit samostatně a zdroj zvolit ručně:

```bash
streamlit run app.py
```

## Reálný Apple Messages archiv

Kompletní read-only gate bez automatického spuštění UI lze spustit samostatně:

```bash
python -m tools.real_archive_gate \
  --chat-db /cesta/k/chat.db \
  --workdir /cesta/k/novemu-prazdnemu-workdir \
  --target EXACT_TARGET
```

`EXACT_TARGET` nahraďte pouze přesnou canonical/source identitou z lokálního archivu. Resolver nikdy fuzzy nevybere conversation. Pokud target není přesná canonical/source identita, další běh se provede s explicitním `--conversation-id`.

Podrobný kontrakt: [`docs/A0_REAL_ARCHIVE_GATE.md`](docs/A0_REAL_ARCHIVE_GATE.md).

## Soukromí

Repozitář `rostakr/datadata` je veřejný. Nikdy sem necommitovat skutečný `chat.db`, osobní zprávy, soukromé přílohy, lokální real-archive reporty, secrets ani jiné osobní zdrojové artefakty.

## Hlavní zásada

**Nejdříve správná data. Potom správné metriky. Až potom AI interpretace.**

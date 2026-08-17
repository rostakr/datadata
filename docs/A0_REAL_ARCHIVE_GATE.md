# A0 — Real archive release gate

> **Autorita:** tento dokument je operativní gate kontrakt podřízený kořenovému `PROJECT_SPEC.md`. Cílový repozitář je `rostakr/datadata`. Protože je veřejný, žádný skutečný `chat.db`, osobní text, příloha, lokální inventář ani real-archive report se nesmí commitovat nebo automaticky publikovat jako GitHub artifact.

Tento nástroj skládá existující A1–A7 kontrakty nad jedním skutečným Apple Messages `chat.db`. Nevytváří vlastní importer, canonical model, analytiku ani AI interpretaci a nevolá LLM.

## Spuštění

Z kořene repozitáře:

```bash
python -m tools.real_archive_gate \
  --chat-db /cesta/k/chat.db \
  --workdir /cesta/k/novemu-prazdnemu-workdir \
  --target EXACT_TARGET
```

`EXACT_TARGET` nahraďte pouze přesnou hodnotou uloženou v canonical/source identitě lokálního archivu. Pokud target není přesná hodnota, gate skončí `TARGET_NOT_RESOLVED` a do lokálního `real_archive_report.json` uloží inventář conversations. Potom spusťte nový workdir s autoritativním ID:

```bash
python -m tools.real_archive_gate \
  --chat-db /cesta/k/chat.db \
  --workdir /cesta/k/dalsimu-novemu-workdir \
  --conversation-id CANONICAL_CONVERSATION_ID
```

`CANONICAL_CONVERSATION_ID` nahraďte lokálně zjištěným autoritativním canonical ID; konkrétní osobní identifikátory nepatří do veřejné dokumentace ani CI artefaktů.

Přílohy lze doplnit explicitně:

```bash
--attachments-root ~/Library/Messages/Attachments
```

## Co gate dělá

1. A1 vytvoří přes SQLite online backup konzistentní logical snapshot včetně committed WAL, tento snapshot hashne, parsuje a reconciliuje. Zdrojový `chat.db` je read-only.
2. A7 ověří A1 staging reconciliation.
3. A2 ingestuje staging do canonical SQLite a spustí structural/semantic integrity.
4. Resolver vybere přesně jednu conversation. `--target` používá pouze exact match nad title/canonical identity, participant identity nebo zdrojovými chat metadata (`display_name`, `chat_identifier`, `guid` atd.). Fuzzy ani substring match nikdy automaticky nevybere data.
5. A3 zpracuje canonical memberships a participant resolution.
6. A7 ověří participant sidecars a A1→A2→A3 vertical reconciliation.
7. A4 přepočítá pouze zvolenou conversation; nezávislý A7 arithmetic/evidence oracle znovu ověří current deterministic result.
8. A5 přečte uložené A4 candidates a A2/A3 message source read-only. Pro jeden candidate každého typu ověří bounded context, evidence dostupnost a membership/source provenance. Pokud A4 nevytvoří candidate, použije se pouze manuální provenance probe bez modelu.
9. A6 načte skutečný canonical read model, vytvoří minimální production packet, doplní A2 source provenance, projde A7 packet oracle a A5 packet adapterem.
10. Vznikne lokální `real_archive_report.json` a log každého CLI kroku.

## Datové invariants

- Zdroj před a po gate musí zůstat nezměněný v rozsahu kontrolovaném gate.
- Unknown/missing hodnoty se nesmí materializovat jako domnělé `false`, `0`, incoming/outgoing nebo odhadnutý čas.
- `is_from_me` zachovává tri-state semantics, pokud zdroj neposkytuje jistý směr.
- Sender identity a source provenance se musí zachovat i při unknown direction.
- Každý downstream packet musí být dohledatelný přes canonical IDs až ke source evidenci.

## Verdict

- `VALID` / `release_ready=true`: všechny integrity/provenance kontroly prošly a nejsou quality warnings.
- `NEEDS_REVIEW`: data nejsou tiše ztracena, ale existuje quality stav vyžadující kontrolu, například neznámé timestampy nebo chybějící attachment soubory.
- `INVALID`: selhal reconciliation, canonical integrity, participant/A4/A5/A6 provenance, target resolution nebo jiný povinný gate.

Běžná A5 redukce dlouhého kontextu na bounded selection je zaznamenána v A5 probe, ale sama o sobě není release chyba; candidate evidence se nesmí tiše ztratit. Pokud samotná candidate evidence překročí nominální `max_messages`, A5 ji rovněž nesmí tiše zahodit; gate proto vydá `A5_CONTEXT_QUALITY_WARNING` a zůstane `NEEDS_REVIEW`, dokud není evidence policy vědomě vyřešena.

## Diagnostika `NEEDS_REVIEW`

Existující lokální report lze klasifikovat bez nového importu a bez změny release verdictu:

```bash
python -m tools.real_archive_review \
  --report /PRIVATE/WORKDIR/real_archive_report.json
```

Classifier čte pouze lokální `real_archive_report.json`, odpovídající `a1_staging/manifest.json` a pokud existuje také A1 `reconciliation.json`. Na stdout nevypisuje lokální cesty, conversation IDs, kontakty, message text, source identifiers, candidate IDs ani názvy příloh.

Attachment stav má tři hodnoty:

- `NONE` — A1 nemá unresolved attachment occurrence;
- `UNVERIFIED_NO_ROOT` — unresolved attachments existují, ale při původním gate nebyl dodán `--attachments-root`; pro skutečné ověření je nutný nový gate run s explicitním rootem;
- `UNRESOLVED_WITH_ROOT` — root byl dodán a některé attachment occurrence zůstaly unresolved; ty je nutné zkontrolovat lokálně.

Pro A1 unsupported records classifier seskupuje pouze známé, statické dvojice `record_type + reason` definované reconciliation kontraktem a přidává jejich počet. Neznámý nebo budoucí důvod se nikdy nevypíše doslova a spadne do `OTHER`. `source_identifier`, message ID, attachment ID ani chat ID se do výstupu nekopírují.

A5 quality warnings se převádějí pouze na neutrální kategorie, například `UNKNOWN_TIMESTAMPS`, `EVIDENCE_EXCEEDS_CONTEXT_LIMIT`, `LEGACY_SOURCE_PROVENANCE`, `MISSING_EVIDENCE`, `MISSING_SOURCE_PROVENANCE` nebo `OTHER`. Původní detail warningu se nevypisuje. Pro diagnostiku bounded-context warningu classifier navíc může uvést pouze allowlisted `candidate_type` a čtyři numerické počty z `a5_probe.checked`: `context_message_count`, `available_message_count`, `omitted_message_count` a `evidence_message_count`. Žádné candidate/message ID ani obsah evidence se nekopírují.

Classifier nezvyšuje `NEEDS_REVIEW` na `VALID`, nepřepisuje `real_archive_report.json` a není náhradou za A7 gate.

## Ochrana dat

Nástroj neposílá zprávy žádné externí službě a report nemá ukládat text zpráv. Inventář obsahuje lokální participant/source identity hodnoty potřebné k bezpečné identifikaci conversation, proto zůstává výhradně v lokálním workdiru.

Veřejná dokumentace používá pouze neutrální placeholdery jako `EXACT_TARGET` a `CANONICAL_CONVERSATION_ID`; konkrétní osobní identifikátory nepatří do veřejné dokumentace ani CI artefaktů.

## Release hranice

Syntetický GitHub A7 gate ověřuje kód. Tento real-archive gate ověřuje konkrétní data. MVP lze označit jako release candidate až po úspěšném běhu na skutečném požadovaném archivu a po vyřešení případných `NEEDS_REVIEW` položek.

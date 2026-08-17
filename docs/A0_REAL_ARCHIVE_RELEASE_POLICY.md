# A0 — Real archive release policy

Tento dokument popisuje úzkou A0 release-policy vrstvu nad existujícím `tools.real_archive_gate`, privacy-safe diagnostikou `tools.real_archive_review` a lokálním attachment auditem `tools.real_archive_attachment_review`.

## Základní pravidlo

`real_archive_report.json` se nikdy nepřepisuje ani nepovyšuje. Zůstává autoritativním raw výstupem konkrétního gate běhu a zachovává všechny A1/A7 diagnostické informace včetně `unsupported_records` a `A1_ATTACHMENTS_MISSING`.

`tools.real_archive_release_review` vyhodnocuje **readiness canonical/text analysis vrstvy**, nikoli absolutní forenzní úplnost všech historických binárních médií. Výstup proto explicitně uvádí:

- `analysis_scope = CANONICAL_TEXT_AND_METADATA`;
- `media_completeness.state = COMPLETE | PARTIAL | UNRESOLVED`;
- případné privacy-safe `limitations`.

Release-policy nesmí tvrdit, že fyzicky chybějící binární obsah byl analyzován.

## Nezávislost raw gate a analysis release

Raw gate může legitimně zůstat `NEEDS_REVIEW`, zatímco analysis release-policy vrátí `VALID`, pokud jsou všechny zbývající raw warningy přesně klasifikované jako známé, auditovatelné omezení, které neporušuje message evidence, relation integrity ani provenance.

To není přepsání raw verdictu. Raw `NEEDS_REVIEW` zůstává zachovaný v `base_gate_verdict` a na disku se nic nemění.

## Ne­blokující unsupported případ

Release-policy může jako neblokující klasifikovat přesnou dvojici:

- `record_type = attachment`
- `reason = attachment row is not referenced by message_attachment_join`

Takový řádek existuje v Apple Messages `attachment` tabulce, ale není součástí žádné `message_attachment_join` relace. A1 reconciliation jej dál eviduje v `unsupported_records`; nic se nemaže ani nepřepisuje.

Současně A1 reconciliation samostatně exaktně kontroluje všechny source message rows, conversation relace a všechny platné message↔attachment relace. Proto zcela nereferencovaný attachment metadata řádek není sám o sobě ztracená message evidence.

## Referencované attachment binárky, které fyzicky nejsou dostupné

`A1_ATTACHMENTS_MISSING` lze v release-policy vrstvě překlasifikovat z blockeru na explicitní media limitation pouze tehdy, pokud lokální privacy-safe audit splní **všechny** podmínky:

- audit `status = PASS`;
- auditovaný missing count přesně odpovídá A1/review missing countu;
- `exact_normalization_recoverable_count = 0`;
- `relocated_unique_candidate_count = 0`;
- `ambiguous_candidate_count = 0`;
- `not_found_count = missing_occurrence_count`;
- `resolver_fix_indicated = false`;
- `relocation_investigation_indicated = false`;
- `physical_absence_likely = true`.

Teprve potom release-policy:

- ponechá raw gate beze změny;
- odstraní `A1_ATTACHMENTS_MISSING` pouze ze svého analysis-release blocker setu;
- přidá limitation `REFERENCED_ATTACHMENT_BINARIES_UNAVAILABLE`;
- nastaví `media_completeness.state = PARTIAL`;
- zachová privacy-safe missing count;
- může vrátit `release_ready = true`, pokud neexistuje žádný jiný warning/error.

Attachment metadata a message↔attachment relation evidence zůstávají zachované. Jen samotné historické binární soubory nejsou dostupné, takže nejsou zahrnuté do media-content analýzy.

## Co zůstává release-blocking

Fail-closed `NEEDS_REVIEW` zůstává zejména pro:

- jakýkoli attachment audit, který nelze dokončit;
- count mismatch mezi A1 a attachment auditem;
- attachment nalezitelný přes percent decoding nebo Unicode normalizaci;
- unikátní relokovaný basename kandidát;
- ambiguous basename kandidáty;
- `attachment row is referenced only by an unsupported relation`;
- `chat_message_join` s chybějícím ID nebo odkazem na chybějící message;
- `message_attachment_join` s chybějícím ID, chybějící message nebo chybějícím attachmentem;
- jakýkoli neznámý nebo budoucí unsupported typ/reason;
- chybějící reconciliation grouping;
- nesoulad mezi manifest `unsupported` count a součtem klasifikovaných skupin;
- jakýkoli jiný A1/A5/A7 warning nebo error.

Pokud klasifikaci nelze dokončit jednoznačně, evaluator nesmí verdict povýšit.

## Použití

Nad existujícím lokálním reportem:

```bash
python -m tools.real_archive_release_review --report /PRIVATE/WORKDIR/real_archive_report.json
```

Pokud je potřeba explicitně přepsat attachment root jen pro lokální kontrolu:

```bash
python -m tools.real_archive_release_review --report /PRIVATE/WORKDIR/real_archive_report.json --attachments-root /PRIVATE/ATTACHMENTS
```

Nástroj používá pouze privacy-safe agregace a attachment audit. Nevypisuje source identifiers, message IDs, conversation IDs, lokální cesty, attachment názvy ani message text.

## Výstup v2

`contract = real-archive-release-review-v2` přidává:

- `analysis_scope`;
- `limitations`;
- `media_completeness`;
- `review.attachment_absence` s agregovanými počty a fail-closed klasifikací.

Původní `base_gate_status`, `base_gate_verdict` a `base_release_ready` zůstávají viditelné, aby nebylo možné zaměnit analysis release za raw archive completeness.

## Exit kódy

- `0` — analysis release-policy verdict je `VALID`;
- `1` — zůstává `NEEDS_REVIEW`;
- `2` — vstup evaluatoru je neplatný.

## Důležité omezení

Tato policy vrstva není náhradou za A7 ani za real-archive gate. Nemůže přepsat `INVALID`, ignorovat neznámé warningy, doplnit chybějící evidence ani měnit A1 reconciliation data. `media_completeness = PARTIAL` je vědomě zachované omezení, nikoli tvrzení o úplném archivu.

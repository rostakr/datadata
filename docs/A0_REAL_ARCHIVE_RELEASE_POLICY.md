# A0 — Real archive release policy

Tento dokument popisuje úzkou A0 release-policy vrstvu nad existujícím `tools.real_archive_gate` a privacy-safe diagnostikou `tools.real_archive_review`.

## Základní pravidlo

`real_archive_report.json` se nikdy nepřepisuje ani nepovyšuje. Zůstává autoritativním raw výstupem konkrétního gate běhu a zachovává všechny A1/A7 diagnostické informace včetně `unsupported_records`.

`tools.real_archive_release_review` pouze vyhodnotí, zda raw `NEEDS_REVIEW` obsahuje výhradně přesně známý, audit-only A1 případ, který nepředstavuje ztrátu message evidence ani platné message↔attachment relace.

## Jediný neblokující unsupported případ

Release-policy může jako neblokující klasifikovat pouze přesnou dvojici:

- `record_type = attachment`
- `reason = attachment row is not referenced by message_attachment_join`

Takový řádek existuje v Apple Messages `attachment` tabulce, ale není součástí žádné `message_attachment_join` relace. A1 reconciliation jej dál eviduje v `unsupported_records`; nic se nemaže ani nepřepisuje.

Současně A1 reconciliation samostatně exaktně kontroluje všechny source message rows, conversation relace a všechny platné message↔attachment relace. Proto zcela nereferencovaný attachment metadata řádek není sám o sobě ztracená message evidence.

## Co zůstává release-blocking

Fail-closed `NEEDS_REVIEW` zůstává zejména pro:

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

Nástroj nejprve použije `tools.real_archive_review`, takže pracuje pouze s privacy-safe agregacemi. Nevypisuje source identifiers, message IDs, conversation IDs, lokální cesty, attachment názvy ani message text.

Výstup obsahuje:

- původní `base_gate_status`, `base_gate_verdict` a `base_release_ready`;
- nový konzervativní `status`, `verdict` a `release_ready`;
- `nonblocking_count`, `blocking_count`, `unclassified_count` a stav úplnosti klasifikace;
- původní attachment a A5 quality klasifikaci;
- privacy-safe doporučené akce.

## Exit kódy

- `0` — release-policy verdict je `VALID`;
- `1` — zůstává `NEEDS_REVIEW`;
- `2` — vstup evaluatoru je neplatný.

## Důležité omezení

Tato policy vrstva není náhradou za A7 ani za real-archive gate. Může odstranit pouze jeden přesně definovaný false-positive release blocker. Nemůže přepsat `INVALID`, ignorovat jiné warningy, doplnit chybějící evidence ani měnit A1 reconciliation data.

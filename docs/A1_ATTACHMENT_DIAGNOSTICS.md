# A1 — Privacy-safe diagnostika chybějících příloh

`tools.real_archive_attachment_review` je read-only lokální diagnostika pro případ, kdy `tools.real_archive_gate` skončí s `A1_ATTACHMENTS_MISSING` i po zadání skutečného Apple Messages `Attachments` rootu.

Nástroj **nemění A1 staging, raw gate report ani release verdict**. Jeho jediným účelem je rozlišit chybu resolveru od skutečně nedostupných binárních souborů.

## Vstup

Nástroj čte existující `real_archive_report.json`; z jeho pracovního adresáře použije `a1_staging/manifest.json` a `a1_staging/messages.jsonl`. Attachment root vezme z manifestu, případně jej lze explicitně přepsat pomocí `--attachments-root`.

```bash
python -m tools.real_archive_attachment_review --report /PRIVATE/RUN/real_archive_report.json
```

## Co se kontroluje

Pouze attachment records, které A1 při původním importu označilo `resolution_status = missing`.

Pro každý takový výskyt se interně zkusí:

1. současná A1 cesta znovu;
2. percent/URL decoding;
3. Unicode NFC normalizace;
4. Unicode NFD normalizace;
5. vyhledání stejného basename pod attachment rootem.

Basename fallback je pouze diagnostický. Pokud existuje více kandidátů, výsledek je `BASENAME_AMBIGUOUS`; nástroj žádný soubor automaticky nevybere. Pokud je k dispozici `total_bytes`, může pomoci zúžit více basename kandidátů, ale pokud velikost nic nerozliší, výsledek zůstává konzervativní.

## Privacy kontrakt

Výstup nikdy neobsahuje:

- filename ani transfer name;
- source attachment/message ID;
- message text;
- původní ani resolved absolutní cestu;
- hash soukromé hodnoty.

Výstup obsahuje jen allowlistované kategorie a agregované počty.

### Path-shape kategorie

- `FILE_URL`
- `TILDE_MESSAGES_ATTACHMENTS`
- `ABSOLUTE_MESSAGES_ATTACHMENTS`
- `RELATIVE_ATTACHMENTS_PREFIX`
- `RELATIVE_OTHER`
- `ABSOLUTE_OTHER`
- `OTHER`

### Resolution kategorie

- `CURRENT_PATH_NOW_EXISTS`
- `PERCENT_DECODE_EXACT`
- `UNICODE_NFC_EXACT`
- `UNICODE_NFD_EXACT`
- `BASENAME_UNIQUE_MATCH`
- `BASENAME_AMBIGUOUS`
- `NOT_FOUND`

## Interpretace

`resolver_fix_indicated=true` znamená, že alespoň některý původně missing soubor lze nalézt deterministickou normalizací cesty. V tom případě má následovat oprava A1 resolveru a nový gate.

`relocation_investigation_indicated=true` znamená, že existuje právě jeden basename kandidát jinde pod rootem. To ještě není automatický důkaz identity; jde o podklad pro další bezpečnou validaci.

`physical_absence_likely=true` se nastaví pouze tehdy, pokud všechny missing occurrences skončí jako `NOT_FOUND` a žádná podporovaná normalizace ani basename lookup nenajde kandidáta. I tehdy jde o diagnostický závěr, nikoli o změnu raw verdictu.

Nesoulad mezi manifestovým `attachments_missing` countem a staging records je fail-closed vstupní chyba diagnostiky.
# Worldwide international catalog

The catalog is extracted from English Wikipedia's six men's and women's international player-list indexes and the linked national-team cap tables. `data/source-manifest.json` records every discovered list, fetch/parse outcome and row count. `data/coverage.json` reports measured coverage and unresolved gaps. The existing 138 verified player profiles are retained separately.

## Attribution and license

Attribution: **Wikipedia contributors**, the linked articles in each player's `sources` and `profile_url`, retrieved at the recorded timestamp. Article links provide access to contributor history. Derived catalog content is made available under [Creative Commons Attribution-ShareAlike 4.0](https://creativecommons.org/licenses/by-sa/4.0/). See Wikipedia's [reuse policy](https://en.wikipedia.org/wiki/Wikipedia:Copyrights#Reusers'_rights_and_obligations). Changes made: extracted factual table cells, normalized team/format names and URLs, combined identical source identities, and converted the result to JSON. No Wikipedia photographs, logos, prose biographies or raw HTML are distributed. This attribution/license applies to the derived data, independently of the application code license.

## Reproduce

Install `beautifulsoup4` in the development environment, then run `python scripts/catalog.py`. The scraper uses Python's standard-library HTTP client, three bounded workers, a short pause per network request, and a resumable `/tmp/cricinator-world-source-cache` directory. Use `--cache PATH` to retain a separate cache and `--refresh` to retrieve all pages again. No credentials or paid API are required. Failures are recorded, never treated as successful zero-player sources. Run `python -m unittest tests.test_catalog` for parser checks.

## Meaning of fields

- IDs hash a normalized Wikipedia profile URL. Only identical URLs merge. Unlinked/red-linked names use source-list URL plus name, preserving entries without inventing cross-format identity.
- `countries` means international teams represented; includes regional/select teams such as West Indies and World XI, not nationality or citizenship.
- `gender` follows the source list's competition category.
- `debut` is the earliest known listed international year across parsed formats. `last_year` is the latest listed year, **not retirement status**. Incomplete source data can make both incomplete.
- `stats` contains only clearly labelled integer matches, batting runs and wickets from each format's cap table. These are source snapshot totals, not live statistics. Missing cells stay absent. Conflicting same-format statistics across team lists are omitted and that format is marked in `stats_ambiguous`; totals are never invented by adding potentially overlapping sources.
- `retrieved` is catalog-build time. Cached pages can be older; a refresh fetches them again. Wikipedia content itself can lag real matches.

## Explicit eligibility exception

Alan Jones (born 1938) is omitted despite an honorary England cap: the England Test list footnote explicitly says his 1970 match later lost Test status. Captain summary/total rows are excluded. Malformed empty span attributes are treated as one column/row; inherited header cells are cleared before numbered data rows.

## Boundaries

Discovery of all six indexes does not prove all players ever are covered. Lists can be absent, incomplete, outdated, inaccessible or differently structured. `complete` remains false. Profile redirects are not resolved, and unlinked people can appear multiple times. Never merge people merely because names match. Sparse source rows do not establish role, batting/bowling hand, leagues, awards or retirement. Catalog size is distinct from accurate, distinguishable gameplay coverage. Review failed/empty sources and unknown fields before making coverage claims.

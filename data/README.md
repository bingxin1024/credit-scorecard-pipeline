# Data

`data/raw/` is git-ignored. Put the raw files here:

| Dataset | File | Source |
|---|---|---|
| Lending Club accepted loans 2007–2018Q4 | `data/raw/accepted_2007_to_2018Q4.csv.gz` | Kaggle `wordsforthewise/lending-club` |
| UCI default of credit card clients (Phase 3) | downloaded automatically with `ucimlrepo` (`fetch_ucirepo(id=350)`) | UCI ML repository |

The Lending Club adapter reads the gzipped CSV directly (`pd.read_csv(..., compression="gzip")`).
A parsed copy is cached in `data/cache/` (also git-ignored) so that re-runs do not re-parse the 390 MB file.

Tests never read `data/raw`; they use synthetic fixtures only.

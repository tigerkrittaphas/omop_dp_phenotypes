# OMOP DP Phenotypes

Interactive **Svelte** dashboard for the OHDSI Phenotype Library: cohorts as a force-directed graph (shared OMOP concepts define edges), with **differentially private** patient counts and pairwise cohort overlaps powered by **Liquid Legions** sketches when you build data from a local OMOP CDM. Public GitHub Pages builds use **`--demo`** so only **synthetic** JSON is bundled (no real patient statistics).

## Public demo data vs local real counts

| File | Purpose | Git |
|---|---|---|
| `app/public/phenotype_counts_dp_demo.json` | Fictional cohort sizes for demos and Pages | Safe to commit |
| `app/public/ll_sketches_demo.{bin,json}` | Synthetic LL sketches (powers the overlap explorer in demo mode) | Safe to commit |
| `app/public/phenotype_counts_dp.json` | Produced by `publish_to_app.py` from your real CDM | **Ignored** by git; do not force-add |
| `app/public/ll_sketches.{bin,json}` | Produced by `publish_to_app.py` from real DP sketches | **Ignored** by git; do not force-add |

Regenerate the demo bundle anytime:

```bash
# 1. Synthetic cohort sizes per phenotype (deterministic, no real data)
uv run python scripts/generate_demo_phenotype_counts.py

# 2. Synthetic LL sketches at the same (m, a, ε) as the production pipeline.
#    Re-syncs dp_count in the demo JSON to the Golden Legion estimates so the
#    table and the overlap panel agree on cardinalities.
uv run python scripts/generate_demo_ll_sketches.py
```

Commit all three demo files (`phenotype_counts_dp_demo.json`, `ll_sketches_demo.json`, `ll_sketches_demo.bin`) and push — the GitHub Pages workflow builds with `--demo`, which makes Vite point both the counts and the LL sketch loaders at the `*_demo` files.

## Local development (frontend)

```bash
cd app
npm ci
npm run dev
```

**Demo data locally** (same JSON as GitHub Pages):

```bash
npm run dev:demo
```

Open the URL Vite prints (usually `http://localhost:5173/`).

### Production build

The app uses **`run-vite.mjs`** so **`--demo`** works (the bare **`vite`** CLI rejects unknown flags).

- **Local real counts** — expects `phenotype_counts_dp.json` from `run_dp.py`:

```bash
npm run build
```

- **Demo / public deploy** — fetches `phenotype_counts_dp_demo.json`:

```bash
npm run build -- --demo
# or
npm run build:demo
```

CI may set **`VITE_DEMO_BUILD=1`** instead of `--demo`.

**Avoid** calling **`vite build`** directly if you need **`--demo`**; use **`npm run build`** or **`node run-vite.mjs`** instead.

```bash
npm run preview
```

## Differential privacy pipeline (Python + R)

Use this when you have a **local OMOP CDM** (for example DuckDB) and want real counts plus pairwise overlaps under DP — not for publishing raw statistics to GitHub.

### 1. Python environment

```bash
uv sync
```

### 2. Phenotype definitions (public metadata)

```bash
uv run python src/dp_preprocessing/fetch_phenotype_library.py
```

Writes `data/phenotype_library.json`. Optional: edit `data/phenotypes_classification.csv` for clinical-system labels in the UI.

### 3. Build the cohort table from authoritative ATLAS definitions

```bash
Rscript src/dp_preprocessing/generate_cohorts.R
```

Uses CirceR + CohortGenerator to translate the ATLAS JSON definitions into OMOP SQL and execute it against your local CDM. Writes:

- `outputs/cohort_counts.csv` — per-cohort patient totals
- `data/cohorts.duckdb` — the `cohort(cohort_definition_id, subject_id, …)` table the sketch builder reads from

### 4. Build DP Liquid Legions sketches

```bash
uv run python -m src.liquid_legions.build_sketches \
    --epsilon 2.0 --m 50000 --a 10.0 \
    --cohort-db data/cohorts.duckdb \
    --out outputs/ll_sketches.npz
```

Reads the ATLAS-generated `cohort` table, builds one sketch per cohort, applies binary randomized response at the given ε, and saves the bundle.

### 5. Publish to the dashboard

```bash
uv run python -m src.liquid_legions.publish_to_app
```

Computes the Golden Legion cardinality per cohort and writes:

- `app/public/phenotype_counts_dp.json` — cohort metadata + DP cardinalities
- `app/public/ll_sketches.bin` + `ll_sketches.json` — bit-packed sketches + metadata for the in-browser overlap explorer

Then use **`npm run build`** (without `--demo`) to test locally. For git push or GitHub Pages, use **`npm run build -- --demo`** so only `phenotype_counts_dp_demo.json` is used.

## Privacy parameters (Liquid Legions sketch)

| Parameter | Meaning | Typical value |
|---|---|---|
| ε (epsilon) | Per-sketch privacy budget — lower = more privacy, more noise. Total budget composes as Kε for K cohorts (use zCDP/RDP accountants for tighter bounds). | 1 – 4 |
| m  | Register count per sketch. More registers = lower variance; linear cost in memory and bandwidth. | 50_000 |
| a  | Truncated-exponential decay. Tune so the Golden Legion window covers your cohort size range; smaller `a` helps large cohorts, larger `a` helps small cohorts. | 6 – 10 |

A Liquid Legions sketch has sensitivity = 1 bit per person (each patient touches exactly one register), so binary randomized response with flip probability `1 / (1 + e^ε)` is ε-DP per sketch. Once published, **any** pairwise or k-way overlap is free post-processing — no extra budget per query. Implementation: `src/liquid_legions/liquid_legions.py`, `src/liquid_legions/build_sketches.py`, `src/liquid_legions/publish_to_app.py`. The in-browser estimator is in `app/src/lib/liquidLegions.js`.

## Tests

```bash
uv run pytest tests/
```

## Project layout

```
app/                                    — Svelte + Vite dashboard (GitHub Pages target)
  public/phenotype_counts_dp_demo.json  — synthetic counts (commit for Pages)
  public/phenotype_counts_dp.json       — local DP cardinalities from publish_to_app.py (gitignored)
  public/ll_sketches.bin                — bit-packed DP sketches for the overlap explorer (gitignored)
  public/ll_sketches.json               — sketch metadata + precomputed cardinalities (gitignored)
  src/lib/liquidLegions.js              — in-browser LL estimator (Golden Legion + correct-OR MLE)
scripts/generate_demo_phenotype_counts.py — writes *_demo.json (synthetic, public)
src/dp_preprocessing/
  fetch_phenotype_library.py            — download PhenotypeLibrary metadata → data/
  phenotypes.py                         — load JSON + system labels
  generate_cohorts.R                    — CirceR / CohortGenerator → cohort_counts.csv + cohorts.duckdb
src/liquid_legions/
  liquid_legions.py                     — sketch class + ε-DP randomized response
  build_sketches.py                     — cohort table → DP-noised sketches (.npz)
  publish_to_app.py                     — sketches → app/public bundle + cardinalities JSON
data/                                   — phenotype JSON + cohorts.duckdb (gitignored except what you add)
outputs/                                — cohort_counts.csv + ll_sketches.npz (local; gitignored)
```

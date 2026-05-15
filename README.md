# OMOP DP Phenotypes

Interactive **Svelte** dashboard for the OHDSI Phenotype Library: cohorts as a force-directed graph (shared OMOP concepts define edges), with **differentially private** patient counts when you build data from a local OMOP CDM. Public GitHub Pages builds use **`--demo`** so only **synthetic** JSON is bundled (no real patient statistics).

## Public demo data vs local real counts

| File | Purpose | Git |
|---|---|---|
| `app/public/phenotype_counts_dp_demo.json` | Fictional counts for demos and Pages | Safe to commit |
| `app/public/phenotype_counts_dp.json` | Produced by `run_dp.py` from real CDM counts | **Ignored** by git (`*.json`); do not force-add |

Regenerate the demo file anytime:

```bash
python3 scripts/generate_demo_phenotype_counts.py
```

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

### Project Pages base path

`vite.config.js` sets `base` to `/<repository>/` when `GITHUB_PAGES=true` (set in the deploy workflow). Locally, `base` defaults to `/`. Override manually:

```bash
VITE_BASE_PATH=/my-repo/ npm run build
```

## GitHub Pages deployment

1. In repo **Settings → Pages**, set **Build and deployment → Source** to **GitHub Actions**.
2. Push to `main` or `master`, or run **Actions → Deploy GitHub Pages → Run workflow**.

The workflow runs **`npm run build -- --demo`** so the published site never embeds the real JSON filename for local-only data.

## Real differential privacy pipeline (Python + optional R)

Use this when you have a **local OMOP CDM** (for example DuckDB) and want true counts + DP noise—not for publishing raw counts to GitHub.

### 1. Python environment

```bash
uv sync
```

### 2. Phenotype definitions (public metadata)

```bash
uv run python src/dp_preprocessing/fetch_phenotype_library.py
```

Writes `data/phenotype_library.json`. Optional: edit `data/phenotypes_classification.csv` for clinical-system labels in the UI.

### 3. Cohort counts (choose one)

`src/dp_preprocessing/generate_cohorts.R` → `outputs/cohort_counts.csv` (requires OMOP DuckDB paths set in the script / env; see `.env.sample`)

### 4. Apply DP and refresh dashboard JSON

```bash
uv run python src/dp_preprocessing/run_dp.py
```

This writes **`app/public/phenotype_counts_dp.json`** (real DP counts). Use **`npm run build`** (without `--demo`) to test locally. For git push or GitHub Pages, use **`npm run build -- --demo`** so only `phenotype_counts_dp_demo.json` is used.

## Privacy parameters (Gaussian mechanism)

| Parameter | Meaning | Typical value |
|---|---|---|
| ε (epsilon) | Privacy budget — lower = more privacy, more noise | 0.1 – 1.0 |
| δ (delta) | Failure probability | 1e-5 |

Sensitivity uses the max number of phenotypes any single patient matches (when a DuckDB connection is available). See `run_dp.py` and `src/dp_preprocessing/phenotype_queries.py`.

## Tests

```bash
uv run pytest tests/
```

## Project layout

```
app/                                    — Svelte + Vite dashboard (GitHub Pages target)
  public/phenotype_counts_dp_demo.json  — synthetic counts (commit for Pages)
  public/phenotype_counts_dp.json       — local real DP output from run_dp.py (gitignored)
scripts/generate_demo_phenotype_counts.py — writes *_demo.json
src/dp_preprocessing/
  fetch_phenotype_library.py            — download PhenotypeLibrary metadata → data/
  phenotypes.py                         — load JSON + system labels
  phenotype_queries.py                  — DuckDB count queries + overlap sensitivity
  run_dp.py                             — OpenDP Gaussian noise → CSV + phenotype_counts_dp.json
  generate_cohorts.R                    — CirceR / CohortGenerator → cohort_counts.csv
data/                                   — phenotype JSON + classification (gitignored except what you add)
outputs/                                — cohort / DP CSVs (local; gitignored)
```

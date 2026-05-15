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

See **GitHub Pages deployment** below for how **`base`** is set on `*.github.io` (project vs user site).

## GitHub Pages deployment

The site must be published from the **built** Vite output (`app/dist`), not from the repo root. If your Pages URL shows the **README** or a Jekyll page, the source is almost certainly set to **“Deploy from a branch”** on `/ (root)` instead of **GitHub Actions**.

### One-time setup

1. Open the repo on GitHub → **Settings** → **Pages** (under “Code and automation”).
2. Under **Build and deployment → Source**, choose **GitHub Actions** (not “Deploy from a branch”).
3. If you previously used a branch, pick **None** or switch to Actions until only the workflow deploys the site.
4. Push to `main` / `master` or run **Actions** → **Deploy GitHub Pages** → **Run workflow**.
5. After a green run, open the site at **`https://<owner>.github.io/<repository>/`** (project site) or **`https://<owner>.github.io/`** if the repository is **`<owner>.github.io`** (user site).

The workflow in `.github/workflows/deploy-pages.yml` runs **`npm ci`** and **`npm run build -- --demo`** in **`app/`**, then uploads **`app/dist`** as the Pages artifact.

`vite.config.js` sets the asset **`base`**: **`/<repository>/`** for normal project repos, **`/`** when the repo name ends with **`.github.io`** (user/org site). Locally, `base` defaults to `/`. Override in CI or locally:

```bash
VITE_BASE_PATH=/my-repo/ npm run build
```

### Checklist if the app is blank or 404

- **Source** is **GitHub Actions** and a **Deploy GitHub Pages** workflow run completed successfully.
- You are using the **Pages** URL (`*.github.io`), not the normal repo file browser (`github.com/...`).
- For a **project** repo, paths are under `/<repository>/`; the workflow sets `GITHUB_PAGES=true` so Vite uses the correct `base` (and `/<owner>.github.io/` repos use base `/`).

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

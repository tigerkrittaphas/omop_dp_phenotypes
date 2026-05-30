#!/usr/bin/env python3
"""
Build a synthetic app/public/phenotype_counts_dp_demo.json for GitHub Pages / public demos.

Counts are **not** derived from any real CDM or cohort statistics — only deterministic
fictional numbers seeded from cohort_id. Structure matches what the Svelte app expects:
cohort_id, phenotype_name, dp_count, concept_ids, system.

Inputs (public metadata only):
  - data/phenotype_library.json  (from OHDSI PhenotypeLibrary fetch)
  - data/phenotypes_classification.csv  (optional; cohort → clinical system)

Env:
  MAX_PHENOTYPES — if set, only include the first N entries (smaller file for demos)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LIBRARY = REPO_ROOT / "data" / "phenotype_library.json"
DEFAULT_CLASSIFICATION = REPO_ROOT / "data" / "phenotypes_classification.csv"
DEFAULT_OUT = REPO_ROOT / "app" / "public" / "phenotype_counts_dp_demo.json"


def load_classification_map(path: Path) -> dict[int, str]:
    if not path.exists():
        return {}
    mapping: dict[int, str] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                mapping[int(row["Cohort ID"])] = row["Clinical System Classification"].strip()
            except (KeyError, ValueError):
                continue
    return mapping


def synthetic_dp_count(cohort_id: int) -> int:
    """Deterministic fake count in a plausible range; not tied to any dataset."""
    # Large odd multiplier → pseudo-uniform spread without using random()
    x = (cohort_id * 0x9E3779B9) & 0xFFFFFFFF
    return 350 + (x % 14_500)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--library",
        type=Path,
        default=Path(os.environ.get("PHENOTYPE_LIBRARY_PATH", DEFAULT_LIBRARY)),
        help="Path to phenotype_library.json",
    )
    parser.add_argument(
        "--classification",
        type=Path,
        default=DEFAULT_CLASSIFICATION,
        help="Optional cohort system labels CSV",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUT,
        help="Write dashboard JSON here",
    )
    args = parser.parse_args()

    library_path = args.library
    if not library_path.is_absolute():
        library_path = REPO_ROOT / library_path
    if not library_path.exists():
        raise SystemExit(
            f"Missing {library_path}\n"
            "Fetch public definitions with:\n"
            "  uv run python src/dp_preprocessing/fetch_phenotype_library.py"
        )

    raw: list[dict] = json.loads(library_path.read_text(encoding="utf-8"))
    class_map = load_classification_map(args.classification)

    max_n = os.environ.get("MAX_PHENOTYPES")
    if max_n:
        raw = raw[: int(max_n)]

    records: list[dict] = []
    for entry in raw:
        concept_ids = entry.get("concept_ids") or []
        if not concept_ids:
            continue
        cid = int(entry["cohort_id"])
        records.append(
            {
                "cohort_id": cid,
                "phenotype_name": str(entry["name"]),
                "dp_count": synthetic_dp_count(cid),
                "concept_ids": [int(x) for x in concept_ids],
                "system": class_map.get(cid, "Other"),
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"Wrote {len(records)} synthetic records to {args.output}")


if __name__ == "__main__":
    main()

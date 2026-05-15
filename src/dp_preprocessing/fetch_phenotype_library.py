"""
Fetch phenotype definitions from the OHDSI PhenotypeLibrary GitHub repository.

Downloads the Cohorts.csv index and the ATLAS JSON for each accepted,
condition-based cohort definition. Extracts the concept IDs used in the
PrimaryCriteria and writes a simplified JSON file to:

    data/phenotype_library.json

Usage:
    uv run python scripts/fetch_phenotype_library.py

Options (env vars):
    MAX_PHENOTYPES   - cap on how many phenotypes to fetch (default: 50)
    FILTER_DOMAIN    - only fetch phenotypes that include ConditionOccurrence (default: true)
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

import pandas as pd

BASE_RAW = "https://raw.githubusercontent.com/OHDSI/PhenotypeLibrary/main/inst"
COHORTS_CSV_URL = f"{BASE_RAW}/Cohorts.csv"
COHORT_JSON_URL = BASE_RAW + "/cohorts/{cohort_id}.json"

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
OUT_FILE = DATA_DIR / "phenotype_library.json"

MAX_PHENOTYPES = os.environ.get("MAX_PHENOTYPES")
FILTER_DOMAIN = os.environ.get("FILTER_DOMAIN", "true").lower() != "false"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch_url(url: str, retries: int = 3) -> bytes:
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                return resp.read()
        except Exception as exc:
            if attempt == retries - 1:
                raise
            print(f"  Retry {attempt + 1}/{retries} for {url}: {exc}")
            time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def _extract_concept_ids_from_json(cohort_json: dict) -> list[int]:
    """
    Extract all OMOP concept IDs used in the primary event criteria.

    Strategy:
    1. Find which ConceptSet IDs are referenced in PrimaryCriteria.CriteriaList
    2. Resolve those IDs against the ConceptSets array
    3. Return deduplicated list of CONCEPT_IDs
    """
    concept_sets: dict[int, list[int]] = {}  # cs_id -> [concept_id, ...]

    for cs in cohort_json.get("ConceptSets", []):
        cs_id = cs.get("id")
        items = cs.get("expression", {}).get("items", [])
        concept_ids = [
            item["concept"]["CONCEPT_ID"]
            for item in items
            if not item.get("isExcluded", False)
            and "concept" in item
        ]
        if concept_ids:
            concept_sets[cs_id] = concept_ids

    # Find codeset IDs referenced in primary criteria
    primary_codeset_ids: set[int] = set()
    for criterion in cohort_json.get("PrimaryCriteria", {}).get("CriteriaList", []):
        for _event_type, event_def in criterion.items():
            if isinstance(event_def, dict) and "CodesetId" in event_def:
                primary_codeset_ids.add(event_def["CodesetId"])

    # Resolve
    result: list[int] = []
    for cs_id in primary_codeset_ids:
        result.extend(concept_sets.get(cs_id, []))

    # Fallback: if primary criteria reference no concept sets, return all concept IDs
    if not result:
        for ids in concept_sets.values():
            result.extend(ids)

    return sorted(set(result))


def _is_condition_based(cohort_json: dict) -> bool:
    """Return True if any primary criterion is a ConditionOccurrence event."""
    for criterion in cohort_json.get("PrimaryCriteria", {}).get("CriteriaList", []):
        if "ConditionOccurrence" in criterion:
            return True
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)

    # 1. Fetch the cohort index
    print(f"Fetching cohort index from {COHORTS_CSV_URL} ...")
    csv_bytes = _fetch_url(COHORTS_CSV_URL)
    catalog = pd.read_csv(io.BytesIO(csv_bytes), low_memory=False)
    print(f"  Total cohorts in catalog: {len(catalog)}")

    # 2. Exclude withdrawn/deprecated; include Accepted, Pending peer review, Pending
    status_col = next((c for c in catalog.columns if c.lower() == "status"), None)
    if status_col:
        exclude = {"withdrawn", "deprecated"}
        catalog = catalog[~catalog[status_col].str.lower().isin(exclude)]
    print(f"  Non-withdrawn cohorts: {len(catalog)}")

    # 3. Filter to condition-based phenotypes using domainConditionOccurrence
    co_col = next(
        (c for c in catalog.columns
         if c.lower() in ("domainconditionoccurrence", "conditionoccurrence", "condition_occurrence")),
        None,
    )
    if co_col and FILTER_DOMAIN:
        catalog_filtered = catalog[catalog[co_col].fillna(0).astype(float) == 1.0]
        if len(catalog_filtered) > 0:
            catalog = catalog_filtered
            print(f"  After ConditionOccurrence domain filter: {len(catalog)} cohorts")

    # Identify name column
    name_col = next(
        (c for c in catalog.columns if c.lower() in ("cohortname", "cohort_name", "name")),
        None,
    )
    id_col = next(
        (c for c in catalog.columns if c.lower() in ("cohortid", "cohort_id", "id")),
        None,
    )
    if not name_col or not id_col:
        print(f"ERROR: could not find name/id columns. Columns: {list(catalog.columns)}")
        sys.exit(1)

    # Limit to MAX_PHENOTYPES
    # if MAX_PHENOTYPES null include all phenotypes
    if MAX_PHENOTYPES and len(catalog) > MAX_PHENOTYPES:
        catalog = catalog.head(MAX_PHENOTYPES)
        print(f"  Fetching JSON for up to {MAX_PHENOTYPES} cohorts...")

    # 4. For each cohort, fetch JSON and extract concept IDs
    phenotypes: list[dict] = []
    for _, row in catalog.iterrows():
        cohort_id = int(row[id_col])
        cohort_name = str(row[name_col]).strip()
        url = COHORT_JSON_URL.format(cohort_id=cohort_id)

        try:
            raw = _fetch_url(url)
            cohort_json = json.loads(raw)
        except Exception as exc:
            print(f"  SKIP cohort {cohort_id} ({cohort_name}): {exc}")
            continue

        if FILTER_DOMAIN and not _is_condition_based(cohort_json):
            print(f"  SKIP cohort {cohort_id} ({cohort_name}): not condition-based")
            continue

        concept_ids = _extract_concept_ids_from_json(cohort_json)
        phenotypes.append({
            "cohort_id": cohort_id,
            "name": cohort_name,
            "concept_ids": concept_ids,
        })
        print(f"  OK   cohort {cohort_id}: {cohort_name!r} — {len(concept_ids)} concept IDs")
        time.sleep(0.1)  # be polite to GitHub

    print(f"\nFetched {len(phenotypes)} phenotypes.")

    # 5. Write output
    OUT_FILE.write_text(json.dumps(phenotypes, indent=2))
    print(f"Written to {OUT_FILE}")


if __name__ == "__main__":
    main()

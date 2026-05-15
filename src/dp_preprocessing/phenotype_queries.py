"""Build and execute phenotype count queries against local OMOP CDM CSV files via DuckDB."""

from __future__ import annotations

import duckdb
import pandas as pd

from phenotypes import PHENOTYPES, Phenotype


def _build_union_sql(phenotypes: list[Phenotype]) -> str:
    """
    Build a single UNION ALL query counting distinct patients per phenotype.

    Each phenotype can reference multiple OMOP concept IDs (its concept set),
    so the WHERE clause uses IN (...) rather than a single equality check.
    Phenotypes with no concept IDs are skipped.
    """
    blocks: list[str] = []
    for p in phenotypes:
        if not p.concept_ids:
            continue
        escaped_name = p.name.replace("'", "''")
        concept_id_list = ", ".join(str(c) for c in p.concept_ids)
        block = (
            f"SELECT '{escaped_name}' AS phenotype_name,\n"
            f"       {p.cohort_id} AS cohort_id,\n"
            f"       COUNT(DISTINCT person_id) AS patient_count\n"
            f"FROM condition_occurrence\n"
            f"WHERE condition_concept_id IN ({concept_id_list})"
        )
        blocks.append(block)

    if not blocks:
        raise ValueError("No phenotypes with concept IDs to query.")

    return "\nUNION ALL\n".join(blocks)


def _check_mapping_coverage(con: duckdb.DuckDBPyConnection) -> float:
    """Return the fraction of condition_occurrence rows with a mapped concept_id > 0."""
    sql = """
        SELECT
            SUM(CASE WHEN condition_concept_id > 0 THEN 1 ELSE 0 END)::DOUBLE
            / COUNT(*) AS mapped_fraction
        FROM condition_occurrence
    """
    try:
        row = con.execute(sql).fetchone()
        return float(row[0]) if row and row[0] is not None else 1.0
    except (duckdb.Error, ValueError, TypeError):
        return 1.0


def get_max_patient_phenotype_overlap(
    con: duckdb.DuckDBPyConnection,
    phenotypes: list[Phenotype] | None = None,
) -> int:
    """
    Return the maximum number of distinct phenotypes matched by any single patient.

    This is the squared L2 sensitivity of the count vector:
        L2_SENSITIVITY = sqrt(get_max_patient_phenotype_overlap(...))

    Each phenotype becomes one subquery that emits (person_id, cohort_id) pairs;
    we UNION ALL them, count distinct cohort_ids per person, and take the MAX.
    """
    if phenotypes is None:
        phenotypes = PHENOTYPES

    blocks: list[str] = []
    for p in phenotypes:
        if not p.concept_ids:
            continue
        concept_id_list = ", ".join(str(c) for c in p.concept_ids)
        block = (
            f"SELECT DISTINCT person_id, {p.cohort_id} AS cohort_id\n"
            f"FROM condition_occurrence\n"
            f"WHERE condition_concept_id IN ({concept_id_list})"
        )
        blocks.append(block)

    if not blocks:
        return 1

    union_sql = "\nUNION ALL\n".join(blocks)
    sql = f"""
        SELECT MAX(phenotype_count) AS max_overlap
        FROM (
            SELECT person_id, COUNT(DISTINCT cohort_id) AS phenotype_count
            FROM ({union_sql}) AS memberships
            GROUP BY person_id
        )
    """
    row = con.execute(sql).fetchone()
    return int(row[0]) if row and row[0] is not None else 1


def fetch_all_phenotype_counts(
    con: duckdb.DuckDBPyConnection,
    phenotypes: list[Phenotype] | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """
    Count distinct patients per phenotype in a single query pass.

    Returns:
        df:       DataFrame with columns [phenotype_name, cohort_id, patient_count]
        warnings: Human-readable warning strings (empty when everything looks fine)
    """
    if phenotypes is None:
        phenotypes = PHENOTYPES

    warnings: list[str] = []

    mapped_frac = _check_mapping_coverage(con)
    if mapped_frac < 0.5:
        warnings.append(
            f"Only {mapped_frac:.1%} of condition_occurrence rows have a mapped "
            "concept_id > 0. Many phenotype counts may be zero."
        )

    sql = _build_union_sql(phenotypes)
    df = con.execute(sql).df()
    df["patient_count"] = df["patient_count"].astype(int)
    return df, warnings

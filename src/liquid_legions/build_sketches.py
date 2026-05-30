"""Build DP Liquid Legions sketches for every phenotype.

Reads person_ids per cohort from the cohort table produced by
`src/dp_preprocessing/generate_cohorts.R` (CirceR + CohortGenerator translating
the authoritative ATLAS phenotype definitions). For each cohort that has rows,
builds one Liquid Legions sketch, applies binary randomized response at the
given ε, and writes a compressed .npz bundle.

Run `src/dp_preprocessing/generate_cohorts.R` first to populate the cohort DB.

Example:
    uv run python -m src.liquid_legions.build_sketches \\
        --epsilon 2.0 --m 50000 --a 8.0 \\
        --cohort-db data/cohorts.duckdb \\
        --out outputs/ll_sketches.npz
"""

from __future__ import annotations

import os
from argparse import ArgumentParser
from pathlib import Path

import duckdb
import numpy as np
from dotenv import load_dotenv
from tqdm import tqdm

from src.dp_preprocessing.phenotypes import load_phenotypes
from .liquid_legions import LiquidLegions

load_dotenv()


def fetch_person_ids(con: duckdb.DuckDBPyConnection, cohort_id: int) -> list[int]:
    """Return distinct person_ids (subject_ids) in the given ATLAS-generated cohort."""
    rows = con.execute(
        "SELECT DISTINCT subject_id FROM cohort WHERE cohort_definition_id = ?",
        [cohort_id],
    ).fetchall()
    return [r[0] for r in rows]


def build_sketches(
    cohort_db_path: Path,
    m: int,
    a: float,
    salt: str,
    epsilon: float,
    seed: int,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Build one DP-noised sketch per cohort present in the cohort DB.

    Reads the `cohort` table produced by generate_cohorts.R; only phenotypes
    with at least one matched subject become sketches. Returns
    (cohort_ids, bits_matrix, p_flip).
    """
    phenotypes = load_phenotypes()
    rng = np.random.default_rng(seed)
    con = duckdb.connect(str(cohort_db_path), read_only=True)

    available = {
        int(r[0])
        for r in con.execute("SELECT DISTINCT cohort_definition_id FROM cohort").fetchall()
    }
    print(f"  {len(available)} cohorts present in {cohort_db_path}")

    cohort_ids: list[int] = []
    bits_rows: list[np.ndarray] = []
    for p in tqdm(phenotypes, desc="cohorts"):
        if p.cohort_id not in available:
            continue
        persons = fetch_person_ids(con, p.cohort_id)
        if not persons:
            continue
        s = LiquidLegions(m=m, a=a, salt=salt)
        s.add_many(persons)
        s.apply_dp(epsilon=epsilon, rng=rng)
        cohort_ids.append(p.cohort_id)
        bits_rows.append(s.bits)

    con.close()
    p_flip = 1.0 / (1.0 + np.exp(epsilon))
    return (
        np.asarray(cohort_ids, dtype=np.int64),
        np.stack(bits_rows).astype(np.int8),
        float(p_flip),
    )


def save_sketches(
    out_path: Path,
    cohort_ids: np.ndarray,
    bits_matrix: np.ndarray,
    m: int,
    a: float,
    salt: str,
    epsilon: float,
    p_flip: float,
    seed: int,
) -> None:
    if (bits_matrix == 0).all() and epsilon > 0 and p_flip > 0:
        raise RuntimeError("Refusing to save: bits matrix is all-zero (sketches likely un-built).")
    if p_flip <= 0.0:
        raise RuntimeError(
            "Refusing to save sketches with p_flip == 0 (no DP noise applied). "
            "Publishing un-noised LL bits is a membership-inference oracle."
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out_path,
        cohort_ids=cohort_ids,
        bits=bits_matrix,
        m=np.int64(m),
        a=np.float64(a),
        salt=np.str_(salt),
        epsilon=np.float64(epsilon),
        p_flip=np.float64(p_flip),
        seed=np.int64(seed),
    )


def load_sketches(path: Path) -> tuple[dict[int, LiquidLegions], dict]:
    """Reload sketches saved by save_sketches. Returns (sketches_by_id, metadata)."""
    with np.load(path, allow_pickle=False) as data:
        m = int(data["m"])
        a = float(data["a"])
        salt = str(data["salt"])
        epsilon = float(data["epsilon"])
        p_flip = float(data["p_flip"])
        cohort_ids = data["cohort_ids"].tolist()
        bits = data["bits"]
    sketches: dict[int, LiquidLegions] = {}
    for cid, b in zip(cohort_ids, bits):
        s = LiquidLegions(m=m, a=a, salt=salt)
        s.bits = b.astype(np.int8)
        s._dp_p_flip = p_flip
        sketches[int(cid)] = s
    meta = {"m": m, "a": a, "salt": salt, "epsilon": epsilon, "p_flip": p_flip}
    return sketches, meta


def main() -> None:
    parser = ArgumentParser(description="Build DP Liquid Legions sketches for all phenotypes.")
    parser.add_argument(
        "--cohort-db",
        dest="cohort_db",
        type=Path,
        default=Path(os.getenv("COHORT_DUCKDB_PATH", "data/cohorts.duckdb")),
        help="Path to the cohort DuckDB produced by generate_cohorts.R.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("outputs/ll_sketches.npz"),
        help="Output .npz path.",
    )
    parser.add_argument("--m", type=int, default=50_000, help="Number of registers.")
    parser.add_argument("--a", type=float, default=10.0, help="Decay parameter.")
    parser.add_argument("--salt", type=str, default="ll", help="Hash salt (public).")
    parser.add_argument("--epsilon", type=float, default=2.0, help="Per-sketch ε.")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed for DP flips.")
    args = parser.parse_args()

    if not args.cohort_db.exists():
        raise SystemExit(
            f"Cohort DuckDB not found at {args.cohort_db} — "
            f"run src/dp_preprocessing/generate_cohorts.R first."
        )

    p_flip = 1.0 / (1.0 + np.exp(args.epsilon))
    print(f"Building sketches from {args.cohort_db} → {args.out}")
    print(f"  m={args.m}, a={args.a}, ε={args.epsilon}, p_flip={p_flip:.4f}")

    cohort_ids, bits_matrix, p_flip = build_sketches(
        cohort_db_path=args.cohort_db,
        m=args.m,
        a=args.a,
        salt=args.salt,
        epsilon=args.epsilon,
        seed=args.seed,
    )
    save_sketches(
        args.out,
        cohort_ids,
        bits_matrix,
        m=args.m,
        a=args.a,
        salt=args.salt,
        epsilon=args.epsilon,
        p_flip=p_flip,
        seed=args.seed,
    )
    size_mb = args.out.stat().st_size / 1e6
    print(
        f"Saved {len(cohort_ids)} sketches → {args.out} "
        f"({size_mb:.2f} MB on disk, bits shape={bits_matrix.shape})"
    )


if __name__ == "__main__":
    main()

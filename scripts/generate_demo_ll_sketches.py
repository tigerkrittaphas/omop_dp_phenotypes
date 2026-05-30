#!/usr/bin/env python3
"""Generate synthetic Liquid Legions sketches for the public GH Pages demo.

Inputs (must already exist):
  app/public/phenotype_counts_dp_demo.json  (from generate_demo_phenotype_counts.py)

Outputs (overwritten, then committed to the repo for the Pages deploy):
  app/public/ll_sketches_demo.bin
  app/public/ll_sketches_demo.json
  app/public/phenotype_counts_dp_demo.json   (dp_count overwritten with Golden Legion
                                              estimates so the table and overlap panel agree)

Sampling model — purely synthetic, not derived from any real cohort:
  - A global synthetic patient pool of POPULATION ids.
  - Each clinical system gets a roughly equal slice of the pool.
  - For a cohort of synthetic size n in system S: draw (SYSTEM_BIAS · n) ids from
    system S's slice and the rest from the global pool. This produces overlap
    structure that clusters by system — visually informative for the demo
    without any link to real patient statistics.

The output sketches go through the same DP randomized-response step as the
production pipeline, so the demo bundle is mathematically valid (ε-DP w.r.t.
the fake input cohorts) — there's nothing real to protect, but the size,
shape, and code paths match what a real deploy produces.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np
from tqdm import tqdm

# Local imports — same machinery as the production pipeline
from src.liquid_legions.liquid_legions import LiquidLegions
from src.liquid_legions.publish_to_app import bit_pack, golden_legion_cardinality


DEFAULT_DEMO_JSON = REPO_ROOT / "app" / "public" / "phenotype_counts_dp_demo.json"
DEFAULT_OUT_DIR = REPO_ROOT / "app" / "public"

# Synthetic-population knobs
POPULATION = 200_000     # global synthetic patient pool
SYSTEM_BIAS = 0.8        # fraction of each cohort drawn from its system slice
SYSTEM_SLICE_SEED = 0xC0FFEE  # fixed: stable system → id partition across runs


def build_system_slices(systems: list[str]) -> dict[str, np.ndarray]:
    """Deterministic partition of POPULATION into per-system patient slices."""
    rng = np.random.default_rng(SYSTEM_SLICE_SEED)
    all_ids = rng.permutation(POPULATION).astype(np.int64)
    slice_size = POPULATION // max(1, len(systems))
    return {
        sys: all_ids[i * slice_size:(i + 1) * slice_size]
        for i, sys in enumerate(sorted(systems))
    }


def sample_person_set(
    cohort_id: int,
    n: int,
    system: str,
    system_slices: dict[str, np.ndarray],
    base_seed: int,
) -> np.ndarray:
    """Sample n distinct synthetic person ids, system-biased per SYSTEM_BIAS."""
    if n <= 0:
        return np.empty(0, dtype=np.int64)

    rng = np.random.default_rng(base_seed + cohort_id)
    system_pool = system_slices.get(system)
    if system_pool is None or len(system_pool) == 0:
        return rng.choice(POPULATION, size=min(n, POPULATION), replace=False).astype(np.int64)

    in_system = min(int(round(n * SYSTEM_BIAS)), len(system_pool))
    out_system = n - in_system

    in_ids = rng.choice(system_pool, size=in_system, replace=False) if in_system else np.empty(0, dtype=np.int64)

    if out_system <= 0:
        return in_ids

    # Sample from the global pool, then filter accidental conflicts with in_ids.
    out_ids = rng.choice(POPULATION, size=out_system, replace=False)
    out_ids = np.setdiff1d(out_ids, in_ids, assume_unique=False)
    # Top up if conflicts removed too many.
    while len(out_ids) < out_system and len(in_ids) + len(out_ids) < POPULATION:
        deficit = out_system - len(out_ids)
        extra = rng.choice(POPULATION, size=deficit, replace=False)
        out_ids = np.unique(np.concatenate([out_ids, np.setdiff1d(extra, in_ids)]))

    return np.concatenate([in_ids, out_ids[:out_system]])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo-counts", type=Path, default=DEFAULT_DEMO_JSON)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--m", type=int, default=50_000, help="Registers per sketch.")
    parser.add_argument("--a", type=float, default=10.0, help="Decay parameter.")
    parser.add_argument("--salt", type=str, default="ll", help="Hash salt (public).")
    parser.add_argument("--epsilon", type=float, default=2.0, help="Per-sketch ε.")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed.")
    args = parser.parse_args()

    if not args.demo_counts.exists():
        raise SystemExit(
            f"Missing {args.demo_counts}. Run\n"
            f"  uv run python scripts/generate_demo_phenotype_counts.py\n"
            f"first."
        )

    demo_records: list[dict] = json.loads(args.demo_counts.read_text(encoding="utf-8"))
    print(f"Loaded {len(demo_records)} demo records from {args.demo_counts}")

    systems = sorted({r.get("system", "Other") for r in demo_records})
    system_slices = build_system_slices(systems)
    print(f"Partitioned synthetic population of {POPULATION:,} across {len(systems)} systems")

    rng_dp = np.random.default_rng(args.seed)
    p_flip = 1.0 / (1.0 + np.exp(args.epsilon))

    cohort_ids: list[int] = []
    bits_rows: list[np.ndarray] = []
    cardinalities: list[int] = []
    for rec in tqdm(demo_records, desc="synthetic sketches"):
        cid = int(rec["cohort_id"])
        n_target = int(rec.get("dp_count", 0))
        if n_target <= 0:
            continue
        system = rec.get("system", "Other")
        persons = sample_person_set(cid, n_target, system, system_slices, args.seed)
        s = LiquidLegions(m=args.m, a=args.a, salt=args.salt)
        s.add_many(persons.tolist())
        s.apply_dp(epsilon=args.epsilon, rng=rng_dp)
        n_hat = golden_legion_cardinality(s.bits, args.m, args.a, p_flip)
        cohort_ids.append(cid)
        bits_rows.append(s.bits)
        cardinalities.append(int(round(n_hat)))

    if not cohort_ids:
        raise SystemExit("No cohorts with dp_count > 0 in the demo JSON.")

    bits_matrix = np.stack(bits_rows).astype(np.int8)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    bin_path = args.out_dir / "ll_sketches_demo.bin"
    bin_path.write_bytes(bit_pack(bits_matrix))

    meta = {
        "m": args.m,
        "a": args.a,
        "salt": args.salt,
        "epsilon": args.epsilon,
        "p_flip": p_flip,
        "cohort_ids": cohort_ids,
        "cardinalities": cardinalities,
        "bytes_per_row": (args.m + 7) // 8,
    }
    json_path = args.out_dir / "ll_sketches_demo.json"
    json_path.write_text(json.dumps(meta))

    # Sync the demo counts file to the Golden Legion estimates so the table and
    # the overlap-panel cardinalities show the same number for each cohort.
    by_id = dict(zip(cohort_ids, cardinalities))
    updated = 0
    new_records = []
    for rec in demo_records:
        cid = int(rec["cohort_id"])
        if cid in by_id:
            rec["dp_count"] = by_id[cid]
            new_records.append(rec)
            updated += 1
    args.demo_counts.write_text(json.dumps(new_records, indent=2), encoding="utf-8")

    print(f"Wrote {bin_path} ({bin_path.stat().st_size / 1e6:.2f} MB)")
    print(f"Wrote {json_path} ({json_path.stat().st_size / 1e3:.1f} KB)")
    print(
        f"Updated dp_count in {args.demo_counts} for {updated} cohorts "
        f"(dropped {len(demo_records) - updated} with no sketch)"
    )


if __name__ == "__main__":
    main()

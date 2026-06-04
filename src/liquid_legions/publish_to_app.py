"""Publish DP Liquid Legions sketches to the Svelte app's public folder.

Reads the .npz produced by build_sketches.py, computes Golden Legion cardinality
per cohort, and writes:

  app/public/ll_sketches.bin        bit-packed bits matrix (K * m / 8 bytes)
  app/public/ll_sketches.json       metadata + cohort_ids + cardinalities
  app/public/phenotype_counts_dp.json   existing file, dp_count replaced with LL estimate

Example:
    uv run python -m src.liquid_legions.publish_to_app \\
        --sketches outputs/ll_sketches.npz
"""

from __future__ import annotations

import json
from argparse import ArgumentParser
from pathlib import Path

import numpy as np
from scipy.optimize import brentq, minimize_scalar
from scipy.special import gammaln
from tqdm import tqdm

from .build_sketches import load_sketches


def _p_k_segment(x0: int, m_seg: int, m: int, a: float) -> np.ndarray:
    k = np.arange(x0, x0 + m_seg)
    norm = 1.0 - np.exp(-a)
    return (np.exp(-a * k / m) - np.exp(-a * (k + 1) / m)) / norm


def find_golden_legion(bits: np.ndarray, m: int, a: float, p_flip: float) -> tuple[int, int]:
    m_seg = max(1, int(min(m, m * np.log(10.0) / a)))
    if m_seg >= m:
        return 0, m
    step = max(1, m_seg // 50)
    denom = (1.0 - 2.0 * p_flip) * m_seg
    best_x0, best_diff = 0, np.inf
    for x0 in range(0, m - m_seg + 1, step):
        observed_ones = int(bits[x0:x0 + m_seg].sum())
        denoised_frac = (observed_ones - p_flip * m_seg) / denom if denom != 0 else 0.0
        if denoised_frac < 0.6:
            return x0, m_seg
        d = abs(denoised_frac - 0.5)
        if d < best_diff:
            best_diff, best_x0 = d, x0
    return best_x0, m_seg


def _invert_fill(est_true_ones: float, x0: int, m_seg: int, m: int, a: float) -> float:
    """Invert the Liquid Legions fill curve F(n) on a register segment.

    Given the (de-noised) number of truly-active registers in the segment, solve
    `sum_k (1 - (1-p_k)^n) = est_true_ones` for the cardinality n (Eq. 1 / Alg. 4).
    """
    est_true_ones = float(np.clip(est_true_ones, 0.0, m_seg))
    if est_true_ones <= 0:
        return 0.0
    p_k_seg = _p_k_segment(x0, m_seg, m, a)

    def gap(n: float) -> float:
        return float(np.sum(1.0 - np.power(1.0 - p_k_seg, n))) - est_true_ones

    upper = 5_000_000.0
    if gap(upper) < 0:
        return upper
    try:
        return float(brentq(gap, 1e-3, upper))
    except ValueError:
        return 0.0


def _cardinality_from_segment(
    observed_ones: float, x0: int, m_seg: int, m: int, a: float, noise_offset: float, p_flip: float,
) -> float:
    """Scalar (single-sketch) RR de-noising followed by fill-curve inversion."""
    denom = 1.0 - 2.0 * p_flip
    est_true_ones = (observed_ones - noise_offset * m_seg) / denom if abs(denom) > 1e-12 else observed_ones
    return _invert_fill(est_true_ones, x0, m_seg, m, a)


def golden_legion_cardinality(bits: np.ndarray, m: int, a: float, p_flip: float) -> float:
    x0, m_seg = find_golden_legion(bits, m, a, p_flip)
    observed_ones = float(bits[x0:x0 + m_seg].sum())
    return _cardinality_from_segment(observed_ones, x0, m_seg, m, a, p_flip, p_flip)


# def golden_legion_or_cardinality(bits_or: np.ndarray, m: int, a: float, p_flip: float) -> float:
#     """Approximate |A ∪ B| from the bitwise OR of two independently RR-flipped sketches.

#     Per-bit OR-active probability is `1 - p²` for true 1s and `2p - p²` for true 0s,
#     so the linear inversion offset is `2p - p²` instead of `p`. Same `1 - 2p` denominator.

#     NOTE: this collapses the OR to a single bit-vector and so cannot tell apart registers
#     where *both* sketches are active (`1 - p²`) from those where only *one* is (`1 - p + p²`).
#     It therefore biases the union low and the intersection high. Kept only as a diagnostic
#     baseline; use `golden_legion_union_cardinality` for the faithful (Algorithm 5) estimate.
#     """
#     x0, m_seg = find_golden_legion(bits_or, m, a, p_flip)
#     observed_ones = float(bits_or[x0:x0 + m_seg].sum())
#     or_offset = 2.0 * p_flip - p_flip ** 2
#     return _cardinality_from_segment(observed_ones, x0, m_seg, m, a, or_offset, p_flip)


def _binom_pmf(n: int, prob: float) -> np.ndarray:
    """PMF of Binomial(n, prob) over k = 0..n as a length-(n+1) array."""
    k = np.arange(n + 1)
    log_coef = gammaln(n + 1) - gammaln(k + 1) - gammaln(n - k + 1)
    with np.errstate(divide="ignore"):
        return np.exp(log_coef + k * np.log(prob) + (n - k) * np.log1p(-prob))


def flip_transition_matrix(K: int, p: float) -> np.ndarray:
    """CorrectionMatrix input N (Algorithm 5): N[b, a] = P(observe b ones | a true ones).

    At a register, `a` of the K sketches are truly active and K-a are not. After flipping
    each bit with prob p, a true-one survives as 1 w.p. (1-p) and a true-zero flips to 1
    w.p. p, so observed ones = Binom(a, 1-p) + Binom(K-a, p) (a convolution of the two).
    """
    M = np.zeros((K + 1, K + 1))
    for a in range(K + 1):
        survivors = _binom_pmf(a, 1.0 - p)        # true ones that stay 1
        false_pos = _binom_pmf(K - a, p)          # true zeros that flip to 1
        M[:, a] = np.convolve(survivors, false_pos)
    return M


def golden_legion_union_cardinality(
    bits_list: list[np.ndarray], m: int, a: float, p_flip: float,
) -> float:
    """|∪ S| over K independently RR-flipped sketches, faithful to Algorithm 5 of the
    Liquid Legions paper (Wright et al. 2020).

    On the Golden Legion segment, build the OneCountsVolumesVector `v[c]` = number of
    registers where exactly c of the K sketches show a 1, then de-noise by inverting the
    flip transition matrix N. The first coordinate of `N^{-1} v` is the de-noised count of
    registers where *no* sketch is truly active; `m_seg - that` is the active-register count
    of the union, which is fed through the fill-curve inversion.
    """
    bits_stack = np.stack(bits_list).astype(np.int8)        # (K, m)
    K = bits_stack.shape[0]
    bits_or = np.bitwise_or.reduce(bits_stack, axis=0).astype(np.int8)

    x0, m_seg = find_golden_legion(bits_or, m, a, p_flip)
    ones_per_register = bits_stack[:, x0:x0 + m_seg].sum(axis=0)   # values 0..K
    v = np.bincount(ones_per_register, minlength=K + 1).astype(float)

    N = flip_transition_matrix(K, p_flip)
    try:
        u = np.linalg.solve(N, v)                 # de-noised register-state counts
    except np.linalg.LinAlgError:                 # singular at p == 0.5
        u = np.linalg.lstsq(N, v, rcond=None)[0]

    zero_count = float(np.clip(u[0], 0.0, m_seg))
    est_union_ones = m_seg - zero_count
    return _invert_fill(est_union_ones, x0, m_seg, m, a)


def overlap_via_or(
    bits_a: np.ndarray, bits_b: np.ndarray, n_a: float, n_b: float,
    m: int, a: float, p_flip: float,
) -> float:
    """|A ∩ B| via inclusion–exclusion: n_a + n_b - |A ∪ B|, with the union estimated by
    the faithful Algorithm 5 CorrectionMatrix de-noising over the two sketches."""
    n_union = golden_legion_union_cardinality([bits_a, bits_b], m, a, p_flip)
    return max(0.0, n_a + n_b - n_union)


def bit_pack(bits_matrix: np.ndarray) -> bytes:
    """Pack a (K, m) int8 0/1 matrix into bytes (MSB-first within each byte).

    If m is not a multiple of 8, the last byte of each row is padded with zeros.
    """
    K, m = bits_matrix.shape
    pad = (-m) % 8
    if pad:
        bits_matrix = np.concatenate(
            [bits_matrix, np.zeros((K, pad), dtype=np.int8)], axis=1
        )
    packed = np.packbits(bits_matrix.astype(np.uint8), axis=1, bitorder="big")
    return packed.tobytes()


def main() -> None:
    parser = ArgumentParser(description="Publish LL sketches to app/public/.")
    parser.add_argument("--sketches", type=Path, default=Path("outputs/ll_sketches.npz"))
    parser.add_argument("--counts-json", type=Path,
                        default=Path("app/public/phenotype_counts_dp.json"))
    parser.add_argument("--out-dir", type=Path, default=Path("app/public"))
    args = parser.parse_args()

    if not args.sketches.exists():
        raise SystemExit(f"Sketches not found at {args.sketches} — run build_sketches.py first.")
    if not args.counts_json.exists():
        raise SystemExit(f"Counts JSON not found at {args.counts_json}")

    sketches, meta = load_sketches(args.sketches)
    m = meta["m"]
    a = meta["a"]
    p_flip = meta["p_flip"]
    epsilon = meta["epsilon"]
    print(f"Loaded {len(sketches)} sketches (m={m}, a={a}, ε={epsilon}, p_flip={p_flip:.4f})")

    cohort_ids = list(sketches.keys())
    bits_matrix = np.stack([sketches[c].bits for c in cohort_ids]).astype(np.int8)

    cardinalities: list[int] = []
    for c in tqdm(cohort_ids, desc="Golden Legion cardinalities"):
        n_hat = golden_legion_cardinality(sketches[c].bits, m, a, p_flip)
        cardinalities.append(int(round(n_hat)))

    # 1. Bit-packed sketches bundle
    args.out_dir.mkdir(parents=True, exist_ok=True)
    bin_path = args.out_dir / "ll_sketches.bin"
    bin_path.write_bytes(bit_pack(bits_matrix))

    meta_out = {
        "m": m,
        "a": a,
        "salt": meta["salt"],
        "epsilon": epsilon,
        "p_flip": p_flip,
        "cohort_ids": cohort_ids,
        "cardinalities": cardinalities,
        "bytes_per_row": (m + 7) // 8,
    }
    json_path = args.out_dir / "ll_sketches.json"
    json_path.write_text(json.dumps(meta_out))

    print(f"Wrote {bin_path} ({bin_path.stat().st_size / 1e6:.2f} MB)")
    print(f"Wrote {json_path} ({json_path.stat().st_size / 1e3:.1f} KB)")

    # 2. Overwrite dp_count in phenotype_counts_dp.json with LL cardinality
    counts = json.loads(args.counts_json.read_text())
    ll_by_id = dict(zip(cohort_ids, cardinalities))
    updated = 0
    dropped = 0
    new_counts = []
    for row in counts:
        cid = row.get("cohort_id")
        if cid in ll_by_id:
            row["dp_count"] = ll_by_id[cid]
            new_counts.append(row)
            updated += 1
        else:
            dropped += 1
    args.counts_json.write_text(json.dumps(new_counts))
    print(f"Updated dp_count for {updated} cohorts in {args.counts_json} "
          f"({dropped} cohorts had no sketch and were dropped)")


if __name__ == "__main__":
    main()

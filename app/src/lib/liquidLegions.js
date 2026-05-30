// Liquid Legions browser-side estimator.
// Ports the Golden Legion + correct-OR likelihood path from the notebook
// (cells 86312551 and 7c94dad9) to plain JS / typed arrays.
//
// Load once via loadSketches(); then call overlapPair(bundle, idA, idB).

const PHI = (Math.sqrt(5) - 1) / 2; // golden-section ratio

/** Build the full p_k array of length m for a truncated-exponential LL hash. */
function buildPk(m, a) {
  const pk = new Float64Array(m);
  const norm = 1.0 - Math.exp(-a);
  for (let k = 0; k < m; k++) {
    pk[k] = (Math.exp((-a * k) / m) - Math.exp((-a * (k + 1)) / m)) / norm;
  }
  return pk;
}

/** log(1 - p_k), cached for the MLE inner loops. */
function buildLog1mPk(pk) {
  const out = new Float64Array(pk.length);
  for (let i = 0; i < pk.length; i++) out[i] = Math.log(1.0 - pk[i]);
  return out;
}

/** Unpack one cohort's bits (MSB-first) into a Uint8Array of length m. */
function unpackRow(packed, rowOffset, bytesPerRow, m) {
  const out = new Uint8Array(m);
  let bitIdx = 0;
  for (let byteIdx = 0; byteIdx < bytesPerRow && bitIdx < m; byteIdx++) {
    const b = packed[rowOffset + byteIdx];
    for (let bit = 7; bit >= 0 && bitIdx < m; bit--) {
      out[bitIdx++] = (b >> bit) & 1;
    }
  }
  return out;
}

/**
 * Fetch ll_sketches.json + ll_sketches.bin and return a bundle:
 *   { m, a, salt, epsilon, pFlip, cohortIds, cardinalities, bits: Uint8Array[K][m],
 *     pk, log1mPk, byId: Map<cohortId, rowIndex> }
 */
export async function loadSketches(baseUrl = import.meta.env.BASE_URL ?? "/") {
  const jsonFile = import.meta.env.VITE_LL_SKETCHES_JSON ?? "ll_sketches.json";
  const binFile  = import.meta.env.VITE_LL_SKETCHES_BIN  ?? "ll_sketches.bin";

  const metaRes = await fetch(`${baseUrl}${jsonFile}`);
  if (!metaRes.ok) throw new Error(`${jsonFile}: ${metaRes.status}`);
  const meta = await metaRes.json();

  const binRes = await fetch(`${baseUrl}${binFile}`);
  if (!binRes.ok) throw new Error(`${binFile}: ${binRes.status}`);
  const packed = new Uint8Array(await binRes.arrayBuffer());

  const { m, a, salt, epsilon, p_flip: pFlip, cohort_ids: cohortIds,
          cardinalities, bytes_per_row: bytesPerRow } = meta;

  const K = cohortIds.length;
  if (packed.length < K * bytesPerRow) {
    throw new Error(`ll_sketches.bin truncated: ${packed.length} < ${K * bytesPerRow}`);
  }

  // Unpack rows up front. ~K*m bytes (700 * 50_000 ≈ 35MB) — fine on desktop.
  const bits = new Array(K);
  for (let i = 0; i < K; i++) {
    bits[i] = unpackRow(packed, i * bytesPerRow, bytesPerRow, m);
  }

  const pk = buildPk(m, a);
  const log1mPk = buildLog1mPk(pk);

  const byId = new Map();
  for (let i = 0; i < K; i++) byId.set(cohortIds[i], i);

  return { m, a, salt, epsilon, pFlip, cohortIds, cardinalities, bits, pk, log1mPk, byId };
}

/** Golden-section search on a unimodal f over [lo, hi]. */
function goldenSectionMinimize(f, lo, hi, xatol = 1e-3, maxIter = 100) {
  let a = lo, b = hi;
  let c = b - PHI * (b - a);
  let d = a + PHI * (b - a);
  let fc = f(c), fd = f(d);
  let iter = 0;
  while (b - a > xatol && iter++ < maxIter) {
    if (fc < fd) {
      b = d;
      d = c; fd = fc;
      c = b - PHI * (b - a);
      fc = f(c);
    } else {
      a = c;
      c = d; fc = fd;
      d = a + PHI * (b - a);
      fd = f(d);
    }
  }
  return (a + b) / 2;
}

/** Find the contiguous Golden Legion window over bits. Returns [x0, mSeg]. */
function findGoldenLegion(bits, m, a, pFlip) {
  const mSeg = Math.max(1, Math.min(m, Math.floor((m * Math.log(10)) / a)));
  if (mSeg >= m) return [0, m];
  const step = Math.max(1, Math.floor(mSeg / 50));
  const denom = (1.0 - 2.0 * pFlip) * mSeg;
  let bestX0 = 0;
  let bestDiff = Infinity;
  // Rolling window sum for speed.
  let ones = 0;
  for (let i = 0; i < mSeg; i++) ones += bits[i];
  for (let x0 = 0; x0 <= m - mSeg; x0 += step) {
    const denoisedFrac = denom !== 0 ? (ones - pFlip * mSeg) / denom : 0.0;
    if (denoisedFrac < 0.6) return [x0, mSeg];
    const d = Math.abs(denoisedFrac - 0.5);
    if (d < bestDiff) { bestDiff = d; bestX0 = x0; }
    // Slide window forward by `step`.
    const nextX0 = x0 + step;
    if (nextX0 > m - mSeg) break;
    for (let j = x0; j < nextX0; j++) ones -= bits[j];
    for (let j = x0 + mSeg; j < nextX0 + mSeg; j++) ones += bits[j];
  }
  return [bestX0, mSeg];
}

/** XOR-aware OR of two bit rows into a fresh Uint8Array. */
function bitwiseOr(a, b) {
  const m = a.length;
  const out = new Uint8Array(m);
  for (let i = 0; i < m; i++) out[i] = a[i] | b[i];
  return out;
}

/**
 * Estimate |A ∩ B| from two DP-flipped LL sketches using the paper-correct
 * union likelihood on the Golden Legion segment. Returns { overlap, nA, nB, nUnion }.
 */
export function overlapPair(bundle, idA, idB) {
  const { m, a, pFlip, bits, pk, log1mPk, cardinalities, byId } = bundle;
  const iA = byId.get(idA);
  const iB = byId.get(idB);
  if (iA == null || iB == null) {
    throw new Error(`unknown cohort id: ${iA == null ? idA : idB}`);
  }
  const nA = cardinalities[iA];
  const nB = cardinalities[iB];
  const bitsOr = bitwiseOr(bits[iA], bits[iB]);

  const [x0, mSeg] = findGoldenLegion(bitsOr, m, a, pFlip);

  // Slice segments.
  const pkSeg = pk.subarray(x0, x0 + mSeg);
  const log1mPkSeg = log1mPk.subarray(x0, x0 + mSeg);
  const bitsSeg = bitsOr.subarray(x0, x0 + mSeg);

  // Precompute parts that don't depend on n_union.
  const c2 = (1.0 - 2.0 * pFlip) ** 2;
  const c1 = pFlip * (1.0 - 2.0 * pFlip);
  const c0 = pFlip * pFlip;
  const qab = new Float64Array(mSeg);
  for (let i = 0; i < mSeg; i++) {
    const qa = Math.exp(nA * log1mPkSeg[i]);
    const qb = Math.exp(nB * log1mPkSeg[i]);
    qab[i] = c1 * (qa + qb) + c0;
  }

  const EPS = 1e-12;
  function negLogLik(nUnion) {
    let ll = 0;
    for (let i = 0; i < mSeg; i++) {
      const qu = Math.exp(nUnion * log1mPkSeg[i]);
      const pOrZero = c2 * qu + qab[i];
      let pOrOne = 1.0 - pOrZero;
      if (pOrOne < EPS) pOrOne = EPS;
      else if (pOrOne > 1.0 - EPS) pOrOne = 1.0 - EPS;
      ll += bitsSeg[i] ? Math.log(pOrOne) : Math.log(1.0 - pOrOne);
    }
    return -ll;
  }

  const lo = Math.max(nA, nB, 1.0);
  const hi = Math.max(nA + nB, lo + 1.0);
  const nUnion = goldenSectionMinimize(negLogLik, lo, hi, 1e-2);
  const overlap = Math.max(0, nA + nB - nUnion);

  // pk parameter is unused beyond the segment slice; expose pk to silence "unused" warnings.
  void pkSeg;

  return { overlap, nA, nB, nUnion };
}

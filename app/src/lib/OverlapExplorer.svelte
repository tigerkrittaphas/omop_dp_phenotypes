<script>
  import { overlapPair } from './liquidLegions.js'

  let {
    bundle = null,
    phenotypes = [],
    selectedA = $bindable(null),
    selectedB = $bindable(null),
  } = $props()

  let queryA = $state('')
  let queryB = $state('')
  let showListA = $state(false)
  let showListB = $state(false)

  /** @type {{overlap: number, nA: number, nB: number, nUnion: number, sameCohort?: boolean} | null} */
  let result = $state(null)
  let computeMs = $state(0)
  let computeError = $state('')

  const byId = $derived(new Map(phenotypes.map(p => [p.cohort_id, p])))

  // Mirror external selection changes (e.g. from the graph) into the input text.
  $effect(() => {
    if (selectedA == null) { queryA = ''; return }
    const p = byId.get(selectedA)
    if (p && p.phenotype_name !== queryA) queryA = p.phenotype_name
  })
  $effect(() => {
    if (selectedB == null) { queryB = ''; return }
    const p = byId.get(selectedB)
    if (p && p.phenotype_name !== queryB) queryB = p.phenotype_name
  })

  function matches(p, q) {
    if (q.trim() === '') return true
    return p.phenotype_name.toLowerCase().includes(q.trim().toLowerCase())
  }
  const optionsA = $derived(phenotypes.filter(p => matches(p, queryA)).slice(0, 50))
  const optionsB = $derived(phenotypes.filter(p => matches(p, queryB)).slice(0, 50))

  function pick(which, p) {
    if (which === 'A') { selectedA = p.cohort_id; queryA = p.phenotype_name; showListA = false }
    else                { selectedB = p.cohort_id; queryB = p.phenotype_name; showListB = false }
  }

  function onTypeA() {
    // Treat typing as "intent to change A" — clear the bound selection until user picks.
    if (selectedA != null) selectedA = null
  }
  function onTypeB() {
    if (selectedB != null) selectedB = null
  }

  // Recompute overlap whenever both selections are present and the bundle is ready.
  $effect(() => {
    computeError = ''
    if (selectedA == null || selectedB == null || !bundle) {
      result = null
      return
    }
    if (selectedA === selectedB) {
      const c = bundle.cardinalities[bundle.byId.get(selectedA)]
      result = { overlap: c, nA: c, nB: c, nUnion: c, sameCohort: true }
      computeMs = 0
      return
    }
    try {
      const t0 = performance.now()
      const r = overlapPair(bundle, selectedA, selectedB)
      computeMs = performance.now() - t0
      result = r
    } catch (e) {
      computeError = e?.message ?? String(e)
      result = null
    }
  })

  const jaccard = $derived(
    result == null
      ? null
      : result.nA + result.nB - result.overlap > 0
        ? result.overlap / (result.nA + result.nB - result.overlap)
        : 0
  )
</script>

<section class="panel">
  <header class="header">
    <h2>Cohort overlap</h2>
    <p class="sub">
      Pick cohorts from the dropdowns or by clicking nodes in the graph.
      Estimate is post-processing of ε-DP sketches — no extra budget per query.
      {#if bundle}ε per sketch = <strong>{bundle.epsilon}</strong>{/if}
    </p>
  </header>

  <div class="picker-row">
    <div class="picker">
      <label for="cohort-a-input"><span class="dot dot-a"></span> Cohort A</label>
      <input id="cohort-a-input" type="text" bind:value={queryA}
             oninput={onTypeA}
             onfocus={() => showListA = true}
             onblur={() => setTimeout(() => showListA = false, 120)}
             placeholder="Search by name…" autocomplete="off" />
      {#if showListA && optionsA.length > 0}
        <ul class="suggest">
          {#each optionsA as p (p.cohort_id)}
            <li>
              <button type="button" class="suggest-row" onmousedown={() => pick('A', p)}>
                <span class="suggest-name">{p.phenotype_name}</span>
                <span class="suggest-id">#{p.cohort_id}</span>
              </button>
            </li>
          {/each}
        </ul>
      {/if}
    </div>

    <div class="picker">
      <label for="cohort-b-input"><span class="dot dot-b"></span> Cohort B</label>
      <input id="cohort-b-input" type="text" bind:value={queryB}
             oninput={onTypeB}
             onfocus={() => showListB = true}
             onblur={() => setTimeout(() => showListB = false, 120)}
             placeholder="Search by name…" autocomplete="off" />
      {#if showListB && optionsB.length > 0}
        <ul class="suggest">
          {#each optionsB as p (p.cohort_id)}
            <li>
              <button type="button" class="suggest-row" onmousedown={() => pick('B', p)}>
                <span class="suggest-name">{p.phenotype_name}</span>
                <span class="suggest-id">#{p.cohort_id}</span>
              </button>
            </li>
          {/each}
        </ul>
      {/if}
    </div>
  </div>

  {#if computeError}
    <p class="status error">{computeError}</p>
  {:else if result}
    <div class="result-grid">
      <div class="metric primary">
        <span class="metric-label">Intersection of Cohort A and B</span>
        <span class="metric-value">{Math.round(result.overlap).toLocaleString()}</span>
      </div>
      <div class="metric">
        <span class="metric-label">Cohort A size</span>
        <span class="metric-value">{Math.round(result.nA).toLocaleString()}</span>
      </div>
      <div class="metric">
        <span class="metric-label">Cohort B size</span>
        <span class="metric-value">{Math.round(result.nB).toLocaleString()}</span>
      </div>
      <div class="metric">
        <span class="metric-label">Union of Cohort A and B</span>
        <span class="metric-value">{Math.round(result.nUnion).toLocaleString()}</span>
      </div>
      <div class="metric">
        <span class="metric-label">Jaccard Similarity Index</span>
        <span class="metric-value">{jaccard != null ? jaccard.toFixed(3) : '—'}</span>
      </div>
    </div>
    <p class="footnote">
      {#if result.sameCohort}
        Same cohort — overlap equals its DP cardinality.
      {:else}
        Computed in <strong>{computeMs.toFixed(1)} ms</strong> on this device.
      {/if}
    </p>
  {:else}
    <p class="status">Pick a cohort for A and B to see their estimated overlap.</p>
  {/if}
</section>

<style>
  .panel {
    padding: 1.25rem 1.5rem;
    background: var(--surface-panel);
    border: 1px solid var(--border-strong);
    border-radius: 10px;
    box-shadow: var(--shadow-sm);
  }
  .header { margin-bottom: 1rem; }
  .header h2 { margin: 0 0 0.25rem; font-size: 1rem; color: var(--text-primary); }
  .sub { margin: 0; font-size: 0.78rem; color: var(--text-secondary); }

  .picker-row {
    display: grid;
    grid-template-columns: 1fr;
    gap: 0.75rem;
    margin-bottom: 1rem;
  }
  .picker { position: relative; display: flex; flex-direction: column; gap: 0.3rem; }
  .picker label {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-secondary);
  }
  .dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .dot-a { background: #22c55e; }
  .dot-b { background: #f59e0b; }
  .picker input {
    padding: 0.4rem 0.6rem;
    font-size: 0.8rem;
    border: 1px solid var(--border-strong);
    border-radius: 6px;
    background: var(--surface-panel);
    color: var(--text-primary);
    outline: none;
    transition: border-color 0.15s;
  }
  .picker input:focus { border-color: var(--accent); }

  .suggest {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    margin: 0.2rem 0 0;
    padding: 0;
    list-style: none;
    background: var(--surface-panel);
    border: 1px solid var(--border-strong);
    border-radius: 6px;
    max-height: 240px;
    overflow-y: auto;
    z-index: 5;
    box-shadow: var(--shadow-md);
  }
  .suggest-row {
    display: flex;
    width: 100%;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    padding: 0.35rem 0.6rem;
    background: transparent;
    border: 0;
    text-align: left;
    color: var(--text-primary);
    cursor: pointer;
    font-size: 0.75rem;
  }
  .suggest-row:hover { background: var(--surface-hover); }
  .suggest-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .suggest-id { font-family: var(--mono); color: var(--text-muted); font-size: 0.7rem; }

  .result-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 0.5rem;
    margin-bottom: 0.6rem;
  }
  .metric {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    padding: 0.55rem 0.7rem;
    background: var(--surface-sunken);
    border-radius: 6px;
  }
  .metric.primary {
    grid-column: 1 / -1;
    background: var(--accent-active-bg);
    color: var(--accent-active-fg);
  }
  .metric-label {
    font-size: 0.66rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
  }
  .metric.primary .metric-label { color: inherit; opacity: 0.85; }
  .metric-value { font-family: var(--mono); font-size: 0.95rem; font-weight: 600; }

  .footnote { margin: 0; font-size: 0.72rem; color: var(--text-muted); }
  .status { color: var(--text-secondary); font-size: 0.8rem; }
  .status.error { color: var(--status-error); }
</style>

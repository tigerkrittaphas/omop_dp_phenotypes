<script>
  import { onMount } from 'svelte'
  import { loadSketches } from './liquidLegions.js'
  import DualGraphPicker from './DualGraphPicker.svelte'
  import OverlapExplorer from './OverlapExplorer.svelte'

  let bundle = $state(null)
  let phenotypes = $state([])
  let loadStatus = $state('idle') // 'idle' | 'loading' | 'ready' | 'error'
  let loadError = $state('')

  /** @type {number | null} */
  let selectedA = $state(null)
  /** @type {number | null} */
  let selectedB = $state(null)

  onMount(async () => {
    loadStatus = 'loading'
    try {
      const countsFile = import.meta.env.VITE_PHENOTYPE_COUNTS_FILE
      const [sketches, countsRes] = await Promise.all([
        loadSketches(),
        fetch(`${import.meta.env.BASE_URL}${countsFile}`),
      ])
      if (!countsRes.ok) throw new Error(`counts JSON: ${countsRes.status}`)
      const all = await countsRes.json()
      bundle = sketches
      phenotypes = all
        .filter(p => sketches.byId.has(p.cohort_id))
        .sort((a, b) => a.phenotype_name.localeCompare(b.phenotype_name))
      loadStatus = 'ready'
    } catch (e) {
      loadError = e?.message ?? String(e)
      loadStatus = 'error'
    }
  })
</script>

{#if loadStatus === 'loading'}
  <p class="status">Loading sketches…</p>
{:else if loadStatus === 'error'}
  <p class="status error">Failed to load sketches: {loadError}</p>
{:else if loadStatus === 'ready'}
  <div class="overlap-layout">
    <div class="graph-col">
      <DualGraphPicker {phenotypes} bind:selectedA bind:selectedB />
    </div>
    <div class="explorer-col">
      <OverlapExplorer {bundle} {phenotypes} bind:selectedA bind:selectedB />
    </div>
  </div>
{/if}

<style>
  .overlap-layout {
    display: grid;
    grid-template-columns: minmax(0, 1.5fr) minmax(360px, 1fr);
    gap: 0.75rem;
    align-items: start;
  }
  .graph-col { min-width: 0; }
  .explorer-col { min-width: 0; }

  .status {
    color: var(--text-secondary);
    padding: 2rem;
    text-align: center;
    font-size: 0.85rem;
  }
  .status.error { color: var(--status-error); }

  @media (max-width: 900px) {
    .overlap-layout { grid-template-columns: 1fr; }
  }
</style>

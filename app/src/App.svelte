<script>
  import { onMount } from 'svelte'
  import NetworkGraph from "./lib/NetworkGraph.svelte";
  import OverlapTab from "./lib/OverlapTab.svelte";

  let theme = $state('light')
  /** @type {'network' | 'overlap'} */
  let activeTab = $state('network')
  let overlapMounted = $state(false)

  // Lazy-mount the overlap tab on first visit, then keep it in the DOM
  // (toggled via display:none) so its sketch bundle isn't re-fetched.
  $effect(() => { if (activeTab === 'overlap') overlapMounted = true })

  onMount(() => {
    const saved = localStorage.getItem('theme')
    if (saved === 'dark' || saved === 'light') theme = saved
    document.documentElement.setAttribute('data-theme', theme)
  })

  $effect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    if (typeof localStorage !== 'undefined') localStorage.setItem('theme', theme)
  })

  function toggle() {
    theme = theme === 'light' ? 'dark' : 'light'
  }
</script>

<header class="topbar">
  <h1>OMOP Phenotype Library</h1>
  <button class="theme-toggle" onclick={toggle} aria-label="Toggle theme" title="Toggle theme">
    {#if theme === 'light'}
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
      </svg>
      <span>Dark</span>
    {:else}
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
      </svg>
      <span>Light</span>
    {/if}
  </button>
</header>

<nav class="tabs" role="tablist">
  <button role="tab" aria-selected={activeTab === 'network'}
          class:active={activeTab === 'network'}
          onclick={() => activeTab = 'network'}>
    Cohort Count and Definition
  </button>
  <button role="tab" aria-selected={activeTab === 'overlap'}
          class:active={activeTab === 'overlap'}
          onclick={() => activeTab = 'overlap'}>
    Cohort Intersection
  </button>
</nav>

<div class="tab-pane" class:hidden={activeTab !== 'network'}>
  <NetworkGraph />
</div>

{#if overlapMounted}
  <div class="tab-pane" class:hidden={activeTab !== 'overlap'}>
    <OverlapTab />
  </div>
{/if}

<footer class="page-footer">
  <p class="description">
    A visualization of <strong>856 clinical phenotypes</strong> from the OHDSI Phenotype Library.
    Nodes represent patient cohorts; edges connect phenotypes that share OMOP concept IDs.
    Patient counts and pairwise overlaps are protected with <strong>differential privacy</strong>
    using <strong>Liquid Legions</strong> sketches — once a sketch is published at ε-DP,
    any cardinality or overlap is post-processing and costs no additional privacy budget.
  </p>
  <p class="sources">
    Phenotype definitions:
    <a href="https://phenotypelibrary.ohdsi.org" target="_blank" rel="noopener">OHDSI Phenotype Library</a>
    · Sketch:
    <a href="https://research.google/pubs/pub49177/" target="_blank" rel="noopener">Wright et al., Liquid Legions</a>
  </p>
</footer>

<style>
  .topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
  }

  .theme-toggle {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.45rem 0.8rem;
    border: 1px solid var(--border-strong);
    background: var(--surface-panel);
    color: var(--text-primary);
    border-radius: 8px;
    font-size: 0.8rem;
    font-weight: 500;
    cursor: pointer;
    transition: background-color 0.15s, border-color 0.15s, color 0.15s;
  }

  .theme-toggle:hover {
    background: var(--surface-hover);
    color: var(--text-strong);
    border-color: var(--accent);
  }

  .theme-toggle svg { display: block; }

  .tabs {
    display: flex;
    gap: 0.25rem;
    margin: 0.75rem 0 0.85rem;
    border-bottom: 1px solid var(--border-strong);
  }
  .tabs button {
    padding: 0.5rem 1rem;
    border: 0;
    background: transparent;
    color: var(--text-secondary);
    font-size: 0.85rem;
    font-weight: 500;
    cursor: pointer;
    border-bottom: 2px solid transparent;
    transition: color 0.12s, border-color 0.12s;
  }
  .tabs button:hover { color: var(--text-primary); }
  .tabs button.active {
    color: var(--accent);
    border-bottom-color: var(--accent);
  }

  .tab-pane.hidden { display: none; }

  .page-footer {
    margin-top: 2rem;
    padding: 1.25rem 1.5rem;
    border-top: 1px solid var(--border-strong);
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }

  .page-footer p {
    margin: 0;
    font-size: 0.78rem;
    color: var(--text-secondary);
    line-height: 1.6;
  }

  .description strong { color: var(--text-primary); font-weight: 600; }

  .sources { color: var(--text-muted); }

  .page-footer a {
    color: var(--accent);
    text-decoration: none;
  }

  .page-footer a:hover { text-decoration: underline; }
</style>

<script>
  import { onMount } from 'svelte'
  import NetworkGraph from "./lib/NetworkGraph.svelte";

  let theme = $state('light')

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

<NetworkGraph />

<footer class="page-footer">
  <p class="description">
    A visualization of <strong>856 clinical phenotypes</strong> from the OHDSI Phenotype Library.
    Nodes represent patient cohorts; edges connect phenotypes that share OMOP concept IDs.
    Patient counts are protected with <strong>differential privacy</strong>
    applied to counts derived from the OMOP CDM Database.
  </p>
  <p class="sources">
    Phenotype definitions:
    <a href="https://phenotypelibrary.ohdsi.org" target="_blank" rel="noopener">OHDSI Phenotype Library</a>
    · Privacy: <a href="https://opendp.org" target="_blank" rel="noopener">OpenDP</a>
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

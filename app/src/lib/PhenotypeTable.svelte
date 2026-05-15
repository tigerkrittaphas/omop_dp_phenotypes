<script>
  let { data, hoveredId = $bindable(null), sortBy = $bindable('count'), height = 900 } = $props()

  let containerEl = $state()

  const sortedData = $derived(
    [...data].sort((a, b) => {
      if (sortBy === 'count')  return b.count - a.count
      if (sortBy === 'id')     return a.id - b.id
      if (sortBy === 'system') return a.system.localeCompare(b.system) || b.count - a.count
      return 0
    })
  )

  $effect(() => {
    if (hoveredId == null || !containerEl) return
    const rowEl = containerEl.querySelector(`#row-${hoveredId}`)
    if (!rowEl) return
    const top = rowEl.offsetTop
    const bottom = top + rowEl.offsetHeight
    const cTop = containerEl.scrollTop
    const cBottom = cTop + containerEl.clientHeight
    if (top < cTop || bottom > cBottom) {
      containerEl.scrollTo({ top: top - containerEl.clientHeight / 2, behavior: 'smooth' })
    }
  })
</script>

<div class="panel" style="height:{height}px">
  <div class="toolbar">
    <span class="sort-label">Sort by</span>
    {#each [['count', 'Count'], ['id', 'Cohort ID'], ['system', 'Classification']] as [key, label]}
      <button class="sort-btn" class:active={sortBy === key} onclick={() => sortBy = key}>
        {label}
      </button>
    {/each}
  </div>

  <div class="container" bind:this={containerEl}>
    <table>
      <thead>
        <tr>
          <th>ID</th>
          <th>Classification</th>
          <th>Phenotype Name</th>
          <th class="right">Count</th>
        </tr>
      </thead>
      <tbody>
        {#each sortedData as d (d.id)}
          <tr id="row-{d.id}" class:highlighted={d.id === hoveredId}
              onclick={() => hoveredId = hoveredId === d.id ? null : d.id}>
            <td class="mono">{d.id}</td>
            <td>
              <span class="chip" style="background:{d.color}22; color:{d.color}">{d.system}</span>
            </td>
            <td class="name" title={d.name}>{d.name}</td>
            <td class="right mono">{d.count.toLocaleString()}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</div>

<style>
  .panel {
    display: flex;
    flex-direction: column;
    width: 100%;
    flex-shrink: 0;
    background: var(--surface-panel);
    border: 1px solid var(--border-strong);
    border-radius: 10px;
    overflow: hidden;
    box-shadow: var(--shadow-sm);
    /* height set via inline style from prop */
  }

  .toolbar {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.55rem 0.75rem;
    background: var(--surface-raised);
    border-bottom: 1px solid var(--border-strong);
    flex-shrink: 0;
  }

  .sort-label {
    font-size: 0.7rem;
    color: var(--text-muted);
    margin-right: 0.15rem;
  }

  .sort-btn {
    padding: 0.18rem 0.55rem;
    font-size: 0.7rem;
    border: 1px solid var(--border-strong);
    border-radius: 999px;
    background: transparent;
    color: var(--text-secondary);
    cursor: pointer;
    transition: all 0.12s;
  }
  .sort-btn:hover { background: var(--surface-hover); color: var(--text-primary); }
  .sort-btn.active {
    background: var(--accent);
    color: var(--text-on-accent);
    border-color: var(--accent);
  }

  .container {
    overflow-y: auto;
    flex: 1;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.74rem;
  }

  thead {
    position: sticky;
    top: 0;
    background: var(--surface-sunken);
    z-index: 1;
  }

  th {
    padding: 0.45rem 0.7rem;
    text-align: left;
    font-weight: 600;
    color: var(--text-secondary);
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    border-bottom: 1px solid var(--border-strong);
  }

  td {
    padding: 0.38rem 0.7rem;
    border-bottom: 1px solid var(--border-soft);
    color: var(--text-primary);
    vertical-align: middle;
  }

  tbody tr { cursor: pointer; }
  tbody tr:hover td { background: var(--surface-hover); }
  tr.highlighted td { background: var(--accent-active-bg); color: var(--accent-active-fg); }
  tr.highlighted .chip { outline: 1px solid currentColor; }

  .mono {
    font-family: var(--mono);
    font-size: 0.7rem;
    color: var(--text-muted);
  }

  .right { text-align: right; }

  .name {
    max-width: 170px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .chip {
    display: inline-block;
    padding: 0.1rem 0.4rem;
    border-radius: 999px;
    font-size: 0.63rem;
    font-weight: 600;
    white-space: nowrap;
  }
</style>

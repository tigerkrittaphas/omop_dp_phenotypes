<script>
  import { onMount, onDestroy } from 'svelte'
  import * as d3 from 'd3'

  let {
    phenotypes = [],
    selectedA = $bindable(null),
    selectedB = $bindable(null),
  } = $props()

  let svgEl = $state()
  let simulation
  let legendSystems = $state([])
  let tooltip = $state({ visible: false, x: 0, y: 0, name: '', count: 0, system: '' })

  const WIDTH = 700
  const HEIGHT = 700
  const MIN_RADIUS = 5
  const MAX_RADIUS = 12
  const MAX_NODES = 500
  const NODE_HIGHLIGHT_SCALE = 1.6
  const LINK_DISTANCE = 60
  const LINK_STRENGTH = 0.8
  const CHARGE_STRENGTH = -10
  const CENTER_STRENGTH = 0.05
  const COLLISION_PADDING = 3
  const COLLISION_STRENGTH = 0.9
  const CLUSTER_STRENGTH = 0.2
  const CLUSTER_REPEL_BASE = 5000

  const COLOR_A = '#22c55e'
  const COLOR_B = '#f59e0b'
  const COLOR_AB_EDGE = '#eab308'

  const SYSTEM_COLORS = {
    'Cardiovascular':         '#ef4444',
    'Neurological':           '#8b5cf6',
    'Respiratory':            '#06b6d4',
    'Oncology':               '#f97316',
    'Gastrointestinal':       '#84cc16',
    'Endocrine / Metabolic':  '#eab308',
    'Musculoskeletal':        '#a16207',
    'Infectious Disease':     '#10b981',
    'Psychiatric':            '#ec4899',
    'Renal / Urological':     '#3b82f6',
    'Hematological':          '#dc2626',
    'Allergy / Immunology':   '#f43f5e',
    'Dermatological':         '#fb923c',
    'Obstetrics / Gynecology':'#d946ef',
    'Ophthalmological':       '#0ea5e9',
    'Other':                  '#94a3b8',
  }
  const systemColor = (s) => SYSTEM_COLORS[s] ?? SYSTEM_COLORS['Other']

  /** @type {(a: number | null, b: number | null) => void} */
  let applySelection = () => {}

  $effect(() => { applySelection(selectedA, selectedB) })

  function handleNodeClick(id) {
    if (id === selectedA) { selectedA = null; return }
    if (id === selectedB) { selectedB = null; return }
    if (selectedA == null) { selectedA = id; return }
    if (selectedB == null) { selectedB = id; return }
    // both filled: FIFO — drop A, slide B → A, new becomes B
    selectedA = selectedB
    selectedB = id
  }

  onMount(() => {
    const valid = phenotypes.filter(p => p.concept_ids && p.concept_ids.length > 0)
    const conceptToPhenotypes = new Map()
    for (const p of valid) {
      for (const cid of p.concept_ids) {
        if (!conceptToPhenotypes.has(cid)) conceptToPhenotypes.set(cid, [])
        conceptToPhenotypes.get(cid).push(p.cohort_id)
      }
    }
    const edgeWeight = new Map()
    for (const members of conceptToPhenotypes.values()) {
      if (members.length < 2) continue
      for (let i = 0; i < members.length; i++) {
        for (let j = i + 1; j < members.length; j++) {
          const a = Math.min(members[i], members[j])
          const b = Math.max(members[i], members[j])
          const key = `${a}-${b}`
          edgeWeight.set(key, (edgeWeight.get(key) ?? 0) + 1)
        }
      }
    }
    const nodes = valid
      .map(p => ({
        id: p.cohort_id,
        name: p.phenotype_name,
        count: p.dp_count ?? 0,
        concepts: p.concept_ids.length,
        system: p.system ?? 'Other',
        color: systemColor(p.system),
      }))
      .slice(0, MAX_NODES)
      .filter(p => p.count > 0)
    const nodeIds = new Set(nodes.map(n => n.id))
    const links = Array.from(edgeWeight.entries())
      .map(([key, weight]) => {
        const [s, t] = key.split('-').map(Number)
        return { source: s, target: t, weight }
      })
      .filter(l => nodeIds.has(l.source) && nodeIds.has(l.target))

    legendSystems = Object.entries(SYSTEM_COLORS)
      .filter(([name]) => nodes.some(n => n.system === name))
      .map(([name, color]) => ({ name, color }))

    drawGraph(nodes, links)
  })

  onDestroy(() => {
    simulation?.stop()
  })

  function drawGraph(nodes, links) {
    const sortedCounts = nodes.map(n => n.count).sort(d3.ascending)
    const countMax = d3.quantile(sortedCounts, 0.99) ?? sortedCounts[sortedCounts.length - 1]
    const rScale = d3.scaleSqrt().domain([0, countMax]).range([MIN_RADIUS, MAX_RADIUS]).clamp(true)

    const weightExtent = d3.extent(links, d => d.weight)
    const strokeScale = d3.scaleLinear().domain(weightExtent).range([1.5, 4])
    const opacityScale = d3.scaleLinear().domain(weightExtent).range([0.4, 0.9])

    const svg = d3.select(svgEl)
      .attr('viewBox', `0 0 ${WIDTH} ${HEIGHT}`)
      .attr('width', '100%')
      .attr('height', HEIGHT)

    const linkG = svg.append('g').attr('class', 'links')
    const linkEl = linkG.selectAll('line')
      .data(links)
      .join('line')
      .attr('class', 'graph-link')
      .attr('stroke-width', d => strokeScale(d.weight))
      .attr('stroke-opacity', d => opacityScale(d.weight))

    const nodeG = svg.append('g').attr('class', 'nodes')
    const nodeEl = nodeG.selectAll('circle')
      .data(nodes)
      .join('circle')
      .attr('r', d => rScale(d.count))
      .attr('fill', d => d.color)
      .attr('stroke', d => d3.color(d.color).darker(0.8))
      .attr('stroke-width', 0.8)
      .attr('cursor', 'pointer')
      .on('mousemove', (event, d) => {
        tooltip = {
          visible: true,
          x: event.offsetX > WIDTH - 280 ? event.offsetX - 280 : event.offsetX + 12,
          y: event.offsetY - 10,
          name: d.name,
          count: d.count,
          system: d.system,
        }
      })
      .on('mouseleave', () => { tooltip = { ...tooltip, visible: false } })
      .on('click', (_event, d) => handleNodeClick(d.id))
      .call(
        d3.drag()
          .on('start', (event, d) => {
            if (!event.active) simulation.alphaTarget(0.3).restart()
            d.fx = d.x; d.fy = d.y
          })
          .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y })
          .on('end', (event, d) => {
            if (!event.active) simulation.alphaTarget(0)
            d.fx = null; d.fy = null
          })
      )

    applySelection = (a, b) => {
      const hasSel = a != null || b != null
      nodeEl
        .transition().duration(180)
        .attr('r', d => {
          if (d.id === a || d.id === b) return rScale(d.count) * NODE_HIGHLIGHT_SCALE
          return rScale(d.count)
        })
        .attr('fill', d => {
          if (d.id === a) return COLOR_A
          if (d.id === b) return COLOR_B
          return d.color
        })
        .attr('stroke', d => {
          if (d.id === a) return d3.color(COLOR_A).darker(1.0)
          if (d.id === b) return d3.color(COLOR_B).darker(1.0)
          return d3.color(d.color).darker(0.8)
        })
        .attr('stroke-width', d => (d.id === a || d.id === b) ? 3 : 0.8)
        .attr('opacity', d => !hasSel || d.id === a || d.id === b ? 1 : 0.25)
      linkEl
        .transition().duration(180)
        .attr('stroke', d => {
          const sId = d.source.id ?? d.source
          const tId = d.target.id ?? d.target
          const isAB = (sId === a && tId === b) || (sId === b && tId === a)
          return isAB ? COLOR_AB_EDGE : null
        })
        .attr('stroke-width', d => {
          const sId = d.source.id ?? d.source
          const tId = d.target.id ?? d.target
          const isAB = (sId === a && tId === b) || (sId === b && tId === a)
          return isAB ? Math.max(4, strokeScale(d.weight) * 1.8) : strokeScale(d.weight)
        })
        .attr('stroke-opacity', d => {
          const sId = d.source.id ?? d.source
          const tId = d.target.id ?? d.target
          const isAB = (sId === a && tId === b) || (sId === b && tId === a)
          if (isAB) return 1
          if (!hasSel) return opacityScale(d.weight)
          const touches = sId === a || sId === b || tId === a || tId === b
          return touches ? opacityScale(d.weight) * 0.6 : 0.06
        })
      simulation.alpha(0.2).restart()
    }

    function forceCluster(alpha) {
      const centroids = new Map()
      for (const node of nodes) {
        if (!centroids.has(node.system)) centroids.set(node.system, { x: 0, y: 0, n: 0 })
        const c = centroids.get(node.system)
        c.x += node.x; c.y += node.y; c.n++
      }
      for (const c of centroids.values()) { c.x /= c.n; c.y /= c.n }
      for (const node of nodes) {
        const c = centroids.get(node.system)
        node.vx += (c.x - node.x) * CLUSTER_STRENGTH * alpha
        node.vy += (c.y - node.y) * CLUSTER_STRENGTH * alpha
      }
      const entries = Array.from(centroids.entries())
      for (let i = 0; i < entries.length; i++) {
        for (let j = i + 1; j < entries.length; j++) {
          const [sysA, ca] = entries[i]
          const [sysB, cb] = entries[j]
          const dx = ca.x - cb.x, dy = ca.y - cb.y
          const dist = Math.sqrt(dx * dx + dy * dy) || 1
          const repel = (CLUSTER_REPEL_BASE / (dist * dist)) * alpha
          for (const node of nodes) {
            if (node.system === sysA) { node.vx += (dx / dist) * repel; node.vy += (dy / dist) * repel }
            else if (node.system === sysB) { node.vx -= (dx / dist) * repel; node.vy -= (dy / dist) * repel }
          }
        }
      }
    }

    simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(links).id(d => d.id).distance(LINK_DISTANCE).strength(LINK_STRENGTH))
      .force('charge', d3.forceManyBody().strength(CHARGE_STRENGTH))
      .force('x', d3.forceX(WIDTH / 2).strength(CENTER_STRENGTH))
      .force('y', d3.forceY(HEIGHT / 2).strength(CENTER_STRENGTH))
      .force('collision', d3.forceCollide().radius(d => rScale(d.count) + COLLISION_PADDING).strength(COLLISION_STRENGTH))
      .force('cluster', forceCluster)
      .on('tick', () => {
        for (const d of nodes) {
          d.x = Math.max(MAX_RADIUS, Math.min(WIDTH - MAX_RADIUS, d.x))
          d.y = Math.max(MAX_RADIUS, Math.min(HEIGHT - MAX_RADIUS, d.y))
        }
        linkEl
          .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
          .attr('x2', d => d.target.x).attr('y2', d => d.target.y)
        nodeEl
          .attr('cx', d => d.x)
          .attr('cy', d => d.y)
      })
  }
</script>

<div class="wrapper">
  <div class="container">
    <svg bind:this={svgEl}></svg>

    <button
      type="button"
      class="reset-btn"
      onclick={() => { selectedA = null; selectedB = null }}
      disabled={selectedA == null && selectedB == null}
      aria-label="Reset cohort A and B"
      title="Clear both selections"
    >
      <svg viewBox="0 0 24 24" width="14" height="14" fill="none"
           stroke="currentColor" stroke-width="2"
           stroke-linecap="round" stroke-linejoin="round">
        <path d="M3 12a9 9 0 1 0 3-6.7" />
        <polyline points="3 4 3 10 9 10" />
      </svg>
      <span>Reset</span>
    </button>

    {#if tooltip.visible}
      <div class="tooltip" style="left:{tooltip.x}px; top:{tooltip.y}px">
        <strong>{tooltip.name}</strong>
        <span class="system-tag" style="background:{systemColor(tooltip.system)}22; color:{systemColor(tooltip.system)}">
          {tooltip.system}
        </span>
        <span>Patients: {tooltip.count.toLocaleString()}</span>
      </div>
    {/if}
  </div>

  <div class="hint">
    Click a node to set <span class="chip chip-a">A</span>, then another for
    <span class="chip chip-b">B</span>. Click again to clear.
  </div>

  <div class="legend">
    {#each legendSystems as s}
      <span class="legend-item">
        <span class="legend-dot" style="background:{s.color}"></span>
        {s.name}
      </span>
    {/each}
  </div>
</div>

<style>
  .wrapper {
    background: var(--surface-panel);
    border: 1px solid var(--border-strong);
    border-radius: 10px;
    padding: 1rem;
    box-shadow: var(--shadow-sm);
  }
  .container { position: relative; overflow: hidden; }
  :global(.graph-link) { stroke: var(--link-color); }

  .reset-btn {
    position: absolute;
    top: 0.5rem;
    right: 0.5rem;
    z-index: 12;
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.3rem 0.6rem;
    border: 1px solid var(--border-strong);
    background: var(--surface-panel);
    color: var(--text-secondary);
    border-radius: 6px;
    font-size: 0.72rem;
    font-weight: 500;
    cursor: pointer;
    box-shadow: var(--shadow-sm);
    transition: background-color 0.12s, color 0.12s, border-color 0.12s;
  }
  .reset-btn:hover:not(:disabled) {
    background: var(--surface-hover);
    color: var(--text-primary);
    border-color: var(--accent);
  }
  .reset-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
  .reset-btn svg { display: block; }

  .tooltip {
    position: absolute;
    pointer-events: none;
    background: var(--tooltip-bg);
    color: var(--tooltip-text);
    border-radius: 6px;
    padding: 0.5rem 0.75rem;
    font-size: 0.8rem;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    max-width: 280px;
    z-index: 10;
    box-shadow: var(--shadow-md);
  }
  .tooltip strong { font-size: 0.85rem; line-height: 1.3; }
  .system-tag {
    display: inline-block;
    padding: 0.1rem 0.4rem;
    border-radius: 999px;
    font-size: 0.7rem;
    font-weight: 600;
    align-self: flex-start;
  }
  .hint {
    margin-top: 0.6rem;
    font-size: 0.72rem;
    color: var(--text-muted);
    text-align: center;
  }
  .chip {
    display: inline-block;
    padding: 0.05rem 0.4rem;
    border-radius: 999px;
    font-size: 0.65rem;
    font-weight: 700;
    color: white;
    margin: 0 0.1rem;
  }
  .chip-a { background: #22c55e; }
  .chip-b { background: #f59e0b; }
  .legend {
    margin-top: 0.8rem;
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem 1rem;
    justify-content: center;
  }
  .legend-item {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    font-size: 0.75rem;
    color: var(--text-secondary);
  }
  .legend-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
  }
</style>

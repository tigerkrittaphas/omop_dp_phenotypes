<script>
  import { onMount, onDestroy, tick } from 'svelte'
  import * as d3 from 'd3'
  import PhenotypeTable from './PhenotypeTable.svelte'
  import CohortDefinition from './CohortDefinition.svelte'

  let svgEl = $state()
  let simulation
  let themeObserver
  let loading = $state(true)
  let error = $state('')
  let tooltip = $state({ visible: false, x: 0, y: 0, name: '', count: 0, concepts: 0, system: '' })
  let legendSystems = $state([])
  let tableData = $state([])
  let sortBy = $state('count')
  let hoveredId = $state(null)
  let tableWidth = $state(520)
  let resizingTable = false
  let resizeStartX = 0
  let resizeStartWidth = 520

  // Set by drawGraph; called whenever hoveredId changes to sync D3 visuals
  let applySelection = (_id) => {}

  const selectedNode = $derived(tableData.find(n => n.id === hoveredId) ?? null)

  $effect(() => {
    applySelection(hoveredId)
  })

  const WIDTH = 700
  const HEIGHT = 700
  const MIN_RADIUS = 2
  const MAX_RADIUS = 12
  const MAX_NODES = 500
  const TABLE_MIN_WIDTH = 420
  const TABLE_MAX_WIDTH = 900

  // Force layout tuning knobs (grouped for easier adjustment)
  const NODE_HIGHLIGHT_SCALE = 1.6
  const LINK_DISTANCE = 60
  const LINK_STRENGTH = 0.8
  const CHARGE_STRENGTH = -10
  const CENTER_STRENGTH = 0.05
  const COLLISION_PADDING = 3
  const COLLISION_STRENGTH = 0.9
  const HOVER_REPEL_RADIUS = 30
  const HOVER_REPEL_STRENGTH = 10.0
  const CLUSTER_STRENGTH = 0.2
  const CLUSTER_REPEL_BASE = 5000

  // Color map keyed by system name — must match values produced by classify_system() in Python
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

  function systemColor(system) {
    return SYSTEM_COLORS[system] ?? SYSTEM_COLORS['Other']
  }

  function selectedFillColor() {
    const theme = document.documentElement.getAttribute('data-theme')
    return theme === 'dark' ? '#ffffff' : '#000000'
  }

  function clampTableWidth(value) {
    return Math.max(TABLE_MIN_WIDTH, Math.min(TABLE_MAX_WIDTH, value))
  }

  function onTableResizeMove(event) {
    if (!resizingTable) return
    const delta = resizeStartX - event.clientX
    tableWidth = clampTableWidth(resizeStartWidth + delta)
  }

  function stopTableResize() {
    if (!resizingTable) return
    resizingTable = false
    window.removeEventListener('mousemove', onTableResizeMove)
    window.removeEventListener('mouseup', stopTableResize)
    document.body.classList.remove('col-resize-active')
  }

  function startTableResize(event) {
    event.preventDefault()
    resizingTable = true
    resizeStartX = event.clientX
    resizeStartWidth = tableWidth
    window.addEventListener('mousemove', onTableResizeMove)
    window.addEventListener('mouseup', stopTableResize)
    document.body.classList.add('col-resize-active')
  }

  onMount(async () => {
    try {
      const countsFile = import.meta.env.VITE_PHENOTYPE_COUNTS_FILE
      const res = await fetch(`${import.meta.env.BASE_URL}${countsFile}`)
      if (!res.ok) throw new Error(`Failed to load JSON: ${res.status}`)
      const phenotypes = await res.json()

      const valid = phenotypes.filter(p => p.concept_ids && p.concept_ids.length > 0)

      // concept_id → list of cohort_ids
      const conceptToPhenotypes = new Map()
      for (const p of valid) {
        for (const cid of p.concept_ids) {
          if (!conceptToPhenotypes.has(cid)) conceptToPhenotypes.set(cid, [])
          conceptToPhenotypes.get(cid).push(p.cohort_id)
        }
      }

      // Edges: pairs sharing ≥1 concept_id; weight = shared concept count
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

      // Build legend from systems actually present, preserving SYSTEM_COLORS order
      legendSystems = Object.entries(SYSTEM_COLORS)
        .filter(([name]) => nodes.some(n => n.system === name))
        .map(([name, color]) => ({ name, color }))

      tableData = nodes

      loading = false
      await tick()
      drawGraph(nodes, links)

      // Keep selected node color in sync when the global theme changes.
      themeObserver?.disconnect()
      themeObserver = new MutationObserver(() => {
        applySelection(hoveredId)
      })
      themeObserver.observe(document.documentElement, {
        attributes: true,
        attributeFilter: ['data-theme'],
      })
    } catch (e) {
      error = e instanceof Error ? e.message : 'Unknown error'
      loading = false
    }
  })

  onDestroy(() => {
    simulation?.stop()
    themeObserver?.disconnect()
    stopTableResize()
  })

  function drawGraph(nodes, links) {
    const countExtent = d3.extent(nodes, d => d.count)
    const rScale = d3.scaleSqrt().domain(countExtent).range([MIN_RADIUS, MAX_RADIUS])

    const weightExtent = d3.extent(links, d => d.weight)
    const strokeScale = d3.scaleLinear().domain(weightExtent).range([1.5, 4])
    const opacityScale = d3.scaleLinear().domain(weightExtent).range([0.4, 0.9])

    const svg = d3.select(svgEl)
      .attr('viewBox', `0 0 ${WIDTH} ${HEIGHT}`)
      .attr('width', '100%')
      .attr('height', HEIGHT)

    svg.append('defs')

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
        d3.select(event.currentTarget)
          .transition().duration(50)
          .attr('r', rScale(d.count) * NODE_HIGHLIGHT_SCALE)
          .attr('stroke-width', 2)
        hoveredNode = d
        if (!event.active) simulation.alphaTarget(0.12).restart()
        tooltip = {
          visible: true,
          x: event.offsetX > WIDTH - 300 ? event.offsetX - 300 : event.offsetX + 12,
          y: event.offsetY - 10,
          name: d.name,
          count: d.count,
          concepts: d.concepts,
          system: d.system,
        }
      })
      .on('mouseleave', (event, d) => {
        // only shrink if not the selected node
        if (d.id !== hoveredId) {
          d3.select(event.currentTarget)
            .transition().duration(200)
            .attr('r', rScale(d.count))
            .attr('stroke-width', 0.8)
        }
        hoveredNode = null
        simulation.alphaTarget(0)
        tooltip = { ...tooltip, visible: false }
      })
      .on('click', (_event, d) => {
        hoveredId = hoveredId === d.id ? null : d.id
      })
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

    applySelection = (sid) => {
      nodeEl
        .transition().duration(150)
        .attr('r', d => d.id === sid ? rScale(d.count) * NODE_HIGHLIGHT_SCALE : rScale(d.count))
        .attr('fill', d => d.id === sid ? selectedFillColor() : d.color)
        .attr('stroke', d => d.id === sid
          ? d3.color(d.color).brighter(0.5)
          : d3.color(d.color).darker(0.8))
        .attr('stroke-width', d => d.id === sid ? 2.5 : 0.8)
      // reheat simulation so collision force recalculates with updated radius
      simulation.alpha(0.3).restart()
    }

    let hoveredNode = null
    function forceHoverRepel(alpha) {
      if (!hoveredNode) return
      const hx = hoveredNode.x, hy = hoveredNode.y
      for (const node of nodes) {
        if (node === hoveredNode) continue
        const dx = node.x - hx
        const dy = node.y - hy
        const dist = Math.sqrt(dx * dx + dy * dy) || 1
        if (dist < HOVER_REPEL_RADIUS) {
          const force = HOVER_REPEL_STRENGTH * alpha * (1 - dist / HOVER_REPEL_RADIUS)
          node.vx += (dx / dist) * force
          node.vy += (dy / dist) * force
        }
      }
    }

    // Pull each node toward its system's live centroid — O(n) per tick
    function forceCluster(alpha) {
      // Pass 1: compute centroid per system
      const centroids = new Map()
      for (const node of nodes) {
        if (!centroids.has(node.system)) centroids.set(node.system, { x: 0, y: 0, n: 0 })
        const c = centroids.get(node.system)
        c.x += node.x; c.y += node.y; c.n++
      }
      for (const c of centroids.values()) { c.x /= c.n; c.y /= c.n }

      // Pass 2: apply attraction toward own centroid
      for (const node of nodes) {
        const c = centroids.get(node.system)
        node.vx += (c.x - node.x) * CLUSTER_STRENGTH * alpha
        node.vy += (c.y - node.y) * CLUSTER_STRENGTH * alpha
      }

      // Pass 3: repel between different-system centroids (12² / 2 = 66 pairs)
      const entries = Array.from(centroids.entries())
      for (let i = 0; i < entries.length; i++) {
        for (let j = i + 1; j < entries.length; j++) {
          const [sysA, ca] = entries[i]
          const [sysB, cb] = entries[j]
          const dx = ca.x - cb.x
          const dy = ca.y - cb.y
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
      .force('collision', d3.forceCollide().radius(d => (d.id === hoveredId ? rScale(d.count) * NODE_HIGHLIGHT_SCALE : rScale(d.count)) + COLLISION_PADDING).strength(COLLISION_STRENGTH))
      .force('cluster', forceCluster)
      .force('hoverRepel', forceHoverRepel)
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
  {#if loading}
    <p class="status">Loading phenotype network…</p>
  {:else if error}
    <p class="status error">Error: {error}</p>
  {:else}
    <div class="main-layout">
      <div class="graph-col">
        <div class="container">
          <svg bind:this={svgEl}></svg>

          {#if tooltip.visible}
            <div class="tooltip" style="left:{tooltip.x}px; top:{tooltip.y}px">
              <strong>{tooltip.name}</strong>
              <span class="system-tag" style="background:{systemColor(tooltip.system)}22; color:{systemColor(tooltip.system)}">
                {tooltip.system}
              </span>
              <span>Patients: {tooltip.count.toLocaleString()}</span>
              <span>Concept IDs: {tooltip.concepts}</span>
            </div>
          {/if}
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

      <button
        type="button"
        class="table-resizer"
        aria-label="Resize table"
        onmousedown={startTableResize}
      ></button>

      <div class="table-col" style="width:{tableWidth}px">
        <PhenotypeTable data={tableData} bind:hoveredId bind:sortBy height={HEIGHT} />
      </div>
    </div>

    <CohortDefinition
      cohortId={selectedNode?.id}
      phenotypeName={selectedNode?.name}
      system={selectedNode?.system}
      color={selectedNode?.color}
    />
  {/if}
</div>

<style>
  .wrapper {
    font-family: var(--sans);
  }

  .main-layout {
    display: flex;
    align-items: flex-start;
    gap: 0.6rem;
  }

  .graph-col {
    flex: 1;
    min-width: 0;
    background: var(--surface-panel);
    border: 1px solid var(--border-strong);
    border-radius: 10px;
    padding: 1rem;
    box-shadow: var(--shadow-sm);
  }

  .table-col {
    width: 520px;
    flex-shrink: 0;
  }

  .table-resizer {
    width: 12px;
    margin: 0 0.15rem;
    border: 0;
    padding: 0;
    border-radius: 999px;
    cursor: col-resize;
    align-self: stretch;
    background: transparent;
    position: relative;
  }

  .table-resizer::before {
    content: '';
    position: absolute;
    top: 1rem;
    bottom: 1rem;
    left: 50%;
    transform: translateX(-50%);
    width: 3px;
    border-radius: 999px;
    background: var(--border-strong);
    opacity: 0.65;
    transition: opacity 0.15s, background-color 0.15s;
  }

  .table-resizer:hover::before {
    opacity: 1;
    background: var(--accent);
  }

  :global(body.col-resize-active) {
    cursor: col-resize;
    user-select: none;
  }

  .container {
    position: relative;
    overflow: hidden;
  }

  :global(.graph-link) {
    stroke: var(--link-color);
  }

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

  .tooltip strong {
    font-size: 0.85rem;
    line-height: 1.3;
  }

  .system-tag {
    display: inline-block;
    padding: 0.1rem 0.4rem;
    border-radius: 999px;
    font-size: 0.7rem;
    font-weight: 600;
    align-self: flex-start;
  }

  .legend {
    margin-top: 1rem;
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

  .status { color: var(--text-secondary); padding: 2rem; text-align: center; }
  .error { color: var(--status-error); }
</style>

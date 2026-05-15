<script>
  let { cohortId, phenotypeName, system, color } = $props()

  let def = $state(null)
  let loading = $state(false)
  let error = $state('')

  const BASE = 'https://raw.githubusercontent.com/OHDSI/PhenotypeLibrary/main/inst/cohorts'

  $effect(() => {
    if (!cohortId) { def = null; return }
    loading = true; error = ''
    fetch(`${BASE}/${cohortId}.json`)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then(d => { def = d; loading = false })
      .catch(e => { error = e.message; loading = false })
  })

  // Human-readable domain label from ATLAS criterion key
  const DOMAIN_LABELS = {
    ConditionOccurrence: 'Condition Occurrence',
    DrugExposure:        'Drug Exposure',
    ProcedureOccurrence: 'Procedure Occurrence',
    Measurement:         'Measurement',
    Observation:         'Observation',
    VisitOccurrence:     'Visit Occurrence',
    DeviceExposure:      'Device Exposure',
    Death:               'Death',
    Specimen:            'Specimen',
  }

  function criterionDomain(criterion) {
    const key = Object.keys(criterion)[0]
    return DOMAIN_LABELS[key] ?? key
  }

  function endStrategyLabel(es) {
    if (!es) return 'Event end date'
    if (es.DateOffset) {
      const field = es.DateOffset.DateField === 'EndDate' ? 'event end date' : 'event start date'
      return `${es.DateOffset.Offset} day(s) after ${field}`
    }
    if (es.CustomEra) return `Custom ERA — gap: ${es.CustomEra.GapDays} day(s)`
    return JSON.stringify(es)
  }

  function collapseLabel(cs) {
    if (!cs) return '—'
    if (cs.CollapseType === 'ERA') return `ERA collapse, ${cs.EraPad}-day gap`
    return cs.CollapseType
  }
</script>

{#if cohortId}
  <div class="panel">
    <div class="panel-header">
      <div class="title-row">
        <span class="cohort-id">#{cohortId}</span>
        <h2 class="name">{phenotypeName}</h2>
        <span class="system-chip" style="background:{color}22; color:{color}">{system}</span>
      </div>
    </div>

    {#if loading}
      <p class="status">Loading cohort definition…</p>
    {:else if error}
      <p class="status error">Failed to load: {error}</p>
    {:else if def}
      <div class="body">

        <!-- Primary Criteria -->
        <section>
          <h3>Primary Criteria</h3>
          <div class="criteria-list">
            {#each def.PrimaryCriteria.CriteriaList as c}
              {@const domain = criterionDomain(c)}
              {@const csId = Object.values(c)[0].CodesetId}
              {@const cs = def.ConceptSets.find(s => s.id === csId)}
              <div class="criterion-card">
                <span class="domain-badge">{domain}</span>
                {#if cs}
                  <span class="cs-name">{cs.name}</span>
                  <div class="concept-table">
                    <table>
                      <thead>
                        <tr><th>Concept</th><th>Code</th><th>Vocabulary</th><th>Descendants</th><th>Exclude</th></tr>
                      </thead>
                      <tbody>
                        {#each cs.expression.items as item}
                          <tr class:excluded={item.isExcluded}>
                            <td>{item.concept.CONCEPT_NAME}</td>
                            <td class="mono">{item.concept.CONCEPT_CODE}</td>
                            <td>{item.concept.VOCABULARY_ID}</td>
                            <td class="center">{item.includeDescendants ? '✓' : '—'}</td>
                            <td class="center">{item.isExcluded ? '✓' : '—'}</td>
                          </tr>
                        {/each}
                      </tbody>
                    </table>
                  </div>
                {/if}
              </div>
            {/each}
          </div>

          <div class="meta-row">
            <div class="meta-item">
              <span class="meta-label">Observation window</span>
              <span class="meta-value">
                {def.PrimaryCriteria.ObservationWindow.PriorDays} days prior,
                {def.PrimaryCriteria.ObservationWindow.PostDays} days post
              </span>
            </div>
            <div class="meta-item">
              <span class="meta-label">Qualified limit</span>
              <span class="meta-value">{def.QualifiedLimit?.Type ?? '—'}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">Expression limit</span>
              <span class="meta-value">{def.ExpressionLimit?.Type ?? '—'}</span>
            </div>
          </div>
        </section>

        <!-- Inclusion Rules -->
        {#if def.InclusionRules?.length}
          <section>
            <h3>Inclusion Rules <span class="count-badge">{def.InclusionRules.length}</span></h3>
            <ol class="inclusion-list">
              {#each def.InclusionRules as rule}
                <li>
                  <strong>{rule.name}</strong>
                  {#if rule.description}<p class="rule-desc">{rule.description}</p>{/if}
                </li>
              {/each}
            </ol>
          </section>
        {/if}

        <!-- Cohort Exit -->
        <section>
          <h3>Cohort Exit</h3>
          <div class="meta-row">
            <div class="meta-item">
              <span class="meta-label">End strategy</span>
              <span class="meta-value">{endStrategyLabel(def.EndStrategy)}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">Collapse</span>
              <span class="meta-value">{collapseLabel(def.CollapseSettings)}</span>
            </div>
            {#if def.CensorWindow?.StartDate || def.CensorWindow?.EndDate}
              <div class="meta-item">
                <span class="meta-label">Censor window</span>
                <span class="meta-value">{def.CensorWindow.StartDate ?? '…'} – {def.CensorWindow.EndDate ?? '…'}</span>
              </div>
            {/if}
          </div>
        </section>

      </div>
    {/if}
  </div>
{/if}

<style>
  .panel {
    margin-top: 1.5rem;
    background: var(--surface-panel);
    border: 1px solid var(--border-strong);
    border-radius: 10px;
    overflow: hidden;
    font-family: var(--sans);
    box-shadow: var(--shadow-sm);
  }

  .panel-header {
    padding: 0.75rem 1.25rem;
    background: var(--surface-raised);
    border-bottom: 1px solid var(--border-strong);
  }

  .title-row {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    flex-wrap: wrap;
  }

  .cohort-id {
    font-family: var(--mono);
    font-size: 0.75rem;
    color: var(--text-muted);
  }

  .name {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
    color: var(--text-strong);
  }

  .system-chip {
    padding: 0.15rem 0.55rem;
    border-radius: 999px;
    font-size: 0.68rem;
    font-weight: 600;
  }

  .status { padding: 1rem 1.25rem; color: var(--text-secondary); font-size: 0.85rem; }
  .error { color: var(--status-error); }

  .body {
    display: flex;
    gap: 0;
    flex-direction: column;
  }

  section {
    padding: 1rem 1.25rem;
    border-bottom: 1px solid var(--border-soft);
  }
  section:last-child { border-bottom: none; }

  h3 {
    margin: 0 0 0.65rem;
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-secondary);
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }

  .count-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: var(--accent);
    color: var(--text-on-accent);
    border-radius: 999px;
    font-size: 0.65rem;
    font-weight: 700;
    padding: 0 0.4rem;
    min-width: 1.2em;
    letter-spacing: 0;
    text-transform: none;
  }

  .criteria-list { display: flex; flex-direction: column; gap: 0.75rem; }

  .criterion-card {
    background: var(--surface-raised);
    border: 1px solid var(--border-strong);
    border-radius: 8px;
    padding: 0.65rem 0.9rem;
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }

  .domain-badge {
    display: inline-block;
    background: var(--accent-soft-bg);
    color: var(--accent-strong);
    border-radius: 4px;
    padding: 0.1rem 0.45rem;
    font-size: 0.68rem;
    font-weight: 600;
    align-self: flex-start;
  }

  .cs-name {
    font-size: 0.82rem;
    font-weight: 500;
    color: var(--text-primary);
  }

  .concept-table { overflow-x: auto; margin-top: 0.25rem; }

  .concept-table table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.73rem;
  }

  .concept-table th {
    padding: 0.3rem 0.6rem;
    background: var(--surface-sunken);
    text-align: left;
    font-weight: 600;
    color: var(--text-secondary);
    font-size: 0.67rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    border-bottom: 1px solid var(--border-strong);
  }

  .concept-table td {
    padding: 0.3rem 0.6rem;
    border-bottom: 1px solid var(--border-soft);
    color: var(--text-primary);
  }

  .concept-table tr.excluded td { color: var(--text-muted); text-decoration: line-through; }
  .mono { font-family: var(--mono); font-size: 0.68rem; color: var(--text-secondary); }
  .center { text-align: center; }

  .meta-row {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem 2rem;
    margin-top: 0.5rem;
  }

  .meta-item {
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
  }

  .meta-label {
    font-size: 0.67rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
  }

  .meta-value {
    font-size: 0.8rem;
    color: var(--text-primary);
  }

  .inclusion-list {
    margin: 0;
    padding-left: 1.2rem;
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }

  .inclusion-list li {
    font-size: 0.82rem;
    color: var(--text-primary);
  }

  .rule-desc {
    margin: 0.15rem 0 0;
    font-size: 0.75rem;
    color: var(--text-secondary);
  }
</style>

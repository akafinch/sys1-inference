<script>
  // Each ask's round trip as three legs, all measured, none estimated:
  //   OpenJev        OpenJev's own wall clock, the total of its Server-Timing header
  //   app → OpenJev  the app's timed call to OpenJev, less OpenJev's time
  //   browser → app  the browser's round trip, less the app's call
  // so the legs always add up to the round trip the browser saw.
  let { history } = $props()

  const LEGS = [
    { key: 'openjev', name: 'OpenJev' },
    { key: 'app', name: 'app → OpenJev' },
    { key: 'browser', name: 'browser → app' },
  ]
  const SHOWN = 10

  function legs({ roundTripMs, backendMs, openjevMs }) {
    if (backendMs === null) return { openjev: null, app: null, browser: roundTripMs } // the app answered on its own
    // OpenJev sends no timing with some refusals: its time then stays inside the app's leg
    return { openjev: openjevMs, app: backendMs - (openjevMs ?? 0), browser: roundTripMs - backendMs }
  }

  const ms = (x) => (x === null ? '—' : `${x >= 100 ? Math.round(x).toLocaleString() : x.toFixed(1)} ms`)

  let latest = $derived(history.at(-1))
  let rows = $derived(history.slice(-SHOWN).reverse())
  let longest = $derived(Math.max(...rows.map((a) => a.roundTripMs), 1))
</script>

<h2>Latency</h2>

<ul class="legend" aria-label="Legs">
  {#each LEGS as leg (leg.key)}
    <li><span class="swatch {leg.key}"></span>{leg.name}</li>
  {/each}
</ul>

{#if latest}
  {@const split = legs(latest)}
  <table>
    <caption class="muted">Ask #{latest.n} · {latest.label}</caption>
    <tbody>
      {#each LEGS as leg (leg.key)}
        <tr>
          <th scope="row"><span class="swatch {leg.key}"></span>{leg.name}</th>
          <td>{ms(split[leg.key])}</td>
        </tr>
      {/each}
      <tr class="total">
        <th scope="row">browser round trip</th>
        <td>{ms(latest.roundTripMs)}</td>
      </tr>
    </tbody>
  </table>
  {#if latest.backendMs !== null && latest.openjevMs === null}
    <p class="muted note">OpenJev sent no timing, so its time is inside the app → OpenJev leg.</p>
  {/if}

  <h3>History</h3>
  <ol>
    {#each rows as ask (ask.n)}
      {@const split = legs(ask)}
      <li>
        <span class="label">#{ask.n} {ask.label}{ask.status === 200 ? '' : ` · ${ask.status}`}</span>
        <span class="row">
          <span class="bar" role="img" aria-label={LEGS.map((l) => `${l.name} ${ms(split[l.key])}`).join(', ')}>
            {#each LEGS as leg (leg.key)}
              {#if split[leg.key] > 0}
                <span
                  class="segment {leg.key}"
                  style:width="{(100 * split[leg.key]) / longest}%"
                  title="{leg.name}: {ms(split[leg.key])}"
                ></span>
              {/if}
            {/each}
          </span>
          <small>{ms(ask.roundTripMs)}</small>
        </span>
      </li>
    {/each}
  </ol>
{:else}
  <p class="muted">Ask a question to see where its time goes.</p>
{/if}

<style>
  h2 {
    margin-bottom: 0.5rem;
  }

  h3 {
    margin: 1.2rem 0 0.5rem;
    font-size: 1rem;
  }

  .legend {
    list-style: none;
    padding: 0;
    margin: 0 0 0.6rem;
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem 1rem;
    font-size: 0.85rem;
  }

  .swatch {
    display: inline-block;
    width: 0.8em;
    height: 0.8em;
    border-radius: 3px;
    margin-right: 0.4em;
    vertical-align: -0.05em;
  }

  .openjev {
    background: var(--leg-openjev);
  }

  .app {
    background: var(--leg-app);
  }

  .browser {
    background: var(--leg-browser);
  }

  table {
    border-collapse: collapse;
    width: 100%;
  }

  caption {
    text-align: left;
    font-size: 0.85rem;
    margin-bottom: 0.2rem;
  }

  th {
    text-align: left;
    font-weight: 400;
    padding: 0.15rem 0;
  }

  td {
    text-align: right;
    font-variant-numeric: tabular-nums;
    font-weight: 600;
  }

  tr.total {
    border-top: 1px solid var(--rule);
  }

  .note {
    font-size: 0.8rem;
    margin: 0.4rem 0 0;
  }

  ol {
    list-style: none;
    padding: 0;
    margin: 0;
    display: grid;
    gap: 0.5rem;
  }

  .label {
    display: block;
    font-size: 0.8rem;
  }

  .row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 5.5em;
    gap: 0.5rem;
    align-items: center;
  }

  .bar {
    display: flex;
    gap: 2px; /* the surface between legs */
    height: 16px;
  }

  .segment {
    display: block;
    height: 100%;
    min-width: 2px;
  }

  .segment:last-child {
    border-radius: 0 4px 4px 0;
  }

  small {
    font-size: 0.8rem;
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
  }
</style>

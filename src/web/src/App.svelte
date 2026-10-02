<script>
  import Answer from './lib/Answer.svelte'
  import Latency from './lib/Latency.svelte'

  let targets = $state.raw({}) // name -> {label, model, device}; the app keeps the addresses
  let texts = $state.raw([])
  let status = $state.raw([])
  let failed = $state('')
  let text = $state.raw(null) // the sample text on screen
  let preset = $state.raw(null) // the preset last loaded into the box
  let target = $state('')
  let bodyText = $state('')
  let asking = $state(false)
  let last = $state.raw(null) // the last ask and its reply
  let history = $state.raw([]) // every ask, newest last

  async function getJSON(url) {
    const r = await fetch(url)
    if (!r.ok) throw new Error(`${url} answered ${r.status}`)
    return r.json()
  }

  async function refreshStatus() {
    try {
      status = await getJSON('/api/status')
    } catch (e) {
      status = [{ address: 'the app', device: '', error: e.message }]
    }
  }

  async function start() {
    try {
      const catalogue = await getJSON('/api/presets')
      targets = catalogue.targets
      texts = catalogue.texts
      showText(texts[0])
    } catch (e) {
      failed = e.message
    }
  }

  function showText(t) {
    text = t
    load(t.presets[0])
  }

  // A preset fills the box with the body exactly as OpenJev will receive it, and picks its model.
  function load(p) {
    preset = p
    target = p.target
    const body = { model: targets[target].model, samples: 1, questions: { [p.id]: p.question }, state: text.state }
    bodyText = JSON.stringify(body, null, 2)
    last = null
  }

  // The box's model follows the picker; text that is not valid JSON is left as typed.
  function pick(name) {
    target = name
    try {
      const body = JSON.parse(bodyText)
      body.model = targets[name].model
      bodyText = JSON.stringify(body, null, 2)
    } catch {}
  }

  async function ask() {
    let body
    try {
      body = JSON.parse(bodyText)
    } catch (e) {
      last = { status: 'Not sent', reason: `the box is not valid JSON: ${e.message}` }
      return
    }
    asking = true
    const asked = { target, preset, text }
    let code, raw
    const started = performance.now()
    try {
      const r = await fetch('/api/ask', {
        method: 'POST',
        // without it the app, like OpenJev, will not read the body as JSON
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target, body }),
      })
      code = r.status
      raw = await r.text()
    } catch (e) {
      code = 'No reply'
      raw = JSON.stringify({ detail: `the app did not answer: ${e.message}` })
    }
    const roundTripMs = performance.now() - started
    asking = false

    let reply
    try {
      reply = JSON.parse(raw)
    } catch {
      reply = { detail: raw }
    }
    const ok = code === 200 && reply.openjev?.answers !== undefined
    last = { ...asked, status: code, reply, ok, reason: ok ? '' : reasonOf(reply) }
    const t = targets[asked.target]
    history = [
      ...history,
      {
        n: history.length + 1,
        label: t.label,
        status: code,
        roundTripMs,
        backendMs: reply.backend_ms ?? null,
        openjevMs: reply.openjev_ms ?? null,
      },
    ]
  }

  // Why an ask failed, from whichever side refused it: the app, or OpenJev.
  function reasonOf(reply) {
    if (reply.error) return reply.error // the app could not get an answer from OpenJev
    const detail = reply.openjev ? reply.openjev.detail : reply.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) return detail.map((d) => `${(d.loc ?? []).join('.')}: ${d.msg}`).join('; ')
    if (detail?.message) return `${detail.message} (${detail.error_type})`
    return JSON.stringify(reply.openjev ?? reply)
  }

  // A preset's intended answer holds only while its question and its text are asked unedited.
  function intendedFor(id) {
    const { preset: p, text: t, reply } = last
    const same = (a, b) => JSON.stringify(a) === JSON.stringify(b)
    if (!p || id !== p.id) return undefined
    return same(reply.sent.questions?.[id], p.question) && same(reply.sent.state, t.state) ? p.intended : undefined
  }

  function askOnCtrlEnter(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && !asking) ask()
  }

  start()
  refreshStatus()
</script>

<header>
  <h1>System 1 inference</h1>
  <div class="status">
    {#each status as row}
      <span class:error={row.error}>
        <strong>{row.device.toUpperCase()}</strong>
        {row.error ?? (row.models.join(', ') || 'none of the demo models listed')}
        <span class="muted">· {row.address}</span>
      </span>
    {/each}
    <button class="small" onclick={refreshStatus}>Refresh</button>
  </div>
</header>

{#if failed}
  <p class="error page">Could not load the presets: {failed}</p>
{:else if text}
  <main>
    <section class="ask">
      <nav aria-label="Sample texts">
        {#each texts as t (t.id)}
          <button class:on={t.id === text.id} aria-pressed={t.id === text.id} onclick={() => showText(t)}>{t.title}</button>
        {/each}
      </nav>
      <p class="use-case">{text.use_case}</p>

      <div class="presets" role="group" aria-label="Preset questions">
        {#each text.presets as p (p.id)}
          <button class:on={p.id === preset?.id} aria-pressed={p.id === preset?.id} onclick={() => load(p)}>
            <span class="type">{p.type}</span>
            {p.label}
          </button>
        {/each}
      </div>

      <fieldset class="targets">
        <legend>Model</legend>
        {#each Object.entries(targets) as [name, t] (name)}
          <label class:on={name === target}>
            <input type="radio" name="target" value={name} checked={name === target} onchange={() => pick(name)} />
            {t.label}
          </label>
        {/each}
      </fieldset>

      <label class="box">
        <span class="muted">The request body, as OpenJev receives it. Edit it freely; Ctrl+Enter asks.</span>
        <textarea bind:value={bodyText} onkeydown={askOnCtrlEnter} spellcheck="false" rows="16"></textarea>
      </label>
      <button class="go" onclick={ask} disabled={asking}>{asking ? 'Asking…' : 'Ask'}</button>

      {#if last}
        <section class="result" aria-live="polite">
          {#if last.ok}
            {#each Object.entries(last.reply.openjev.answers) as [id, answer] (id)}
              <Answer {id} {answer} intended={intendedFor(id)} />
            {/each}
            <p class="muted">
              Answered by {last.reply.openjev.model} on the {targets[last.target].device.toUpperCase()} · {last.reply.openjev.usage
                ?.input_tokens} input tokens
            </p>
            <details>
              <summary>The body the app sent</summary>
              <pre>{JSON.stringify(last.reply.sent, null, 2)}</pre>
            </details>
          {:else}
            <p class="error"><strong>{last.status}</strong> {last.reason}</p>
          {/if}
        </section>
      {/if}
    </section>

    <aside>
      <Latency {history} />
    </aside>
  </main>
{/if}

<style>
  header {
    padding: 0.8rem 1.5rem;
    border-bottom: 2px solid var(--rule);
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 0.5rem 2rem;
  }

  .status {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 0.4rem 1.5rem;
  }

  button.small {
    font-size: 0.75rem;
    border-width: 1px;
  }

  main {
    display: grid;
    grid-template-columns: minmax(0, 2fr) minmax(20rem, 1fr);
    gap: 1.5rem;
    padding: 1rem 1.5rem 2rem;
  }

  @media (max-width: 1100px) {
    main {
      grid-template-columns: minmax(0, 1fr);
    }
  }

  .page {
    padding: 1rem 1.5rem;
  }

  nav,
  .presets {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  nav button {
    font-size: 1.15rem;
    font-weight: 600;
  }

  .use-case {
    margin: 0.6rem 0 0.8rem;
  }

  .type {
    font-family: var(--mono);
    font-size: 0.8em;
    margin-right: 0.3em;
    opacity: 0.8;
  }

  .targets {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem 1.2rem;
    margin: 1rem 0;
    border: 0;
    padding: 0;
  }

  .targets legend {
    font-weight: 600;
    margin-bottom: 0.3rem;
  }

  .targets label.on {
    font-weight: 600;
  }

  .targets input {
    width: 1.1em;
    height: 1.1em;
  }

  .box {
    display: grid;
    gap: 0.3rem;
    font-size: 0.85rem;
  }

  textarea {
    font: 17px/1.35 var(--mono);
    color: var(--ink);
    border: 2px solid var(--rule);
    border-radius: 8px;
    padding: 0.6rem;
    resize: vertical;
  }

  button.go {
    margin-top: 0.8rem;
    font-size: 1.2rem;
    font-weight: 600;
    padding: 0.4em 2em;
  }

  .result {
    margin-top: 1.2rem;
    padding-top: 1rem;
    border-top: 2px solid var(--rule);
  }

  details {
    font-size: 0.8rem;
  }

  pre {
    font: 15px/1.35 var(--mono);
    white-space: pre-wrap;
    background: var(--panel);
    padding: 0.6rem;
    border-radius: 8px;
  }

  aside {
    background: var(--panel);
    border-radius: 12px;
    padding: 1rem 1.2rem;
    align-self: start;
  }
</style>

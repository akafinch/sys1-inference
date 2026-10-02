<script>
  // One typed answer, formatted by its type, beside the answer its preset intends.
  let { id, answer, intended } = $props()

  const f3 = (x) => x.toFixed(3)
  // A trained level reads "Critical; requires action within the same day.": its first words name it.
  const short = (text) => String(text).split(/[;:]/)[0]

  let levels = $derived(answer.type === 'score' ? Object.keys(answer.legend).length : 0)
  // the level the expected score sits nearest
  let level = $derived(answer.type === 'score' ? Math.min(levels - 1, Math.max(0, Math.round(answer.score))) : 0)

  let hit = $derived(
    answer.type === 'choice' ? answer.choice === intended
    : answer.type === 'score' ? level === intended
    : answer.noul >= 0.5 === intended,
  )

  function describe(value) {
    if (answer.type === 'score') return `level ${value}, ${short(answer.legend[value])}`
    if (answer.type === 'noul') return value ? 'yes' : 'no'
    return value
  }
</script>

<article>
  <h3><span class="id">{id}</span> <span class="muted">{answer.type}</span></h3>

  {#if answer.type === 'choice'}
    <p class="headline"><strong>{answer.choice}</strong> <span class="muted">confidence {f3(answer.confidence)}</span></p>
    <ul>
      {#each Object.entries(answer.probabilities) as [option, p] (option)}
        <li class:top={option === answer.choice}>
          <span class="name">{option}</span>
          <span class="track"><span class="fill" style:width="{p * 100}%"></span></span>
          <span class="value">{f3(p)}</span>
        </li>
      {/each}
    </ul>
  {:else if answer.type === 'score'}
    <p class="headline">
      <strong>{answer.score.toFixed(2)}</strong>
      nearest level {level}: {answer.legend[level]}
      <span class="muted">confidence {f3(answer.confidence)}</span>
    </p>
    <ul>
      {#each Object.entries(answer.probabilities) as [i, p] (i)}
        <li class:top={Number(i) === level}>
          <span class="name" title={answer.legend[i]}>{i} · {short(answer.legend[i])}</span>
          <span class="track"><span class="fill" style:width="{p * 100}%"></span></span>
          <span class="value">{f3(p)}</span>
        </li>
      {/each}
    </ul>
  {:else if answer.type === 'noul'}
    <p class="headline">
      <strong class="hero">{f3(answer.noul)}</strong>
      probability yes <span class="muted">· leans {answer.noul >= 0.5 ? 'yes' : 'no'}</span>
    </p>
    <span class="track meter"><span class="fill" style:width="{answer.noul * 100}%"></span></span>
  {:else}
    <pre>{JSON.stringify(answer, null, 2)}</pre>
  {/if}

  {#if intended !== undefined}
    <p class="intended">
      Intended: <strong>{describe(intended)}</strong>
      <span class={hit ? 'hit' : 'error'}>{hit ? '✓ matches' : '✗ differs'}</span>
    </p>
  {/if}
</article>

<style>
  article {
    margin-bottom: 1.2rem;
  }

  .id {
    font-family: var(--mono);
  }

  .headline {
    margin: 0.3rem 0 0.5rem;
    font-size: 1.1rem;
  }

  .headline strong {
    font-size: 1.6rem;
    margin-right: 0.3em;
  }

  .headline .hero {
    font-size: 3rem;
  }

  ul {
    list-style: none;
    padding: 0;
    margin: 0;
    display: grid;
    grid-template-columns: max-content minmax(8rem, 1fr) max-content;
    gap: 0.35rem 0.8rem;
    align-items: center;
  }

  li {
    display: contents;
  }

  .name {
    font-family: var(--mono);
    font-size: 0.9rem;
  }

  li.top .name,
  li.top .value {
    font-weight: 700;
  }

  .value {
    font-variant-numeric: tabular-nums;
  }

  .track {
    display: block;
    height: 18px;
    background: var(--track);
    border-radius: 4px;
  }

  .fill {
    display: block;
    height: 100%;
    background: var(--other);
    border-radius: 0 4px 4px 0;
  }

  li.top .fill,
  .meter .fill {
    background: var(--accent);
  }

  .meter {
    max-width: 30rem;
  }

  .intended {
    margin: 0.6rem 0 0;
  }

  .hit {
    color: var(--hit);
    font-weight: 600;
  }

  .error {
    font-weight: 600;
  }
</style>

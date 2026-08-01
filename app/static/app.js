const state = {
  scenario: null,
  mode: 'production',
  questionId: 'risk-signals',
  result: null,
}

const $ = (selector) => document.querySelector(selector)
const $$ = (selector) => Array.from(document.querySelectorAll(selector))
const PIPELINE_STEP_DELAY = 760

const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds))

function escapeHtml(value = '') {
  const element = document.createElement('div')
  element.textContent = String(value)
  return element.innerHTML
}

function renderScenario() {
  const scenario = state.scenario
  const transaction = scenario.case.transaction
  const customer = scenario.case.customer
  $('#case-id').textContent = scenario.case.case_id
  $('#case-title').textContent = scenario.case.question
  $('#case-facts').innerHTML = [
    ['Amount', `$${transaction.amount.toLocaleString()} ${transaction.currency}`],
    ['Customer', customer.name],
    ['Merchant', transaction.merchant],
    ['Network', `${transaction.ip_location} IP`],
  ]
    .map(([label, value]) => `<span><small>${label}</small>${escapeHtml(value)}</span>`)
    .join('')

  $('#mode-controls').innerHTML = scenario.modes
    .map(
      (mode) =>
        `<button class="mode-button ${mode.id === state.mode ? 'active' : ''}" data-mode="${mode.id}">${mode.label}</button>`
    )
    .join('')
  $('#question-controls').innerHTML = scenario.questions
    .map(
      (question) => `<option value="${escapeHtml(question.id)}" ${question.id === state.questionId ? 'selected' : ''}>
        ${escapeHtml(question.label)} — ${escapeHtml(question.question)}
      </option>`
    )
    .join('')
  $('#question-controls').innerHTML = `<select class="question-select" id="question-select" aria-label="Investigation question">${$('#question-controls').innerHTML}</select>`

  $$('.mode-button').forEach((button) =>
    button.addEventListener('click', () => {
      state.mode = button.dataset.mode
      renderScenario()
      renderIdleState()
    })
  )
  $('#question-select').addEventListener('change', (event) => {
    state.questionId = event.target.value
    renderIdleState()
  })

  const currentMode = scenario.modes.find((mode) => mode.id === state.mode)
  $('#mode-description').textContent = currentMode.description
}

function stageMarker(status) {
  if (status === 'warning') return '!'
  if (status === 'skipped') return '–'
  return '✓'
}

function renderPipeline(stages, pending = false) {
  $('#pipeline').innerHTML = stages
    .map(
      (stage, index) => `<div class="stage ${pending ? 'pending' : `${stage.status} resolved`}" data-stage-index="${index}">
        <div class="stage-heading">
          <strong>${escapeHtml(stage.stage)}</strong>
          <span class="stage-marker">${pending ? index + 1 : stageMarker(stage.status)}</span>
        </div>
        <span class="stage-detail">${escapeHtml(stage.detail)}</span>
      </div>`
    )
    .join('')
}

function idleStages() {
  if (state.mode === 'naive') {
    return [
      { stage: 'retrieve', status: 'complete', detail: 'Vector top-k only' },
      { stage: 'filter', status: 'skipped', detail: 'No evidence validation' },
      { stage: 'generate', status: 'warning', detail: 'Answer from unverified context' },
    ]
  }

  return [
    { stage: 'exact facts', status: 'complete', detail: 'Read structured case data' },
    { stage: 'retrieve', status: 'complete', detail: 'Find semantically relevant sources' },
    { stage: 'filter', status: 'complete', detail: 'Validate version, tenant and access' },
    { stage: 'cite', status: 'complete', detail: 'Build the evidence brief' },
  ]
}

function renderIdleState() {
  state.result = null
  const selectedQuestion = state.scenario.questions.find((question) => question.id === state.questionId)
  $('#result-mode').textContent = state.mode === 'production' ? 'Production RAG ready' : 'Naive RAG ready'
  $('#result-question').textContent = selectedQuestion.question
  $('#result-status').textContent = 'Waiting to run'
  $('#result-status').style.background = '#eef1f6'
  $('#result-status').style.color = 'var(--muted)'
  renderPipeline(idleStages(), true)
  $('#brief-panel').innerHTML = `
    <div class="idle-placeholder">
      <strong>Run the investigation when you are ready.</strong>
      <p>The pipeline will reveal each step before producing its evidence brief.</p>
    </div>`
  $('#sources-panel').innerHTML = '<p class="empty-state">Included sources will appear after the run.</p>'
  $('#discarded-panel').innerHTML = '<p class="empty-state">Rejected sources will appear after the run.</p>'
  $('#practice-panel').innerHTML = ''
}

function preparePipelineAnimation(result) {
  $('#result-mode').textContent = result.mode === 'production' ? 'Production RAG running' : 'Naive RAG running'
  $('#result-question').textContent = result.question
  $('#result-status').textContent = 'Inspecting evidence…'
  $('#result-status').style.background = 'var(--indigo-soft)'
  $('#result-status').style.color = 'var(--indigo)'
  renderPipeline(result.pipeline, true)
  $('#brief-panel').innerHTML = `
    <div class="investigation-placeholder">
      <span class="activity-dot" aria-hidden="true"></span>
      <div><strong>Following the evidence pipeline</strong><p>The final brief appears after every stage has completed.</p></div>
    </div>`
  $('#sources-panel').innerHTML = ''
  $('#discarded-panel').innerHTML = ''
  $('#practice-panel').innerHTML = ''
}

async function animatePipeline(stages) {
  const elements = $$('.stage')
  await sleep(180)

  for (const [index, stage] of stages.entries()) {
    const element = elements[index]
    element.classList.remove('pending')
    element.classList.add('active')
    element.querySelector('.stage-marker').textContent = '•'
    element.setAttribute('aria-current', 'step')
    await sleep(PIPELINE_STEP_DELAY)
    element.classList.remove('active')
    element.classList.add('resolved', stage.status)
    element.querySelector('.stage-marker').textContent = stageMarker(stage.status)
    element.removeAttribute('aria-current')
  }

  await sleep(180)
}

function list(items) {
  return items.length
    ? `<ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>`
    : '<p class="empty-state">No signals returned.</p>'
}

function renderBrief(brief) {
  $('#brief-panel').innerHTML = `
    <p class="brief-summary">${escapeHtml(brief.summary)}</p>
    ${brief.warning ? `<div class="warning-box">⚠ ${escapeHtml(brief.warning)}</div>` : ''}
    <div class="signal-grid">
      <article class="signal-card risk"><h3>${escapeHtml(brief.primary_label || 'Risk signals')}</h3>${list(brief.risk_signals)}</article>
      <article class="signal-card trust"><h3>${escapeHtml(brief.secondary_label || 'Trust signals')}</h3>${list(brief.trust_signals)}</article>
    </div>
    <article class="signal-card" style="margin-top:14px"><h3>${escapeHtml(brief.missing_label || 'Still unknown')}</h3>${list(brief.missing_evidence)}</article>
    <div class="decision"><div><span>Recommended next action</span><p>${escapeHtml(brief.recommended_action)}</p></div><span>Confidence: ${escapeHtml(brief.confidence)}</span></div>
  `
}

function renderPracticeCta() {
  $('#practice-panel').innerHTML = `
    <a class="practice-cta" href="https://codewithlucian.com/coding/embeddings_vector_search_rag?utm_source=rag_fraud_lab&utm_medium=project&utm_campaign=rag_at_10_million&utm_content=ai_questions_cta" target="_blank" rel="noopener noreferrer">
      <span class="practice-copy"><small>Continue with interview practice</small><strong>Can you explain these RAG trade-offs under interview pressure?</strong><span>Explore 33 focused questions on embeddings, vector search, and RAG.</span></span>
      <span class="practice-arrow" aria-hidden="true">→</span>
    </a>`
}

function renderSources(target, sources, rejected = false) {
  const element = $(target)
  if (!sources.length) {
    element.innerHTML = `<p class="empty-state">${rejected ? 'This pipeline did not reject any evidence.' : 'No evidence returned.'}</p>`
    return
  }
  element.innerHTML = `<div class="source-list">${sources
    .map(
      (source) => `<article class="source ${rejected ? 'rejected' : ''}">
        <div class="source-head"><strong>${escapeHtml(source.title)}</strong><span class="score">${Math.round(source.similarity * 100)}% similar</span></div>
        ${source.excluded_reason ? `<p class="reason">Rejected: ${escapeHtml(source.excluded_reason)}</p>` : ''}
        <p>${escapeHtml(source.content)}</p>
      </article>`
    )
    .join('')}</div>`
}

function renderResult(result) {
  state.result = result
  $('#result-mode').textContent = result.mode === 'production' ? 'Production RAG response' : 'Naive RAG response'
  $('#result-question').textContent = result.question
  $('#result-status').textContent = result.mode === 'production' ? 'Evidence verified' : 'Unverified context'
  $('#result-status').style.background = result.mode === 'production' ? 'var(--green-soft)' : 'var(--amber-soft)'
  $('#result-status').style.color = result.mode === 'production' ? 'var(--green)' : 'var(--amber)'
  renderPipeline(result.pipeline)
  renderBrief(result.brief)
  renderSources('#sources-panel', result.retrieved_evidence)
  renderSources('#discarded-panel', result.discarded_evidence, true)
  renderPracticeCta()
  $('.results').classList.remove('investigating')
  $('.results').classList.add('result-reveal')
  setTimeout(() => $('.results').classList.remove('result-reveal'), 420)
}

async function runInvestigation() {
  const button = $('#run-button')
  button.disabled = true
  button.firstChild.textContent = 'Running… '
  $$('.mode-button, #question-select').forEach((control) => (control.disabled = true))
  $('.results').classList.add('investigating')
  try {
    const response = await fetch('/api/investigate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question_id: state.questionId, mode: state.mode }),
    })
    if (!response.ok) throw new Error('Investigation failed')
    const result = await response.json()
    preparePipelineAnimation(result)
    await animatePipeline(result.pipeline)
    renderResult(result)
  } catch (error) {
    $('#brief-panel').innerHTML = `<div class="warning-box">Could not run the investigation. ${escapeHtml(error.message)}</div>`
    $('.results').classList.remove('investigating')
  } finally {
    button.disabled = false
    button.firstChild.textContent = 'Run investigation '
    $$('.mode-button, #question-select').forEach((control) => (control.disabled = false))
  }
}

async function start() {
  state.scenario = await fetch('/api/scenario').then((response) => response.json())
  renderScenario()
  $('#run-button').addEventListener('click', runInvestigation)
  renderIdleState()
}

start().catch((error) => {
  $('#brief-panel').innerHTML = `<div class="warning-box">Unable to load the demo: ${escapeHtml(error.message)}</div>`
})

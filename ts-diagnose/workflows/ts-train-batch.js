export const meta = {
  name: 'ts-train-batch',
  description: '一轮候选并行重训：每条候选派一张 worker 卡片，回 receipt 数组（不判定、不写账本、不问用户）',
  phases: [{ title: 'Train', detail: '每条候选一个 worker，chunk 内并行；判定与账本归主 agent' }],
}

// args = {engine, workdir, agent_type, task, candidates: [...], chunk}
// agent_type: 'model-improve-worker'（task=candidate|baseline）或 'architecture-attribution-worker'（task=intervention）
const CONTRACT = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['COMPUTE_DONE', 'NEED_INFO', 'BLOCKED'] },
    task: { type: 'string' },
    exp_id: { type: 'string' },
    hypothesis_id: { type: ['string', 'null'] },
    receipt_line: { type: 'string' },
    receipt_file: { type: 'string' },
    config_diff: { type: ['object', 'array'] },
    per_seed: { type: 'array', items: { type: 'number' } },
    mean: { type: ['number', 'null'] },
    std: { type: ['number', 'null'] },
    run_status: { type: 'array', items: { type: 'string' } },
    metrics_dirs: { type: 'array', items: { type: 'string' } },
    slices_per_seed: { type: 'array', items: { type: 'object' } },
    summary_file: { type: 'string' },
    need_info: { type: 'array', items: { type: 'string' } },
    blocked_reason: { type: 'string' },
  },
  required: ['status', 'task', 'run_status'],
}

const a = args || {}
if (!a.engine || !a.workdir || !a.agent_type || !Array.isArray(a.candidates) || a.candidates.length === 0) {
  throw new Error('args 须含 engine / workdir / agent_type / 非空 candidates[]')
}
const task = a.task || 'candidate'
const chunk = Math.max(1, Number(a.chunk) || 4)

function idOf(c) {
  return c.exp_id || c.hypothesis_id || 'unknown'
}

function pickInputFields(c) {
  const picked = {}
  for (const k of ['exp_id', 'hypothesis_id', 'config_diff', 'guard_slices']) {
    if (c[k] !== undefined) picked[k] = c[k]
  }
  return picked
}

function prompt(c) {
  return [
    `任务类型 task：${task}`,
    `工作目录：${a.workdir}`,
    `引擎目录：${a.engine}`,
    '按你的卡片执行下面这一条任务；final message 只回卡片「输出契约」的 JSON，不回其他文字：',
    JSON.stringify(pickInputFields(c)),
  ].join('\n')
}

phase('Train')
const results = []
for (let i = 0; i < a.candidates.length; i += chunk) {
  const part = a.candidates.slice(i, i + chunk)
  log(`训练批次 ${Math.floor(i / chunk) + 1}/${Math.ceil(a.candidates.length / chunk)}：${part.map(idOf).join(', ')}`)
  const got = await parallel(part.map(c => () =>
    agent(prompt(c), { agentType: a.agent_type, schema: CONTRACT, label: `train:${idOf(c)}`, phase: 'Train' })))
  got.forEach((r, j) => {
    results.push(r || {
      status: 'BLOCKED', task, exp_id: part[j].exp_id || '', hypothesis_id: part[j].hypothesis_id || null,
      run_status: ['crash'], blocked_reason: 'worker 无返回（被跳过或异常终止）',
    })
  })
}
const failed = results.filter(r => r.status !== 'COMPUTE_DONE').map(r => r.exp_id || r.hypothesis_id)
if (failed.length) log(`未完成 ${failed.length} 条：${failed.join(', ')}`)
return { results, failed }

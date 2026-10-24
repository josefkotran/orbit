// A turn as the engine raises it (start, a streamed request with thinking, text and a tool, the tool's call, the
// end) and the "Mozek" pane drawn on the terminal and the desktop: what it shows.
import { expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'

/** What the engine itself answers beneath the plugin, as plainly as the plugin needs it. */
function engine(on: On) {
  on('session.start', ($, e) => ({ cwd: e.cwd }))
  on('command.register', () => ({ value: {} }) as never)
  on('turn.start', ($, e) => ({ turnId: e.turnId }))
  on('turn.complete', ($, e) => ({ text: e.answer }))
}

const pane = {
  component: 'Pane',
  requestId: 'mozek',
  props: { title: 'Mozek', isFocused: false, bodyColumns: 60, placement: 'dock', scroll: { offset: 0, bodyRows: 60 }, view: {} },
} as const

const square = (color: string, isFilled: boolean) => ({
  color, isFilled, categoryName: isFilled ? 'Messages' : 'Free space', tokens: 50000, percentage: 25, squareFullness: isFilled ? 1 : 0,
})

test('a turn shows in the pane: thinking, the tool and its time, the context', async ($, on) => {
  const clock = mock.clock(on, { now: 1_000 })
  engine(on)
  on('session.model', () => ({ value: 'claude-opus-5-5' }))
  on('session.usage', () => ({ value: {
    startedAt: 0,
    context: {
      window: 200_000, tokens: 50_000, percent: 25,
      breakdown: {
        categories: [
          { name: 'Messages', tokens: 50_000, color: 'claude', isDeferred: false, kind: 'used' as const },
          { name: 'Free space', tokens: 150_000, color: 'inactive', isDeferred: false, kind: 'free' as const },
        ],
        totalTokens: 50_000, maxTokens: 200_000, rawMaxTokens: 200_000, autocompactSource: 'model' as never,
        percentage: 25, gridRows: [[square('claude', true), square('inactive', false)]], model: 'claude-opus-5-5',
        memoryFiles: [], mcpTools: [], agents: [], isAutoCompactEnabled: true, apiUsage: null,
      },
    },
    rateLimits: [{ kind: 'five_hour', percentUsed: 23 }],
  } }))
  on('turn.step', async function* () {
    yield { kind: 'thinking' as const, index: 0, text: 'Nejdřív si přečtu ceník, pak ' }
    yield { kind: 'thinking' as const, index: 0, text: 'porovnám ceny.' }
    yield { kind: 'tool' as const, index: 1, id: 'tu1', name: 'Read' }
    yield { kind: 'stop' as const, stopReason: 'tool_use' as const, usage: { input_tokens: 10, output_tokens: 420, cache_creation_input_tokens: 0, cache_read_input_tokens: 0, model: 'opus' } }
    return { turnId: 't1', index: 0, answer: '', toolUses: [], stopReason: 'tool_use' as const, usage: null }
  })
  on('tool.call', async () => {
    await clock.sleep(1_500)
    return { result: 'obsah' }
  })

  await $.session.start({ cwd: 'C:/projekt', surface: 'terminal', isInteractive: true })
  await $.turn.start({ text: 'Porovnej ceník', turnId: 't1' })
  for await (const _ of $.turn.step({ turnId: 't1', index: 0, model: 'claude-opus-5-5', messageCount: 1 })) {
    // the plugin sees each piece on its way
  }
  const call = $.tool.call({ tool: 'Read', file_path: 'C:/projekt/data/cenik.md', tool_use_id: 'tu1' })
  await clock.advance(1_500)
  await call
  await $.turn.complete({ answer: 'Hotovo.', durationMs: 4_000, isAborted: false, turnId: 't1', reason: 'end_turn' as never })
  await clock.advance(3_000)

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ plugin: 'orbit-mozek', surface, ...pane })
    expect(await ui.find({ type: 'Text', text: /porovnám ceny/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /cenik\.md/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /1,5 s/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /poslední tah 4 s/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /5 h 23 %/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /Zprávy/ })).toBeDefined()
    await ui.unmount()
  }
})

test('/mozek opens the pane and writes nothing into the conversation', async ($, on) => {
  mock.clock(on)
  engine(on)
  const opened: string[] = []
  on('ui.open', ($, e) => {
    opened.push(e.id)
    return { value: {} } as never
  })
  await $.session.start({ cwd: 'C:/projekt', surface: 'terminal', isInteractive: true })
  // origin and presentation: the kit stamps them as the engine does
  const ran = await $.command.run({ command: 'mozek', args: '' } as never)
  expect(ran.text).toBeUndefined()
  expect(opened).toEqual(['mozek'])
})

// After each turn the engine hands over the limits the answers reported; the mod leaves them for Orbit's panel in
// every Orbit data folder it finds (one with config.json), and nothing anywhere else.
test('the limits go to Orbit, without asking anything', async ($, on) => {
  mock.clock(on, { now: 1_760_000_000_000 })
  engine(on)
  on('session.measure', ($, e) => ({ changed: e.changed }))
  on('session.id', () => ({ value: 'sess-1' }))
  mock.env(on, { LOCALAPPDATA: 'C:\\Users\\jana\\AppData\\Local', USERPROFILE: 'C:\\Users\\jana' })
  const norm = (path: string): string => path.replace(/\\/g, '/')
  // only the checkout in ~/orbit is an Orbit data folder here (no installed Orbit)
  on('fs.exists', ($, e) => ({ value: norm(e.path) === 'C:/Users/jana/orbit/config.json' }))
  const written: { path: string; text: string }[] = []
  on('fs.write', ($, e) => {
    written.push({ path: norm(e.path), text: e.text })
    return { value: undefined }
  })
  const context = { window: 200_000, tokens: 50_000, percent: 25 }

  await $.session.start({ cwd: 'C:/projekt', surface: 'terminal', isInteractive: true })
  await $.session.measure({ context, rateLimits: [], changed: ['context'] })
  expect(written).toEqual([]) // no reading yet
  await $.session.measure({
    context,
    rateLimits: [
      { kind: 'five_hour', percentUsed: 23.5, resetsAt: '2025-10-09T14:00:00.000Z' },
      { kind: 'seven_day', percentUsed: 41 },
      { kind: 'spend_limit', percentUsed: 10 },
    ],
    changed: ['context', 'rateLimits'],
  })
  expect(written.map(w => w.path)).toEqual(['C:/Users/jana/orbit/sessions/status/sess-1.mod.json'])
  const record = JSON.parse(written[0]!.text) as Record<string, unknown>
  expect(record.session_id).toBe('sess-1')
  expect(record.time).toBe(1_760_000_000)
  expect(record.rate_limits).toEqual({
    five_hour: { used_percentage: 23.5, resets_at: '2025-10-09T14:00:00.000Z' },
    seven_day: { used_percentage: 41 },
  })
})

// Orbit asks the session to stop a background shell nobody needs: the mod finds the request in Orbit's data folder,
// stops the shell with TaskStop (Claude Code knows, the session isn't woken up) and answers next to it. Another
// session's request and one Orbit gave up on long ago are left alone.
test('a shell Orbit asks to stop is stopped with TaskStop, and the answer goes back', async ($, on) => {
  const clock = mock.clock(on, { now: 1_760_000_000_000 })
  engine(on)
  on('session.id', () => ({ value: 'sess-1' }))
  mock.env(on, { USERPROFILE: 'C:\\Users\\jana' })
  const norm = (path: string): string => path.replace(/\\/g, '/')
  const stopDir = 'C:/Users/jana/orbit/sessions/stop'
  on('fs.exists', ($, e) => ({ value: norm(e.path) === 'C:/Users/jana/orbit/config.json' }))
  const now = 1_760_000_000
  const requests: Record<string, string> = {
    'sess-1.bh3di8ppc.json': JSON.stringify({ session_id: 'sess-1', task_id: 'bh3di8ppc', time: now }),
    'sess-2.bxfglwn8j.json': JSON.stringify({ session_id: 'sess-2', task_id: 'bxfglwn8j', time: now }),
    'sess-1.bold0000.json': JSON.stringify({ session_id: 'sess-1', task_id: 'bold0000', time: now - 3600 }),
  }
  const file = (name: string) => ({ name, kind: 'file' as const, size: 80, mtimeMs: 1, isLink: false })
  on('fs.list', ($, e) => ({ value: norm(e.path ?? '') === stopDir ? Object.keys(requests).map(file) : [] }) as never)
  on('fs.read', ($, e) => ({ value: requests[norm(e.path).split('/').pop() ?? ''] ?? '' }) as never)
  const written: { path: string; text: string }[] = []
  on('fs.write', ($, e) => {
    written.push({ path: norm(e.path), text: e.text })
    return { value: undefined }
  })
  const stopped: string[] = []
  on('tool.call', { tool: 'TaskStop' }, ($, e) => {
    stopped.push(String((e as { task_id?: string }).task_id))
    return { result: { message: 'Successfully stopped task' }, text: 'Successfully stopped task: bh3di8ppc' } as never
  })

  await $.session.start({ cwd: 'C:/projekt', surface: 'terminal', isInteractive: true })
  await clock.advance(2_000)
  expect(stopped).toEqual(['bh3di8ppc'])
  expect(written.map(w => w.path)).toEqual([`${stopDir}/sess-1.bh3di8ppc.done.json`])
  expect(JSON.parse(written[0]!.text)).toEqual({ ok: true, text: 'Successfully stopped task: bh3di8ppc' })
  await clock.advance(4_000) // the same request again (Orbit hasn't removed it yet): not stopped twice
  expect(stopped).toEqual(['bh3di8ppc'])
})

// Orbit's Autopilot hands the session a prompt (a round of work, what the user said on the phone): the mod finds it in
// Orbit's data folder, submits it as the user's own words and answers next to it. Another session's prompt and one
// Orbit gave up on long ago are left alone; a session busy with a turn gets it queued, and Orbit hears so.
test("a prompt from Orbit is submitted as the user's words, and the answer goes back", async ($, on) => {
  const clock = mock.clock(on, { now: 1_760_000_000_000 })
  engine(on)
  on('session.id', () => ({ value: 'sess-1' }))
  mock.env(on, { USERPROFILE: 'C:\\Users\\jana' })
  const norm = (path: string): string => path.replace(/\\/g, '/')
  const promptDir = 'C:/Users/jana/orbit/sessions/prompt'
  on('fs.exists', ($, e) => ({ value: norm(e.path) === 'C:/Users/jana/orbit/config.json' }))
  const now = 1_760_000_000
  const requests: Record<string, string> = {
    'sess-1.a1b2c3d4.json': JSON.stringify({ session_id: 'sess-1', id: 'a1b2c3d4', time: now, text: 'Autopilot: kolo 1' }),
    'sess-2.e5f6a7b8.json': JSON.stringify({ session_id: 'sess-2', id: 'e5f6a7b8', time: now, text: 'cizí relace' }),
    'sess-1.c0ffee00.json': JSON.stringify({ session_id: 'sess-1', id: 'c0ffee00', time: now - 3600, text: 'staré' }),
  }
  const file = (name: string) => ({ name, kind: 'file' as const, size: 80, mtimeMs: 1, isLink: false })
  on('fs.list', ($, e) => ({ value: norm(e.path ?? '') === promptDir ? Object.keys(requests).map(file) : [] }) as never)
  on('fs.read', ($, e) => ({ value: requests[norm(e.path).split('/').pop() ?? ''] ?? '' }) as never)
  const written: { path: string; text: string }[] = []
  on('fs.write', ($, e) => {
    written.push({ path: norm(e.path), text: e.text })
    return { value: undefined }
  })
  const submitted: { text: string; asUser?: boolean }[] = []
  let busy = false
  on('prompt.submit', async ($, e) => {
    submitted.push({ text: e.text, asUser: e.origin.kind === 'plugin' ? e.origin.asUser : undefined })
    if (busy) await clock.sleep(60_000) // a turn runs: the prompt waits for it
    return { text: e.text, origin: e.origin }
  })

  await $.session.start({ cwd: 'C:/projekt', surface: 'terminal', isInteractive: true })
  await clock.advance(2_000)
  expect(submitted).toEqual([{ text: 'Autopilot: kolo 1', asUser: true }])
  expect(written.map(w => w.path)).toEqual([`${promptDir}/sess-1.a1b2c3d4.done.json`])
  expect(JSON.parse(written[0]!.text)).toEqual({ ok: true, text: 'started' })
  await clock.advance(4_000) // the same request again (Orbit hasn't removed it yet): not submitted twice
  expect(submitted.length).toBe(1)

  busy = true
  requests['sess-1.d00d1e55.json'] = JSON.stringify({ session_id: 'sess-1', id: 'd00d1e55', time: now + 6, text: 'kolo 2' })
  await clock.advance(2_000)
  await clock.advance(QUEUED)
  expect(submitted.map(s => s.text)).toEqual(['Autopilot: kolo 1', 'kolo 2'])
  expect(JSON.parse(written.at(-1)!.text)).toEqual({ ok: true, text: 'queued' })
})

const QUEUED = 1_600

// Orbit switches the session to the model picked in its panel: the mod runs Claude Code's own /model with the alias,
// says it took the request (.ack) and what came of it (.done, with the model the session runs on now). Another
// session's request, one Orbit gave up on, and anything that isn't one of Orbit's aliases are left alone.
test('a model switch from Orbit runs /model in the session and the answer goes back', async ($, on) => {
  const clock = mock.clock(on, { now: 1_760_000_000_000 })
  engine(on)
  on('session.id', () => ({ value: 'sess-1' }))
  let model = 'claude-opus-5-5'
  on('session.model', () => ({ value: model }))
  mock.env(on, { USERPROFILE: 'C:\\Users\\jana' })
  const norm = (path: string): string => path.replace(/\\/g, '/')
  const modelDir = 'C:/Users/jana/orbit/sessions/model'
  on('fs.exists', ($, e) => ({ value: norm(e.path) === 'C:/Users/jana/orbit/config.json' }))
  const now = 1_760_000_000
  const requests: Record<string, string> = {
    'sess-1.a1b2c3d4e5f6.json': JSON.stringify({ session_id: 'sess-1', id: 'a1b2c3d4e5f6', time: now, model: 'sonnet' }),
    'sess-2.e5f6a7b8c9d0.json': JSON.stringify({ session_id: 'sess-2', id: 'e5f6a7b8c9d0', time: now, model: 'haiku' }),
    'sess-1.c0ffee00c0ff.json': JSON.stringify({ session_id: 'sess-1', id: 'c0ffee00c0ff', time: now - 3600, model: 'haiku' }),
    'sess-1.bad0bad0bad0.json': JSON.stringify({ session_id: 'sess-1', id: 'bad0bad0bad0', time: now, model: 'haiku --x' }),
  }
  const file = (name: string) => ({ name, kind: 'file' as const, size: 80, mtimeMs: 1, isLink: false })
  on('fs.list', ($, e) => ({ value: norm(e.path ?? '') === modelDir ? Object.keys(requests).map(file) : [] }) as never)
  on('fs.read', ($, e) => ({ value: requests[norm(e.path).split('/').pop() ?? ''] ?? '' }) as never)
  const written: { path: string; text: string }[] = []
  on('fs.write', ($, e) => {
    written.push({ path: norm(e.path), text: e.text })
    return { value: undefined }
  })
  on('ui.toast', () => ({ value: undefined }))
  const ran: { command: string; args: string }[] = []
  on('command.run', ($, e) => {
    ran.push({ command: e.command, args: e.args })
    model = 'claude-sonnet-5-5'
    return { text: 'Set model to `Sonnet 5.5` and saved as your default for new sessions' }
  })

  await $.session.start({ cwd: 'C:/projekt', surface: 'terminal', isInteractive: true })
  await clock.advance(2_000)
  expect(ran).toEqual([{ command: 'model', args: 'sonnet' }])
  expect(written.map(w => w.path)).toEqual([
    `${modelDir}/sess-1.a1b2c3d4e5f6.ack.json`, `${modelDir}/sess-1.a1b2c3d4e5f6.done.json`,
  ])
  expect(JSON.parse(written[1]!.text)).toEqual({
    ok: true, text: 'Set model to `Sonnet 5.5` and saved as your default for new sessions', model: 'claude-sonnet-5-5',
  })
  await clock.advance(4_000) // the same request again (Orbit hasn't removed it yet): not run twice
  expect(ran.length).toBe(1)
})
